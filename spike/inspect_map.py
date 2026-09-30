"""Periksa hasil run.py untuk peta dari video: di mana peta putus, dan apakah pose query masuk akal.

Tanpa titik acuan meter pun, dua hal ini sudah terlihat:
1. Potongan peta. COLMAP bisa menghasilkan beberapa model terpisah. run.py hanya memakai yang
   terbesar (sfm/), sisanya di sfm/models/<n>/. Rentang nomor frame per potongan menunjukkan di
   detik berapa video putus (nomor frame / fps ekstraksi).
2. Lompatan query. Frame query diambil berurutan dari video yang direkam sambil berjalan, jadi
   posisi yang meloncat jauh dari query sebelumnya hampir pasti pose salah. Satuannya
   "langkah peta", median jarak antar-frame peta berurutan, karena skala model SfM belum meter.

Contoh:
    python spike/inspect_map.py outputs/floor10-v1/kp1024-r1024
    python spike/inspect_map.py --self-test
"""

import argparse
import csv
import itertools
import json
import re
import sys
from pathlib import Path

import numpy as np
import pycolmap

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # akar repo, untuk paket server
from server.localizer import MIN_INLIERS


def frame_no(name: str) -> int:
    return int(re.findall(r"\d+", Path(name).stem)[-1])


def ranges(ids: list[int]) -> list[str]:
    runs = [[ids[0]]]
    for i in ids[1:]:
        if i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    return [f"{r[0]}-{r[-1]}" if len(r) > 1 else f"{r[0]}" for r in runs]


def centers(model) -> dict[int, np.ndarray]:
    return {
        frame_no(im.name): im.cam_from_world().inverse().translation for im in model.images.values()
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path, nargs="?", help="folder kp*-r* keluaran run.py")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        assert frame_no("mapping/video1_LabHallDemo_00073.jpg") == 73
        assert ranges([0, 1, 2, 5, 7, 8]) == ["0-2", "5", "7-8"]
        assert ranges([4]) == ["4"]
        print("self-test ok")
        return

    sfm = a.run_dir / "sfm"
    parts = [("utama", sfm)] + [
        (d.name, d) for d in sorted((sfm / "models").iterdir()) if (d / "images.bin").exists()
    ]
    print("== potongan peta (nomor frame) ==")
    step = None
    for label, d in parts:
        c = centers(pycolmap.Reconstruction(d))
        ids = sorted(c)
        steps = [np.linalg.norm(c[j] - c[i]) for i, j in itertools.pairwise(ids) if j == i + 1]
        med = float(np.median(steps)) if steps else float("nan")
        step = med if label == "utama" else step
        print(f"{label}: {len(ids)} frame, rentang {ranges(ids)}, langkah median {med:.3f}")

    print(f"\n== query terhadap peta utama (layanan menolak di bawah {MIN_INLIERS} inlier) ==")
    prev, accepted, rows = None, 0, 0
    with open(a.run_dir / "results.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows += 1
            n = frame_no(r["query"])
            if r["ok"] != "True":
                print(f"{n:4d}  GAGAL")
                continue
            inl, c = int(r["inliers"]), np.array(json.loads(r["center_xyz_model"]))
            accepted += inl >= MIN_INLIERS
            jump = "" if prev is None else f"  loncat {np.linalg.norm(c - prev[1]) / step:6.1f}x"
            mark = "" if inl >= MIN_INLIERS else "  ditolak"
            print(f"{n:4d}  inlier {inl:4d}/{int(r['correspondences']):4d}{jump}{mark}")
            prev = (n, c)
    print(f"\nditerima layanan: {accepted}/{rows} query")


if __name__ == "__main__":
    main()
