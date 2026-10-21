"""Kerangka gedung, peta 2D, dan .glb untuk halaman area (spesifikasi 2026-10-21 bagian 5c, 5g)."""

import io
import json
import math
import struct

import numpy as np
import pytest
from PIL import Image

from server import floorplan

# 90 derajat di sumbu z, skala 2, geser +1 di x
SIM = {
    "scale": 2.0,
    "rotation_xyzw": [0, 0, math.sqrt(0.5), math.sqrt(0.5)],
    "translation": [1, 0, 0],
}


def test_to_building_scales_rotates_then_translates():
    out = floorplan.to_building(np.array([[1.0, 0, 0], [0, 0, 1.0]]), SIM)
    np.testing.assert_allclose(out, [[1.0, 2.0, 0.0], [1.0, 0.0, 2.0]], atol=1e-9)


def test_to_building_matches_pycolmap_sim3d():
    pycolmap = pytest.importorskip("pycolmap")
    q = np.array([0.1, -0.7, 0.2, 0.68])
    q /= np.linalg.norm(q)
    m = {"scale": 0.43, "rotation_xyzw": q.tolist(), "translation": [3.1, -0.9, 1.34]}
    p = np.array([[0.5, -1.2, 2.0], [3.0, 0.1, -0.4]])
    sim = pycolmap.Sim3d(m["scale"], pycolmap.Rotation3d(q), np.array(m["translation"]))
    np.testing.assert_allclose(floorplan.to_building(p, m), sim * p, atol=1e-6)


def test_floorplan_marks_occupied_cells_and_keeps_the_pixel_rule():
    points = np.array([[1.0, 2.0, 1.0]] * 50 + [[4.0, 4.0, 1.0]])
    png, meta = floorplan.render_floorplan(points, np.array([[0.0, 0.0, 1.3]]))
    img = Image.open(io.BytesIO(png)).convert("L")
    assert img.size == (meta["width"], meta["height"])
    px = int((1.0 - meta["origin_x"]) / meta["res_m"])
    py = meta["height"] - 1 - int((2.0 - meta["origin_y"]) / meta["res_m"])
    assert img.getpixel((px, py)) < 128


def test_floor_points_are_ignored():
    points = np.array([[1.0, 2.0, 0.05]] * 50 + [[4.0, 4.0, 1.0]])
    png, meta = floorplan.render_floorplan(points, np.array([[0.0, 0.0, 1.3]]))
    img = Image.open(io.BytesIO(png)).convert("L")
    px = int((1.0 - meta["origin_x"]) / meta["res_m"])
    py = meta["height"] - 1 - int((2.0 - meta["origin_y"]) / meta["res_m"])
    assert img.getpixel((px, py)) == 255


def test_glb_header_and_point_count():
    glb = floorplan.points_glb(
        np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]), np.array([[255, 0, 0], [0, 255, 0]])
    )
    magic, version, length = struct.unpack_from("<4sII", glb, 0)
    assert (magic, version, length) == (b"glTF", 2, len(glb))
    json_len, _ = struct.unpack_from("<II", glb, 12)
    doc = json.loads(glb[20 : 20 + json_len])
    prim = doc["meshes"][0]["primitives"][0]
    assert prim["mode"] == 0
    assert doc["accessors"][prim["attributes"]["POSITION"]]["count"] == 2
    assert "COLOR_0" in prim["attributes"]
