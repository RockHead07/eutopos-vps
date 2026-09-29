"""Ukur latensi lokalisasi satu foto dalam satu proses hangat, per tahap.

Semua model dan data peta dimuat sekali, seperti layanan /localize nanti. Tiap foto uji lalu
dilokalisasi dari awal sampai akhir: baca foto, deskriptor global (MegaLoc), retrieval, fitur lokal
(ALIKED), pencocokan (LightGlue) ke k kandidat, lalu PnP.

Butuh peta hasil spike/run.py dengan retrieval (ada global-r<R>.h5):
    python spike/run.py data/demo --out outputs/retrieval-test --exhaustive-max 0
    python spike/bench_localize.py data/demo --map outputs/retrieval-test --k 5 --threads 2
    python spike/bench_localize.py data/demo --map outputs/retrieval-test --k 5 --device cuda

Logika korespondensi 2D-3D mengikuti hloc.localize_sfm.pose_from_cluster (commit c13273b), tapi di
memori, tanpa berkas .h5 per permintaan.
"""

import argparse
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

import h5py
import numpy as np
import pycolmap
import torch
from env_info import env
from hloc import extract_features, extractors, match_features, matchers
from hloc.extract_features import resize_image
from hloc.localize_sfm import QueryLocalizer
from hloc.utils.base_model import dynamic_load
from hloc.utils.io import read_image

MEGALOC = extract_features.confs["megaloc"]
ALIKED = extract_features.confs["aliked-n16"]
LIGHTGLUE = match_features.confs["aliked+lightglue"]
DEV = torch.device("cpu")  # diatur --device di main()


def load_model(pkg, conf):
    return dynamic_load(pkg, conf["model"]["name"])(conf["model"]).eval().to(DEV)


def preprocess(path: Path, resize_max: int):
    """Sama dengan hloc ImageDataset: RGB float, sisi terpanjang <= resize_max, skala 0..1."""
    image = read_image(path, False).astype(np.float32)
    size = image.shape[:2][::-1]
    if max(size) > resize_max:
        scale = resize_max / max(size)
        image = resize_image(image, tuple(round(x * scale) for x in size), "cv2_area")
    tensor = torch.from_numpy(image.transpose((2, 0, 1)) / 255.0)[None].to(DEV)
    return tensor, np.array(size)


def half(x):
    # hloc menyimpan fitur sebagai float16 (as_half=True); tiru agar hasilnya setara
    return x.astype(np.float16).astype(np.float32)


def load_map(global_h5: Path, run_dir: Path):
    model = pycolmap.Reconstruction(run_dir / "sfm")
    db = {}
    with h5py.File(run_dir / "features.h5", "r") as fl, h5py.File(global_h5, "r") as fg:
        for image_id, image in model.images.items():
            g = fl[image.name]
            db[image.name] = {
                "id": image_id,
                "keypoints": torch.from_numpy(g["keypoints"].__array__()).float()[None].to(DEV),
                "descriptors": torch.from_numpy(g["descriptors"].__array__()).float()[None].to(DEV),
                "size": tuple(g["image_size"].__array__()),
                "global": fg[image.name]["global_descriptor"].__array__().astype(np.float32),
                "points3D_ids": np.array(
                    [p.point3D_id if p.has_point3D() else -1 for p in image.points2D]
                ),
            }
    return model, db


