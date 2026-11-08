"""Uji penempatan entitas splat PlayCanvas ke kerangka gedung (Task 2 Step 1)."""

import math

import numpy as np
import pycolmap

from server.splat_frame import placement


def quat_rotate(rotation_xyzw: list[float] | np.ndarray, v: np.ndarray) -> np.ndarray:
    return pycolmap.Rotation3d(rotation_xyzw) * v


def test_placement_maps_a_model_point_to_the_viewer_frame():
    rng = np.random.default_rng(42)
    scale = 0.7
    q_rand = rng.standard_normal(4)
    q_rand /= np.linalg.norm(q_rand)
    rot_model = pycolmap.Rotation3d(q_rand)
    trans_model = rng.standard_normal(3)

    meter_from_model = {
        "scale": scale,
        "rotation_xyzw": [float(x) for x in rot_model.quat],
        "translation": [float(x) for x in trans_model],
    }

    p = np.array([1.2, -0.8, 3.4], dtype=float)
    g = scale * (rot_model * p) + trans_model
    expected_viewer = np.array([g[0], g[2], -g[1]], dtype=float)

    placed = placement(meter_from_model)
    actual_viewer = quat_rotate(placed["rotation_xyzw"], placed["scale"] * p) + np.asarray(
        placed["position"], dtype=float
    )

    diff = np.linalg.norm(actual_viewer - expected_viewer)
    assert diff < 1e-9


def test_placement_has_unit_quaternion_and_positive_scale():
    rng = np.random.default_rng(123)
    q_rand = rng.standard_normal(4)
    q_rand /= np.linalg.norm(q_rand)
    rot_model = pycolmap.Rotation3d(q_rand)
    meter_from_model = {
        "scale": 1.45,
        "rotation_xyzw": [float(x) for x in rot_model.quat],
        "translation": [0.1, -2.3, 4.5],
    }

    placed = placement(meter_from_model)
    q = placed["rotation_xyzw"]
    norm_q = math.sqrt(sum(x * x for x in q))
    assert abs(norm_q - 1.0) < 1e-6
    assert placed["scale"] > 0
    assert len(placed["position"]) == 3
    assert len(placed["rotation_xyzw"]) == 4
