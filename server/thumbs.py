"""Foto kecil frame scan untuk "foto asli" di halaman area (spesifikasi 2026-10-21 bagian 5d).

Dibuat pekerja ke <map_dir>/thumbs/ karena container api tidak memasang /data/jobs. cv2.imwrite
tidak menyalin EXIF, jadi foto interior gedung tidak membawa metadata ponsel.
"""

from pathlib import Path

import cv2

WIDTH = 480
QUALITY = 80


def make_thumbs(mapping_dir: Path, out_dir: Path, width: int = WIDTH) -> int:
    """Foto kecil (nama sama dengan frame) untuk semua frame; mengembalikan jumlah yang dibuat."""
    frames = sorted(mapping_dir.glob("*.jpg")) if mapping_dir.is_dir() else []
    if not frames:
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    for f in frames:
        img = cv2.imread(str(f))
        if img is None:
            continue
        h, w = img.shape[:2]
        small = cv2.resize(img, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
        if cv2.imwrite(str(out_dir / f.name), small, [cv2.IMWRITE_JPEG_QUALITY, QUALITY]):
            made += 1
    return made