def localize(q_path, models, model, db, db_names, db_global, camera, localizer, k, resize):
    megaloc, aliked, lightglue, _ = models
    t = {}  # tiap tahap diakhiri .cpu().numpy() yang menunggu GPU, jadi waktu CUDA tetap sah

    t0 = time.perf_counter()
    img_g, _ = preprocess(q_path, models[3])
    img_l, size = preprocess(q_path, resize)
    t["read"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    desc = half(megaloc({"image": img_g})["global_descriptor"][0].cpu().numpy())
    t["global"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    sim = db_global @ desc
    cand = [db_names[i] for i in np.argsort(-sim)[: min(k, len(db_names))]]
    t["retrieval"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    pred = aliked({"image": img_l})
    kp = pred["keypoints"][0].cpu().numpy()
    scales = (size / np.array(img_l.shape[-2:][::-1])).astype(np.float32)
    kp = half((kp + 0.5) * scales[None] - 0.5)
    q_desc = half(pred["descriptors"][0].cpu().numpy())
    t["local"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    kp_idx_to_3D = defaultdict(list)
    q_kp_t = torch.from_numpy(kp)[None].to(DEV)
    q_desc_t = torch.from_numpy(q_desc)[None].to(DEV)
    for name in cand:
        d = db[name]
        out = lightglue(
            {
                "image0": torch.empty((1, 1, *size[::-1]), device=DEV),
                "keypoints0": q_kp_t,
                "descriptors0": q_desc_t,
                "image1": torch.empty((1, 1, *d["size"][::-1]), device=DEV),
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
    ret = localizer.localize(kp + 0.5, mkp, mp3d, camera)  # +0.5: koordinat COLMAP
    t["pose"] = time.perf_counter() - t0

    t["total"] = sum(t.values())
    inliers = int(ret["num_inliers"]) if ret else 0
    center = ret["cam_from_world"].inverse().translation.tolist() if ret else None
    return t, inliers, len(mp3d), center


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path, help="folder berisi query/")
    ap.add_argument("--map", type=Path, required=True, help="--out dari run.py")
    ap.add_argument("--max-kp", type=int, default=1024)
    ap.add_argument("--resize", type=int, default=1024)
    ap.add_argument("--global-resize", type=int, default=1024, help="sisi terpanjang untuk MegaLoc")
    ap.add_argument("--k", type=int, default=5, help="jumlah kandidat foto peta per query")
    ap.add_argument("--repeat", type=int, default=3, help="ulangan per query, dilaporkan median")
    ap.add_argument("--threads", type=int, default=0, help="batasi thread torch (0 = bawaan)")
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cpu", help="perangkat inferensi")
    a = ap.parse_args()

    global DEV
    DEV = torch.device(a.device)
    if a.threads:
        torch.set_num_threads(a.threads)
    run_dir = a.map / f"kp{a.max_kp}-r{a.resize}"
    aliked_conf = {**ALIKED, "model": {**ALIKED["model"], "max_num_keypoints": a.max_kp}}

    t0 = time.perf_counter()
    models = (
        load_model(extractors, MEGALOC),
        load_model(extractors, aliked_conf),
        load_model(matchers, LIGHTGLUE),
        a.global_resize,
    )
    t_models = time.perf_counter() - t0
    t0 = time.perf_counter()
    model, db = load_map(a.map / f"global-r{a.global_resize}.h5", run_dir)
    t_map = time.perf_counter() - t0

    db_names = list(db)
    db_global = np.stack([db[n]["global"] for n in db_names])
    map_cam = next(iter(model.cameras.values()))
    localizer = QueryLocalizer(model, {"estimation": {"ransac": {"max_error": 12}}})
    queries = sorted(
        p for p in (a.dataset / "query").iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )

    results = []
    with torch.inference_mode():
        for q in queries:
            cam = pycolmap.infer_camera_from_image(q)
            if (cam.width, cam.height) == (map_cam.width, map_cam.height):
                cam = map_cam
            args = (q, models, model, db, db_names, db_global, cam, localizer, a.k, a.resize)
            localize(*args)  # pemanasan, tidak dihitung
            runs = [localize(*args) for _ in range(a.repeat)]
            med = {s: round(statistics.median(r[0][s] for r in runs), 3) for s in runs[0][0]}
            results.append(
                {
                    "query": q.name,
                    "inliers": runs[-1][1],
                    "correspondences": runs[-1][2],
                    "ok": runs[-1][1] > 0,
                    "t_median_s": med,
                    "center_xyz_model": runs[-1][3],
                }
            )

    summary = {
        "device": torch.cuda.get_device_name(0) if a.device == "cuda" else "cpu",
        "threads": torch.get_num_threads(),
        "max_keypoints": a.max_kp,
        "resize_max": a.resize,
        "global_resize_max": a.global_resize,
        "k": a.k,
        "repeat": a.repeat,
        "map_images": len(db_names),
        "t_load_models_s": round(t_models, 2),
        "t_load_map_s": round(t_map, 2),
        "queries": results,
        "env": env(),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
