"""Kerangka gedung G untuk halaman area: konversi dari model SfM, peta 2D, dan awan titik .glb.

Rumus sama dengan Localizer.to_building: p_G = s * R(q_xyzw) * p + t dari align.json versi aktif.
"""

import io
import json
import struct

import numpy as np
from PIL import Image


def _matrix(q_xyzw) -> np.ndarray:
    x, y, z, w = (float(v) for v in q_xyzw)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def to_building(xyz: np.ndarray, meter_from_model: dict) -> np.ndarray:
    """Titik N x 3 kerangka model ke G (meter menurut align.json)."""
    m = meter_from_model
    rot = _matrix(m["rotation_xyzw"])
    return m["scale"] * (np.asarray(xyz, dtype=float) @ rot.T) + np.asarray(m["translation"])


def render_floorplan(
    points_g: np.ndarray,
    cams_g: np.ndarray,
    res_m: float = 0.03,
    z_min: float = 0.2,
    z_max: float = 2.2,
) -> tuple[bytes, dict]:
    """Peta tampak atas: kerapatan titik setinggi dinding dan meja (lantai dan plafon dibuang).

    Piksel dari (x, y): px = int((x - origin_x) / res_m),
    py = height - 1 - int((y - origin_y) / res_m).
    """
    p = np.asarray(points_g, dtype=float).reshape(-1, 3)
    p = p[(p[:, 2] > z_min) & (p[:, 2] < z_max)]
    xy = np.vstack([p[:, :2], np.asarray(cams_g, dtype=float).reshape(-1, 3)[:, :2]])
    if len(xy) == 0:
        xy = np.zeros((1, 2))
    # Persentil memotong pencilan supaya satu titik nyasar tidak membesarkan kanvas.
    lo = np.percentile(xy, 1, axis=0) - 0.5
    hi = np.percentile(xy, 99, axis=0) + 0.5
    width, height = ((hi - lo) / res_m).astype(int) + 1
    grid = np.zeros((height, width))
    ix = ((p[:, 0] - lo[0]) / res_m).astype(int)
    iy = ((p[:, 1] - lo[1]) / res_m).astype(int)
    ok = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
    np.add.at(grid, (height - 1 - iy[ok], ix[ok]), 1)
    scale = np.log1p(grid.max()) or 1.0
    img = 255 - np.clip(np.log1p(grid) / scale * 255 * 1.6, 0, 255)
    buf = io.BytesIO()
    Image.fromarray(img.astype(np.uint8)).save(buf, "PNG")
    meta = {
        "origin_x": float(lo[0]),
        "origin_y": float(lo[1]),
        "res_m": res_m,
        "width": int(width),
        "height": int(height),
    }
    return buf.getvalue(), meta


def points_glb(points_g: np.ndarray, colors: np.ndarray) -> bytes:
    """Awan titik berwarna sebagai .glb (glTF 2.0, primitif POINTS). G (z atas) ke glTF (y atas)."""
    g = np.asarray(points_g, dtype=float).reshape(-1, 3)
    pos = np.stack([g[:, 0], g[:, 2], -g[:, 1]], axis=1).astype(np.float32)
    col = (np.asarray(colors, dtype=float).reshape(-1, 3) / 255.0).astype(np.float32)
    pos_bytes, col_bytes = pos.tobytes(), col.tobytes()
    doc = {
        "asset": {"version": "2.0", "generator": "eutopos"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "COLOR_0": 1}, "mode": 0}]}],
        "buffers": [{"byteLength": len(pos_bytes) + len(col_bytes)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pos_bytes)},
            {"buffer": 0, "byteOffset": len(pos_bytes), "byteLength": len(col_bytes)},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(pos),
                "type": "VEC3",
                "min": pos.min(axis=0).tolist() if len(pos) else [0, 0, 0],
                "max": pos.max(axis=0).tolist() if len(pos) else [0, 0, 0],
            },
            {"bufferView": 1, "componentType": 5126, "count": len(col), "type": "VEC3"},
        ],
    }
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    binary = pos_bytes + col_bytes
    binary += b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(js), 0x4E4F534A)
        + js
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )
