"""Pratinjau sebuah job: frame pertama video peta, diperkecil, disimpan di folder petanya.

Folder peta dipilih karena container api hanya bisa membaca /maps (tidak /data/jobs), dan karena
penghapusan job membuang folder itu sekaligus. Pratinjau tidak boleh menggagalkan job: semua galat
dibuat jadi False.
"""

import glob
from pathlib import Path

WIDTH = 640
QUALITY = 80


def first_frame(mapping: Path, videos: list[dict]) -> Path | None:
    """Frame pertama dari video peta pertama. Nama frame: <nama berkas video>_<5 digit>.jpg."""
    for v in videos:
        if v.get("role") == "peta" and v.get("path"):
            stem = glob.escape(Path(v["path"]).stem)
            found = sorted(mapping.glob(f"{stem}_[0-9][0-9][0-9][0-9][0-9].jpg"))
            if found:
                return found[0]
    return min(mapping.glob("*.jpg"), default=None)


def make_preview(mapping: Path, videos: list[dict], out: Path) -> bool:
    """Tulis `out` (JPEG, lebar maksimal 640 px). False kalau tidak ada frame atau gagal."""
    import cv2  # impor tertunda: hanya pekerja dan perintah pengisian ulang yang butuh

    try:
        src = first_frame(mapping, videos)
        img = cv2.imread(str(src)) if src else None
        if img is None:
            return False
        h, w = img.shape[:2]
        if w > WIDTH:
            img = cv2.resize(img, (WIDTH, round(h * WIDTH / w)), interpolation=cv2.INTER_AREA)
        # Ditulis ke berkas sementara lalu diganti: yang dibaca api tidak pernah setengah jadi.
        tmp = out.with_name("preview.tmp.jpg")
        if not cv2.imwrite(str(tmp), img, [cv2.IMWRITE_JPEG_QUALITY, QUALITY]):
            return False
        tmp.replace(out)
        return True
    except Exception:
        return False
