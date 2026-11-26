"""Inti lokalisasi: model dan peta dimuat sekali, lalu satu foto dilokalisasi per panggilan.

Satu-satunya pemilik logika lokalisasi. Dipakai layanan (server/app.py) dan alat ukur
(spike/bench_localize.py), supaya angka yang diukur adalah angka kode yang dilayankan.

Alur: deskriptor global (MegaLoc), retrieval k foto peta, fitur lokal (ALIKED), pencocokan
(LightGlue) ke k kandidat, lalu PnP + RANSAC. Korespondensi 2D-3D mengikuti
hloc.localize_sfm.pose_from_cluster (commit c13273b), tapi di memori. Sengaja TIDAK memakai
hloc.localize_sfm.main(): saat PnP gagal, fungsi itu menulis pose foto peta teratas alih-alih
melaporkan gagal (docs/multi-map-localization-research.md).
"""

import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np
import pycolmap
import torch
from hloc import extract_features, extractors, match_features, matchers
from hloc.extract_features import resize_image
from hloc.localize_sfm import QueryLocalizer
from hloc.utils.base_model import dynamic_load

from server import sim3
from server.alignment import AlignFile
from server.map_layout import missing_files

# ponytail: ambang awal. Di spike, pose salah punya 6 sampai 14 inlier dan pose benar ratusan.
# Setel ulang dengan kolom inliers di errors_m.csv dari data lapangan.
MIN_INLIERS = 50
AMBIGUOUS_SCORE_DELTA = 0.02
AMBIGUOUS_DISTANCE_M = 5.0
PRIOR_RADIUS_DEFAULT_M = 20.0
PRIOR_RADIUS_MIN_M = 5.0
PRIOR_RADIUS_MAX_M = 50.0
DEEP_SEARCH_K = 10

MEGALOC = extract_features.confs["megaloc"]
ALIKED = extract_features.confs["aliked-n16"]
LIGHTGLUE = match_features.confs["aliked+lightglue"]
LEGACY_DETECTION_THRESHOLD = 0.2


def map_detection_threshold(run_dir: Path) -> float:
    path = run_dir / "summary.json"
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return LEGACY_DETECTION_THRESHOLD
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: cannot read map metadata: {exc}") from exc
    if not isinstance(summary, dict):
        raise ValueError(f"{path}: expected a JSON object")

    value = summary.get("detection_threshold", LEGACY_DETECTION_THRESHOLD)
    message = f"{path}: detection_threshold must be a positive finite number"
    if type(value) not in (int, float):
        raise ValueError(message)
    try:
        threshold = float(value)
    except OverflowError as exc:
        raise ValueError(message) from exc
    if not 0 < threshold < math.inf:
        raise ValueError(message)
    return threshold


def half(x):
    # hloc menyimpan fitur sebagai float16 (as_half=True); tiru agar hasilnya setara
    return x.astype(np.float16).astype(np.float32)


def trust_megaloc_hub_repo():
    """Tandai repo torch hub gmberton/MegaLoc sebagai tepercaya.

    hloc memuat MegaLoc lewat torch.hub.load tanpa trust_repo. Bawaan torch ("check") bertanya y/N
    secara interaktif untuk repo yang belum tepercaya, dan di container itu membuat layanan macet.
    Kode repo itu sudah dibaca (hanya torch, bobot safetensors, docs/spike-plan.md), jadi ditandai
    tepercaya secara eksplisit, dengan cara yang sama seperti torch mencatatnya."""
    hub = Path(torch.hub.get_dir())
    hub.mkdir(parents=True, exist_ok=True)
    trusted = hub / "trusted_list"
    names = trusted.read_text(encoding="utf-8").split() if trusted.exists() else []
    if "gmberton_MegaLoc" not in names:
        with trusted.open("a", encoding="utf-8") as f:
            f.write("gmberton_MegaLoc\n")


