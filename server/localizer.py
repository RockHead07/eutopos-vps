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

MEGALOC = extract_features.confs["megaloc"]
ALIKED = extract_features.confs["aliked-n16"]
LIGHTGLUE = match_features.confs["aliked+lightglue"]


def half(x):
    # hloc menyimpan fitur sebagai float16 (as_half=True); tiru agar hasilnya setara
    return x.astype(np.float16).astype(np.float32)


@dataclass
class Result:
    ok: bool
    inliers: int
    correspondences: int
    cam_from_world: pycolmap.Rigid3d | None  # kerangka model SfM
    center_model: list[float] | None
    t: dict[str, float] = field(default_factory=dict)


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
    ):
        self.dev = torch.device(device)
        self.resize, self.global_resize, self.k = resize, global_resize, k
        self.min_inliers = min_inliers
        aliked = {**ALIKED, "model": {**ALIKED["model"], "max_num_keypoints": max_kp}}

        t0 = time.perf_counter()
        self.megaloc = self._load(extractors, MEGALOC)
        self.aliked = self._load(extractors, aliked)
        self.lightglue = self._load(matchers, LIGHTGLUE)
        self.t_load_models = time.perf_counter() - t0

        t0 = time.perf_counter()
        run_dir = map_dir / f"kp{max_kp}-r{resize}"
        self.model = pycolmap.Reconstruction(run_dir / "sfm")
        self.db = self._load_db(run_dir / "features.h5", map_dir / f"global-r{global_resize}.h5")
        self.db_names = list(self.db)
        self.db_global = np.stack([self.db[n]["global"] for n in self.db_names])
        self.map_camera = next(iter(self.model.cameras.values()))
        self.pnp = QueryLocalizer(self.model, {"estimation": {"ransac": {"max_error": 12}}})
        align = run_dir / "align.json"  # ditulis spike/eval_meter.py, kalau titik acuan sudah ada
        self.align = json.loads(align.read_text(encoding="utf-8")) if align.exists() else None
        self.t_load_map = time.perf_counter() - t0

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
                    "points3D_ids": np.array(
                        [p.point3D_id if p.has_point3D() else -1 for p in image.points2D]
                    ),
                }
        return db

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

    @torch.inference_mode()
    def localize(self, image: np.ndarray, camera: pycolmap.Camera) -> Result:
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
        order = np.argsort(-(self.db_global @ desc))[: min(self.k, len(self.db_names))]
        cand = [self.db_names[i] for i in order]
        t["retrieval"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        pred = self.aliked({"image": img_l})
        kp = pred["keypoints"][0].cpu().numpy()
        scales = (size / np.array(img_l.shape[-2:][::-1])).astype(np.float32)
        kp = half((kp + 0.5) * scales[None] - 0.5)
        q_desc = half(pred["descriptors"][0].cpu().numpy())
        t["local"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        kp_idx_to_3D = defaultdict(list)
        q_kp_t, q_desc_t = self._t(kp), self._t(q_desc)
        for name in cand:
            d = self.db[name]
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
            for qi, mi in matches:
                id3 = d["points3D_ids"][mi]
                if id3 not in kp_idx_to_3D[qi]:
                    kp_idx_to_3D[qi].append(id3)
        t["match"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        idxs = list(kp_idx_to_3D.keys())
        mkp = [i for i in idxs for _ in kp_idx_to_3D[i]]
        mp3d = [j for i in idxs for j in kp_idx_to_3D[i]]
        ret = self.pnp.localize(kp + 0.5, mkp, mp3d, camera)  # +0.5: koordinat COLMAP
        t["pose"] = time.perf_counter() - t0
        t["total"] = sum(t.values())

        inliers = int(ret["num_inliers"]) if ret else 0
        # Inlier rendah = pose tak bisa dipercaya: foto potret miring di spike tetap menghasilkan
        # pose dengan 8 sampai 14 inlier, salah tapi yakin.
        if ret is None or inliers < self.min_inliers:
            return Result(False, inliers, len(mp3d), None, None, t)
        pose = ret["cam_from_world"]
        return Result(True, inliers, len(mp3d), pose, pose.inverse().translation.tolist(), t)

    def to_building(self, cam_from_world: pycolmap.Rigid3d):
        """Pose kamera di kerangka gedung (meter) lewat align.json, atau None kalau belum ada."""
        if self.align is None:
            return None
        m = self.align["meter_from_model"]
        sim = pycolmap.Sim3d(
            m["scale"],
            pycolmap.Rotation3d(np.array(m["rotation_xyzw"])),
            np.array(m["translation"]),
        )
        world_from_cam = cam_from_world.inverse()
        position = (sim * world_from_cam.translation[None])[0]
        rotation = sim.rotation * world_from_cam.rotation
        return position.tolist(), rotation.quat.tolist()
