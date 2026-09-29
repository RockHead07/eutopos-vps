"""Ambil frame dari video capture menjadi foto peta, satu frame tertajam per jendela waktu.

Tutorial COLMAP menyarankan menjarangkan frame video: frame yang terlalu rapat tidak menambah
informasi, hanya memperlama rekonstruksi. Dari setiap jendela (1/--fps detik) dipilih frame dengan
variansi Laplacian tertinggi, ukuran ketajaman standar, supaya frame yang buram karena gerak tidak
ikut.

Syarat video: lanskap, lensa 1x, stabilisasi video DIMATIKAN (stabilisasi elektronik memotong dan
membengkokkan tiap frame secara berbeda, sehingga intrinsik kamera tidak lagi sama untuk semua
frame), HDR video mati, berjalan pelan.

Contoh (satu video per putaran):
    python spike/extract_frames.py video1.mp4 video2.mp4 --out data/floor10/mapping
    python spike/extract_frames.py --self-test
"""

import argparse
import statistics
import tempfile
from pathlib import Path

import cv2
import numpy as np


def sharpness(frame) -> float:
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    s = 640 / max(g.shape)  # ponytail: diukur di resolusi kecil, cukup untuk membandingkan
    if s < 1:
        g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def extract(video: Path, out: Path, fps: float):
    """Tulis frame terpilih ke out/<nama video>_<nomor>.jpg -> [(indeks frame, ketajaman)]."""
    cap = cv2.VideoCapture(str(video))  # OpenCV memutar frame sesuai metadata rotasi video
    if not cap.isOpened():
        raise SystemExit(f"tidak bisa membuka {video}")
    win = max(1, round((cap.get(cv2.CAP_PROP_FPS) or 30) / fps))
    chosen, best, i = [], None, 0

    def flush():
        idx, score, frame = best
        cv2.imwrite(
            str(out / f"{video.stem}_{len(chosen):05d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]
        )
        chosen.append((idx, score))

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        score = sharpness(frame)
        if best is None or score > best[1]:
            best = (i, score, frame)
        i += 1
        if i % win == 0:
            flush()
            best = None
    if best is not None:
        flush()
    cap.release()
    return chosen


def self_test():
    """Video sintetis bergeser pelan; di tiap jendela hanya satu frame yang tidak diburamkan."""
    rng = np.random.default_rng(0)
    scene = cv2.GaussianBlur(rng.integers(0, 255, (600, 900, 3), dtype=np.uint8), (0, 0), 1.5)
    sharp = {3, 20, 44, 50}  # satu per jendela 15 frame (30 fps -> 2 fps)
    with tempfile.TemporaryDirectory() as d:
        video, out = Path(d) / "uji.mp4", Path(d) / "mapping"
        out.mkdir()
        vw = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30, (640, 480))
        for i in range(60):
            f = scene[40 : 40 + 480, 2 * i : 2 * i + 640]
            vw.write(f if i in sharp else cv2.GaussianBlur(f, (0, 0), 3))
        vw.release()
        chosen = extract(video, out, 2.0)
        assert [c[0] for c in chosen] == sorted(sharp), chosen
        assert len(list(out.glob("*.jpg"))) == 4
    print("self-test OK", chosen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", type=Path, nargs="*")
    ap.add_argument("--out", type=Path, help="folder mapping/ tujuan")
    ap.add_argument("--fps", type=float, default=2.0, help="frame per detik yang diambil")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not (a.videos and a.out):
        ap.error("butuh video dan --out, atau --self-test")

    a.out.mkdir(parents=True, exist_ok=True)
    for v in a.videos:
        chosen = extract(v, a.out, a.fps)
        scores = [s for _, s in chosen]
        med = statistics.median(scores) if scores else 0
        blur = sum(s < 0.3 * med for s in scores)
        # frame buram tetap disimpan supaya rantai foto tidak putus; ulangi putaran kalau banyak
        print(f"{v.name}: {len(chosen)} frame, ketajaman median {med:.0f}, {blur} jauh lebih buram")


if __name__ == "__main__":
    main()