def compute_inlier_ratio(inliers: int, correspondences: int) -> float | None:
    """Rasio inlier terhadap korespondensi, None bila korespondensi nol."""
    if correspondences <= 0:
        return None
    return float(inliers) / float(correspondences)


def median_reprojection_error_px(
    cam_from_world: pycolmap.Rigid3d | None,
    points2d: np.ndarray,
    points3d: np.ndarray,
    inlier_mask: np.ndarray | None,
    camera: pycolmap.Camera,
) -> float | None:
    """Galat reproyeksi median (piksel) pada inlier PnP, None bila tidak bisa dihitung."""
    if cam_from_world is None or inlier_mask is None or len(points2d) == 0:
        return None
    mask = np.asarray(inlier_mask, dtype=bool)
    if len(mask) != len(points2d) or not np.any(mask):
        return None
    pts2d_in = np.asarray(points2d, dtype=np.float64)[mask]
    pts3d_in = np.asarray(points3d, dtype=np.float64)[mask]
    rot = cam_from_world.rotation.matrix()
    cam_pts = (rot @ pts3d_in.T).T + cam_from_world.translation
    proj = camera.img_from_cam(cam_pts)
    finite = np.all(np.isfinite(proj), axis=1)
    if not np.any(finite):
        return None
    errs = np.linalg.norm(proj[finite] - pts2d_in[finite], axis=1)
    return float(np.median(errs))


def retrieval_is_ambiguous(
    scores: np.ndarray,
    centers_model: list[np.ndarray | None],
    scale_m: float | None,
    *,
    score_delta: float = AMBIGUOUS_SCORE_DELTA,
    distance_m: float = AMBIGUOUS_DISTANCE_M,
) -> bool:
    """True bila dua kandidat top-k berskor selisih <= score_delta tetapi berjauhan > distance_m."""
    if scale_m is None or scale_m <= 0 or len(scores) < 2:
        return False
    n = min(len(scores), len(centers_model))
    for i in range(n):
        ci = centers_model[i]
        if ci is None:
            continue
        si = float(scores[i])
        for j in range(i + 1, n):
            cj = centers_model[j]
            if cj is None:
                continue
            if abs(si - float(scores[j])) <= score_delta:
                if float(np.linalg.norm(ci - cj)) * scale_m > distance_m:
                    return True
    return False


def clamp_prior_radius(radius_m: float | None) -> float:
    """Radius prior dalam meter: bawaan 20 m, dijepit ke [5, 50]."""
    if radius_m is None:
        return PRIOR_RADIUS_DEFAULT_M
    return max(PRIOR_RADIUS_MIN_M, min(PRIOR_RADIUS_MAX_M, float(radius_m)))


def filter_prior_indices(
    db_centers_model: list[np.ndarray | None],
    align: dict | None,
    prior_xy: tuple[float, float],
    radius_m: float,
) -> list[int]:
    """Indeks gambar peta yang pusat kameranya (di kerangka gedung G) berada dalam radius prior."""
    if align is None:
        return []
    sim = sim3.from_align(align["meter_from_model"])
    px, py = float(prior_xy[0]), float(prior_xy[1])
    kept = []
    for i, center in enumerate(db_centers_model):
        if center is None:
            continue
        pos_g = (sim * np.asarray(center, dtype=np.float64)[None])[0]
        if math.hypot(float(pos_g[0]) - px, float(pos_g[1]) - py) <= radius_m:
            kept.append(i)
    return kept


@dataclass
class Result:
    ok: bool
    inliers: int
    correspondences: int
    cam_from_world: pycolmap.Rigid3d | None  # kerangka model SfM
    center_model: list[float] | None
    t: dict[str, float] = field(default_factory=dict)
    inlier_ratio: float | None = None
    reprojection_error_px_median: float | None = None
    retrieval_top1: float | None = None
    ambiguous: bool = False
    prior_used: bool = False
    outside_prior: bool = False
    deep_search: bool = False

    def __post_init__(self) -> None:
        if self.inlier_ratio is None and self.correspondences > 0:
            self.inlier_ratio = compute_inlier_ratio(self.inliers, self.correspondences)


class Localizer:
    def __init__(
        self,
        map_dir: Path,
        *,
        max_kp: int = 1024,
        resize: int = 1024,
        global_resize: int = 512,
        k: int = 5,
        device: str = "cpu",
        min_inliers: int = 0,
        align_source=None,  # callable -> dict | None, mis. alignment.DbAlign(...).get
    ):
        self.dev = torch.device(device)
        self.resize, self.global_resize, self.k = resize, global_resize, k
        self.min_inliers = min_inliers
        # Periksa peta dulu: pesan yang jelas, dan tidak membuang waktu memuat model.
        if missing := missing_files(map_dir, max_kp, resize, global_resize):
            raise FileNotFoundError(f"map is incomplete in {map_dir}: {[str(p) for p in missing]}")

        run_dir = map_dir / f"kp{max_kp}-r{resize}"
        self.detection_threshold = map_detection_threshold(run_dir)
        aliked = {
            **ALIKED,
            "model": {
                **ALIKED["model"],
                "max_num_keypoints": max_kp,
                "detection_threshold": self.detection_threshold,
            },
        }
        t0 = time.perf_counter()
        trust_megaloc_hub_repo()
        self.megaloc = self._load(extractors, MEGALOC)
        self.aliked = self._load(extractors, aliked)
        self.lightglue = self._load(matchers, LIGHTGLUE)
        self.t_load_models = time.perf_counter() - t0

        t0 = time.perf_counter()
        self.model = pycolmap.Reconstruction(run_dir / "sfm")
        self.db = self._load_db(run_dir / "features.h5", map_dir / f"global-r{global_resize}.h5")
        self.db_names = list(self.db)
        self.db_global = np.stack([self.db[n]["global"] for n in self.db_names])
        self.map_camera = next(iter(self.model.cameras.values()))
        self.pnp = QueryLocalizer(self.model, {"estimation": {"ransac": {"max_error": 12}}})
        # ditulis spike/eval_meter.py lalu dipasang manage align; dibaca ulang saat berganti
        self._align = AlignFile(run_dir / "align.json")
        self._align_source = align_source
        self.t_load_map = time.perf_counter() - t0

    @property
    def align(self) -> dict | None:
        # dashboard (database) lebih dulu; kosong berarti align.json (manage align)
        if self._align_source is not None and (dash := self._align_source()) is not None:
            return dash
        return self._align.get()

    def _load(self, pkg, conf):
        return dynamic_load(pkg, conf["model"]["name"])(conf["model"]).eval().to(self.dev)

    def _load_db(self, local_h5: Path, global_h5: Path):
        db = {}
        with h5py.File(local_h5, "r") as fl, h5py.File(global_h5, "r") as fg:
            for image_id, image in self.model.images.items():
                g = fl[image.name]
                db[image.name] = {
                    "id": image_id,
                    "keypoints": self._t(g["keypoints"].__array__()),
                    "descriptors": self._t(g["descriptors"].__array__()),
                    "size": tuple(g["image_size"].__array__()),
                    "global": fg[image.name]["global_descriptor"].__array__().astype(np.float32),
                    "center_model": image.projection_center().astype(np.float64),
                    "points3D_ids": np.array(
                        [p.point3D_id if p.has_point3D() else -1 for p in image.points2D]
                    ),
                }
        return db

    def _db_center(self, name: str) -> np.ndarray | None:
        d = self.db.get(name)
        if d is None:
            return None
        center = d.get("center_model")
        if center is not None:
            return center
        img = self.model.images.get(d["id"])
        return img.projection_center().astype(np.float64) if img is not None else None

    def _align_scale(self) -> float | None:
        align = self.align
        if align is None:
            return None
        return float(align["meter_from_model"]["scale"])

    def _t(self, a):
        return torch.from_numpy(a).float()[None].to(self.dev)

    def _prep(self, image: np.ndarray, resize_max: int):
        """Sama dengan hloc ImageDataset: RGB float, sisi terpanjang <= resize_max, skala 0..1."""
        size = image.shape[:2][::-1]
        if max(size) > resize_max:
            scale = resize_max / max(size)
            image = resize_image(image, tuple(round(x * scale) for x in size), "cv2_area")
        tensor = torch.from_numpy(image.transpose((2, 0, 1)) / 255.0)[None].to(self.dev)
        return tensor, np.array(size)

    def same_size_as_map(self, width: int, height: int) -> bool:
        """Ponsel sama, resolusi sama: intrinsik kalibrasi peta lebih baik dari taksiran EXIF."""
        return (width, height) == (self.map_camera.width, self.map_camera.height)

    def _run_pnp_attempt(
        self,
        order: np.ndarray,
        scores: np.ndarray,
        kp: np.ndarray,
        q_kp_t: torch.Tensor,
        q_desc_t: torch.Tensor,
        size: np.ndarray,
        camera: pycolmap.Camera,
        align_scale: float | None,
        match_cache: dict[str, np.ndarray],
    ):
        cand = [self.db_names[int(i)] for i in order]
        top_scores = scores[order] if len(order) > 0 else np.empty((0,), dtype=np.float32)
        retrieval_top1 = float(top_scores[0]) if len(top_scores) > 0 else None
        ambiguous = retrieval_is_ambiguous(
            top_scores, [self._db_center(n) for n in cand], align_scale
        )

        t0 = time.perf_counter()
        kp_idx_to_3D = defaultdict(list)
        for name in cand:
            d = self.db[name]
            matches = match_cache.get(name)
            if matches is None:
                out = self.lightglue(
                    {
                        "image0": torch.empty((1, 1, *size[::-1]), device=self.dev),
                        "keypoints0": q_kp_t,
                        "descriptors0": q_desc_t,
                        "image1": torch.empty((1, 1, *d["size"][::-1]), device=self.dev),
                        "keypoints1": d["keypoints"],
                        "descriptors1": d["descriptors"],
                    }
                )
                m0 = out["matches0"][0].cpu().numpy()
                idx = np.where(m0 > -1)[0]
                matches = np.stack([idx, m0[idx]], -1)
                matches = matches[d["points3D_ids"][matches[:, 1]] != -1]
                match_cache[name] = matches
            for qi, mi in matches:
                id3 = d["points3D_ids"][mi]
                if id3 not in kp_idx_to_3D[qi]:
                    kp_idx_to_3D[qi].append(id3)
        match_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        idxs = list(kp_idx_to_3D.keys())
        mkp = [i for i in idxs for _ in kp_idx_to_3D[i]]
        mp3d = [j for i in idxs for j in kp_idx_to_3D[i]]
        pts2d_all = kp + 0.5  # +0.5: koordinat COLMAP
        ret = self.pnp.localize(pts2d_all, mkp, mp3d, camera) if mp3d else None
        reproj_median = None
        if ret is not None and int(ret["num_inliers"]) > 0 and len(mp3d) > 0:
            pts3d_arr = np.asarray([self.model.points3D[j].xyz for j in mp3d], dtype=np.float64)
            reproj_median = median_reprojection_error_px(
                ret["cam_from_world"], pts2d_all[mkp], pts3d_arr, ret.get("inlier_mask"), camera
            )
        pose_s = time.perf_counter() - t0

        inliers = int(ret["num_inliers"]) if ret else 0
        correspondences = len(mp3d)
        inlier_ratio = compute_inlier_ratio(inliers, correspondences)
        ok = ret is not None and inliers >= self.min_inliers
        pose = ret["cam_from_world"] if ok else None
        center = pose.inverse().translation.tolist() if ok else None
        return (
            ok,
            inliers,
            correspondences,
            pose,
            center,
            inlier_ratio,
            reproj_median,
            retrieval_top1,
            ambiguous,
            match_s,
            pose_s,
        )

    def _localize_from_features(
        self,
        desc: np.ndarray,
        kp: np.ndarray,
        q_desc: np.ndarray,
        size: np.ndarray,
        camera: pycolmap.Camera,
        *,
        t_init: dict[str, float],
        prior_xy: tuple[float, float] | None = None,
        prior_radius_m: float | None = None,
    ) -> Result:
        t = dict(t_init)
        align = self.align
        align_scale = float(align["meter_from_model"]["scale"]) if align is not None else None

        t0 = time.perf_counter()
        scores = self.db_global @ desc
        full_order = np.argsort(-scores)
        prior_used = False
        outside_prior = False
        deep_search = False

        if prior_xy is not None and align is not None:
            prior_used = True
            radius = clamp_prior_radius(prior_radius_m)
            eligible = filter_prior_indices(
                [self._db_center(n) for n in self.db_names], align, prior_xy, radius
            )
            eligible_set = set(eligible)
            order = np.array(
                [i for i in full_order if int(i) in eligible_set][: self.k], dtype=np.intp
            )
        else:
            order = full_order[: min(self.k, len(self.db_names))]
        t["retrieval"] = time.perf_counter() - t0

        q_kp_t, q_desc_t = self._t(kp), self._t(q_desc)
        match_cache: dict[str, np.ndarray] = {}
        attempt = self._run_pnp_attempt(
            order, scores, kp, q_kp_t, q_desc_t, size, camera, align_scale, match_cache
        )
        t["match"] = attempt[9]
        t["pose"] = attempt[10]

        if not attempt[0]:
            if prior_used:
                t_fb = time.perf_counter()
                order_all = full_order[: min(self.k, len(self.db_names))]
                attempt = self._run_pnp_attempt(
                    order_all, scores, kp, q_kp_t, q_desc_t, size, camera, align_scale, match_cache
                )
                t["prior_fallback"] = time.perf_counter() - t_fb
                outside_prior = True
            elif prior_xy is None and DEEP_SEARCH_K > self.k and len(self.db_names) > self.k:
                t_ds = time.perf_counter()
                order_deep = full_order[: min(DEEP_SEARCH_K, len(self.db_names))]
                attempt = self._run_pnp_attempt(
                    order_deep,
                    scores,
                    kp,
                    q_kp_t,
                    q_desc_t,
                    size,
                    camera,
                    align_scale,
                    match_cache,
                )
                t["deep_search"] = time.perf_counter() - t_ds
                deep_search = True

        t["total"] = sum(t.values())
        (
            ok,
            inliers,
            correspondences,
            pose,
            center,
            inlier_ratio,
            reproj_median,
            retrieval_top1,
            ambiguous,
            _,
            _,
        ) = attempt
        return Result(
            ok,
            inliers,
            correspondences,
            pose,
            center,
            t,
            inlier_ratio=inlier_ratio,
            reprojection_error_px_median=reproj_median,
            retrieval_top1=retrieval_top1,
            ambiguous=ambiguous,
            prior_used=prior_used,
            outside_prior=outside_prior,
            deep_search=deep_search,
        )

    @torch.inference_mode()
    def localize(
        self,
        image: np.ndarray,
        camera: pycolmap.Camera,
        *,
        prior_xy: tuple[float, float] | None = None,
        prior_radius_m: float | None = None,
    ) -> Result:
        """image: RGB float32 (H, W, 3), sudah tegak. camera: intrinsik foto itu."""
        t = {}  # tiap tahap diakhiri .cpu().numpy() yang menunggu GPU, jadi waktu CUDA tetap sah

        t0 = time.perf_counter()
        img_g, _ = self._prep(image, self.global_resize)
        img_l, size = self._prep(image, self.resize)
        t["prep"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        desc = half(self.megaloc({"image": img_g})["global_descriptor"][0].cpu().numpy())
        t["global"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        pred = self.aliked({"image": img_l})
        kp = pred["keypoints"][0].cpu().numpy()
        scales = (size / np.array(img_l.shape[-2:][::-1])).astype(np.float32)
        kp = half((kp + 0.5) * scales[None] - 0.5)
        q_desc = half(pred["descriptors"][0].cpu().numpy())
        t["local"] = time.perf_counter() - t0

        return self._localize_from_features(
            desc,
            kp,
            q_desc,
            size,
            camera,
            t_init=t,
            prior_xy=prior_xy,
            prior_radius_m=prior_radius_m,
        )

    @torch.inference_mode()
    def localize_batch(
        self,
        images: list[np.ndarray],
        cameras: list[pycolmap.Camera],
        *,
        prior_xy: tuple[float, float] | None = None,
        prior_radius_m: float | None = None,
    ) -> list[Result]:
        """Lokalisasi beberapa frame sekaligus: ekstraksi MegaLoc dan ALIKED digabung per ukuran."""
        if len(images) != len(cameras):
            raise ValueError("jumlah gambar dan kamera harus sama")
        if not images:
            return []

        n = len(images)
        t0 = time.perf_counter()
        prepped_g, prepped_l, sizes = [], [], []
        for img in images:
            ig, _ = self._prep(img, self.global_resize)
            il, sz = self._prep(img, self.resize)
            prepped_g.append(ig)
            prepped_l.append(il)
            sizes.append(sz)
        prep_per = (time.perf_counter() - t0) / n

        t0 = time.perf_counter()
        descs: list[np.ndarray | None] = [None] * n
        groups_g: dict[tuple[int, int], list[int]] = defaultdict(list)
        for idx, ig in enumerate(prepped_g):
            groups_g[(ig.shape[-2], ig.shape[-1])].append(idx)
        for idxs in groups_g.values():
            batch_g = torch.cat([prepped_g[i] for i in idxs], dim=0)
            out_g = self.megaloc({"image": batch_g})["global_descriptor"].cpu().numpy()
            for pos, i in enumerate(idxs):
                descs[i] = half(out_g[pos])
        global_per = (time.perf_counter() - t0) / n

        t0 = time.perf_counter()
        kps: list[np.ndarray | None] = [None] * n
        q_descs: list[np.ndarray | None] = [None] * n
        groups_l: dict[tuple[int, int], list[int]] = defaultdict(list)
        for idx, il in enumerate(prepped_l):
            groups_l[(il.shape[-2], il.shape[-1])].append(idx)
        for idxs in groups_l.values():
            batch_l = torch.cat([prepped_l[i] for i in idxs], dim=0)
            pred = self.aliked({"image": batch_l})
            h_l, w_l = batch_l.shape[-2], batch_l.shape[-1]
            for pos, i in enumerate(idxs):
                kp = pred["keypoints"][pos].cpu().numpy()
                scales = (sizes[i] / np.array([w_l, h_l])).astype(np.float32)
                kps[i] = half((kp + 0.5) * scales[None] - 0.5)
                q_descs[i] = half(pred["descriptors"][pos].cpu().numpy())
        local_per = (time.perf_counter() - t0) / n

        results = []
        for i in range(n):
            results.append(
                self._localize_from_features(
                    descs[i],
                    kps[i],
                    q_descs[i],
                    sizes[i],
                    cameras[i],
                    t_init={"prep": prep_per, "global": global_per, "local": local_per},
                    prior_xy=prior_xy,
                    prior_radius_m=prior_radius_m,
                )
            )
        return results

    def to_building(self, cam_from_world: pycolmap.Rigid3d):
        """Pose kamera di kerangka gedung (meter) lewat align.json, atau None kalau belum ada."""
        align = self.align
        if align is None:
            return None
        sim = sim3.from_align(align["meter_from_model"])
        world_from_cam = cam_from_world.inverse()
        position = (sim * world_from_cam.translation[None])[0]
        rotation = sim.rotation * world_from_cam.rotation
        return position.tolist(), rotation.quat.tolist()
