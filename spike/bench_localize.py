"""Ukur latensi lokalisasi satu foto dalam satu proses hangat, per tahap.

Memakai kode yang sama dengan layanan (server/localizer.py): model dan data peta dimuat sekali,
lalu tiap foto uji dilokalisasi dari awal sampai akhir. Tahap: baca berkas, praproses, deskriptor
global (MegaLoc), retrieval, fitur lokal (ALIKED), pencocokan (LightGlue) ke k kandidat, lalu PnP.

Butuh peta hasil spike/run.py dengan retrieval (ada global-r<R>.h5):
    python spike/run.py data/demo --out outputs/retrieval-test --exhaustive-max 0
    python spike/bench_localize.py data/demo --map outputs/retrieval-test --k 5 --threads 2
    python spike/bench_localize.py data/demo --map outputs/retrieval-test --k 5 --device cuda
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pycolmap
import torch
from env_info import env
from hloc.utils.io import read_image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # akar repo, untuk paket server
from server.localizer import Localizer


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

    if a.threads:
        torch.set_num_threads(a.threads)
    loc = Localizer(
        a.map,
        max_kp=a.max_kp,
        resize=a.resize,
        global_resize=a.global_resize,
        k=a.k,
        device=a.device,
    )
    queries = sorted(
        p for p in (a.dataset / "query").iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )

    def run(q: Path, cam: pycolmap.Camera):
        t0 = time.perf_counter()
        image = read_image(q, False).astype(np.float32)
        read = time.perf_counter() - t0
        r = loc.localize(image, cam)
        t = {"read": read, **r.t}
        t["total"] += read
        return t, r

    results = []
    for q in queries:
        cam = pycolmap.infer_camera_from_image(q)
        if loc.same_size_as_map(cam.width, cam.height):
            cam = loc.map_camera
        run(q, cam)  # pemanasan, tidak dihitung
        runs = [run(q, cam) for _ in range(a.repeat)]
        med = {s: round(statistics.median(t[s] for t, _ in runs), 3) for s in runs[0][0]}
        last = runs[-1][1]
        results.append(
            {
                "query": q.name,
                "inliers": last.inliers,
                "correspondences": last.correspondences,
                "ok": last.ok,
                "t_median_s": med,
                "center_xyz_model": last.center_model,
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
        "map_images": len(loc.db_names),
        "t_load_models_s": round(loc.t_load_models, 2),
        "t_load_map_s": round(loc.t_load_map, 2),
        "queries": results,
        "env": env(),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
