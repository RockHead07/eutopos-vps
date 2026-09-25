"""Ukur waktu ALIKED + LightGlue per foto dan per pasangan, model hangat, per batas keypoint.

    python spike/bench_matching.py data/demo/mapping --kp 512 1024 2048 -1

Memakai paket lightglue langsung (bukan DataLoader hloc) supaya yang terukur hanya komputasinya.
"""

import argparse
import statistics
import time
from itertools import combinations
from pathlib import Path

import torch
from lightglue import ALIKED, LightGlue
from lightglue.utils import load_image, rbd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", type=Path)
    ap.add_argument("--kp", type=int, nargs="+", default=[512, 1024, 2048, -1])
    ap.add_argument("--resize", type=int, default=1024)  # sama dengan konfigurasi hloc aliked-n16
    ap.add_argument("--pairs", type=int, default=8)
    a = ap.parse_args()

    paths = sorted(p for p in a.images.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    imgs = [load_image(p, resize=a.resize) for p in paths]
    pairs = list(combinations(range(len(imgs)), 2))[: a.pairs]
    matcher = LightGlue(features="aliked").eval()
    print(
        f"torch {torch.__version__}, threads {torch.get_num_threads()}, "
        f"{len(imgs)} foto, {len(pairs)} pasangan, resize {a.resize}"
    )

    with torch.inference_mode():
        for kp in a.kp:
            ext = ALIKED(max_num_keypoints=kp).eval()  # -1 = tanpa batas
            ext.extract(imgs[0])  # pemanasan
            t_ext, feats = [], []
            for im in imgs:
                t0 = time.perf_counter()
                feats.append(ext.extract(im))
                t_ext.append(time.perf_counter() - t0)
            matcher({"image0": feats[0], "image1": feats[1]})  # pemanasan
            t_match, n_match = [], []
            for i, j in pairs:
                t0 = time.perf_counter()
                out = rbd(matcher({"image0": feats[i], "image1": feats[j]}))
                t_match.append(time.perf_counter() - t0)
                n_match.append(len(out["matches"]))
            n_kp = statistics.mean(f["keypoints"].shape[1] for f in feats)
            print(
                f"kp={'tanpa batas' if kp < 0 else kp:>11} | rata2 keypoint {n_kp:7.0f} | "
                f"ekstraksi {statistics.median(t_ext):6.2f} s/foto | "
                f"pencocokan {statistics.median(t_match):6.2f} s/pasangan | "
                f"rata2 match {statistics.mean(n_match):6.0f}"
            )


if __name__ == "__main__":
    main()
