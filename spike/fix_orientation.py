"""Salin dataset foto sambil memutar piksel sesuai tag rotasi EXIF.

Ponsel menyimpan foto potret sebagai piksel mentah yang miring 90 derajat plus tag EXIF Orientation.
hloc membaca foto dengan cv2.IMREAD_IGNORE_ORIENTATION, jadi foto itu diproses dalam keadaan miring,
dan ALIKED + LightGlue tidak tahan rotasi 90 derajat: hasilnya pose yang salah tapi yakin
(docs/spike-plan.md). Skrip ini menulis salinan yang pikselnya sudah tegak, tanpa tag rotasi.
Tag EXIF lain (termasuk focal length untuk intrinsik awal) dipertahankan.

Contoh:
    python spike/fix_orientation.py data/room-rehearsal data/room-rehearsal-upright
    python spike/run.py data/room-rehearsal-upright --out outputs/room-rehearsal
"""

import argparse
import shutil
from pathlib import Path

from PIL import Image, ImageOps

ORIENTATION = 0x0112
EXTS = {".jpg", ".jpeg", ".png"}


def orientation(path: Path) -> int:
    with Image.open(path) as im:
        return im.getexif().get(ORIENTATION, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    a = ap.parse_args()
    if a.dst.exists():
        raise SystemExit(f"{a.dst} sudah ada; hapus dulu supaya tidak tercampur")

    n_rot = 0
    for p in sorted(a.src.rglob("*")):
        if not p.is_file():
            continue
        out = a.dst / p.relative_to(a.src)
        out.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() not in EXTS or orientation(p) == 1:
            shutil.copy2(p, out)  # tanpa encode ulang
            continue
        with Image.open(p) as im:
            up = ImageOps.exif_transpose(im)  # memutar piksel dan membuang tag Orientation
            up.save(out, exif=up.getexif().tobytes(), quality=95)
        n_rot += 1
    print(f"{n_rot} foto ditegakkan, sisanya disalin apa adanya, ke {a.dst}")


if __name__ == "__main__":
    main()
