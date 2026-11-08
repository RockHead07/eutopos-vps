"""Transformasi penempatan entitas splat PlayCanvas ke kerangka gedung (Task 2).

Memetakan titik di kerangka model/PLY ke posisi gedung dalam meter dengan sumbu
PlayCanvas (Y atas, tangan kanan) yang bersesuaian dengan (x, z, -y) gedung.
Komposisi:
    p_pc = C (s R p + t)
    C = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]
sehingga:
    scale = s
    rotation = q(C R)
    position = C t
"""

import numpy as np
import pycolmap

_C = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]], dtype=float)
_ROT_C = pycolmap.Rotation3d(_C)


def placement(meter_from_model: dict) -> dict:
    """Hitung transformasi entitas PlayCanvas dari meter_from_model (align.json atau DB)."""
    scale = float(meter_from_model["scale"])
    rot_model = pycolmap.Rotation3d(np.asarray(meter_from_model["rotation_xyzw"], dtype=float))
    trans_model = np.asarray(meter_from_model["translation"], dtype=float)

    rot_pc = _ROT_C * rot_model
    pos_pc = _C @ trans_model

    return {
        "position": [float(x) for x in pos_pc],
        "rotation_xyzw": [float(x) for x in rot_pc.quat],
        "scale": scale,
    }
