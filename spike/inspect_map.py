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
    python spike/inspect_map.py outputs/floor10-v1/kp1024-r1024 --html outputs/floor10-v1/map.html
    python spike/inspect_map.py outputs/floor10-v1/kp1024-r1024 --json outputs/floor10-v1/i.json
    python spike/inspect_map.py --self-test
"""

import argparse
import csv
import itertools
import json
import os
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
    ap.add_argument("--html", type=Path, help="simpan tampilan 3D peta utama dan posisi query")
    ap.add_argument("--json", type=Path, help="simpan ringkasan potongan dan query")
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
    step = main_model = None
    part_rows = []
    for label, d in parts:
        model = pycolmap.Reconstruction(d)
        if label == "utama":
            main_model = model
        c = centers(model)
        ids = sorted(c)
        steps = [np.linalg.norm(c[j] - c[i]) for i, j in itertools.pairwise(ids) if j == i + 1]
        med = float(np.median(steps)) if steps else float("nan")
        step = med if label == "utama" else step
        print(f"{label}: {len(ids)} frame, rentang {ranges(ids)}, langkah median {med:.3f}")
        part_rows.append({"label": label, "frames": len(ids), "ranges": ranges(ids)})

    print(f"\n== query terhadap peta utama (layanan menolak di bawah {MIN_INLIERS} inlier) ==")
    prev, accepted, rows, located = None, 0, 0, []
    results = a.run_dir / "results.csv"  # tidak ada kalau peta dibangun tanpa foto uji
    with open(results if results.exists() else os.devnull, encoding="utf-8") as f:
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
            located.append((n, c, inl))
    print(f"\nditerima layanan: {accepted}/{rows} query")
    if a.json:
        summary = {"parts": part_rows, "queries": rows, "accepted": accepted}
        a.json.write_text(json.dumps({**summary, "min_inliers": MIN_INLIERS}), encoding="utf-8")
    if a.html:
        save_html(a.html, main_model, located)


def save_html(path: Path, model, located):
    # Potongan lain punya kerangka koordinat sendiri, jadi hanya potongan utama yang digambar.
    import plotly.graph_objects as go
    from hloc.utils import viz_3d

    fig = viz_3d.init_figure()
    viz_3d.plot_reconstruction(fig, model, color="rgba(60,110,255,0.5)", name="peta utama")
    for name, color, keep in [
        (f"query diterima (>= {MIN_INLIERS} inlier)", "rgb(20,160,60)", True),
        ("query ditolak", "rgb(230,90,20)", False),
    ]:
        sel = [(n, c, inl) for n, c, inl in located if (inl >= MIN_INLIERS) == keep]
        if not sel:
            continue
        xyz = np.array([c for _, c, _ in sel])
        fig.add_trace(
            go.Scatter3d(
                x=xyz[:, 0],
                y=xyz[:, 1],
                z=xyz[:, 2],
                mode="markers+text",
                text=[str(n) for n, _, _ in sel],
                hovertext=[f"query {n}: {inl} inlier" for n, _, inl in sel],
                marker={"size": 5, "color": color},
                name=name,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(path)  # plotly.js ikut di dalam berkas, bisa dibuka tanpa internet
    print(f"tampilan 3D: {path}")


if __name__ == "__main__":
    main()
