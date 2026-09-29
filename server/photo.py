"""Baca foto dari unggahan: tegakkan sesuai EXIF dan tentukan intrinsik cadangan dari EXIF."""

import io
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pycolmap
from PIL import Image

# Sama dengan PIL.ImageOps.exif_transpose. Piksel didekode dengan OpenCV (dekoder yang dipakai
# hloc saat membangun peta), jadi rotasi EXIF diterapkan manual di sini.
_UPRIGHT = {
    2: lambda a: a[:, ::-1],
    3: lambda a: a[::-1, ::-1],
    4: lambda a: a[::-1],
    5: lambda a: a.transpose(1, 0, 2),
    6: lambda a: np.rot90(a, -1),
    7: lambda a: a.transpose(1, 0, 2)[::-1, ::-1],
    8: lambda a: np.rot90(a, 1),
}


def decode_upright(data: bytes) -> np.ndarray:
    """-> RGB float32 (H, W, 3), tegak. ValueError kalau bukan gambar."""
    raw = cv2.imdecode(
        np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION
    )
    if raw is None:
        raise ValueError("bukan gambar yang bisa dibaca")
    with Image.open(io.BytesIO(data)) as im:
        orientation = im.getexif().get(0x0112, 1)
    image = _UPRIGHT.get(orientation, lambda a: a)(raw[:, :, ::-1])
    return np.ascontiguousarray(image).astype(np.float32)


def exif_camera(data: bytes, width: int, height: int) -> pycolmap.Camera:
    """Intrinsik taksiran COLMAP dari EXIF (panjang fokus) untuk foto tegak width x height.

    Tanpa EXIF, COLMAP memakai tebakan bawaan (fokus 1,2 x sisi terpanjang).
    """
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "query.jpg"
        path.write_bytes(data)
        cam = pycolmap.infer_camera_from_image(path)
    f = float(cam.params[0])  # SIMPLE_RADIAL: [f, cx, cy, k]; fokus tak berubah saat diputar
    return pycolmap.Camera(
        model="SIMPLE_RADIAL", width=width, height=height, params=[f, width / 2, height / 2, 0.0]
    )


def pinhole(fx: float, fy: float, cx: float, cy: float, width: int, height: int):
    return pycolmap.Camera(model="PINHOLE", width=width, height=height, params=[fx, fy, cx, cy])
