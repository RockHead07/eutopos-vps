"""Uji R8: prior posisi lunak dan deep search (k=5 -> k=10)."""

import io
import threading

import numpy as np
import pycolmap
import torch
from fastapi.testclient import TestClient
from PIL import Image

from server.localizer import (
    DEEP_SEARCH_K,
    PRIOR_RADIUS_DEFAULT_M,
    PRIOR_RADIUS_MAX_M,
    PRIOR_RADIUS_MIN_M,
    Localizer,
    clamp_prior_radius,
    filter_prior_indices,
)


def _identity_align(scale: float = 1.0) -> dict:
    return {
        "method": "survey",
        "reference_points": 4,
        "residual_median_m": 0.1,
        "meter_from_model": {
            "scale": scale,
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
            "translation": [0.0, 0.0, 0.0],
        },
    }


def _make_synthetic_localizer(db_specs, *, align=None, k=5, min_inliers=50, good_names=None):
    """Bangun Localizer ringan tanpa memuat bobot MegaLoc/ALIKED/LightGlue."""
    loc = object.__new__(Localizer)
    loc.dev = torch.device("cpu")
    loc.resize = 64
    loc.global_resize = 32
    loc.k = k
    loc.min_inliers = min_inliers
    loc._align_source = lambda: align
    loc._align = type("NoAlign", (), {"get": lambda self: None})()

    loc.model = pycolmap.Reconstruction()
    cam = pycolmap.Camera(model="PINHOLE", width=64, height=48, params=[50.0, 50.0, 32.0, 24.0])
    loc.map_camera = cam

    good_names = set(good_names or ())
    loc.db = {}
    loc.db_names = []
    globals_list = []

    # Setiap gambar DB punya 1 titik 3D unik; PnP palsu cek apakah titik 3D gambar "good" muncul
    good_point_ids = set()
    for idx, (name, score, center_xyz) in enumerate(db_specs, start=1):
        p3d_id = loc.model.add_point3D(np.array([0.0, 0.0, 2.0 + idx * 0.1]), pycolmap.Track())
        if name in good_names:
            good_point_ids.add(p3d_id)
        g_vec = np.array([score, 0.0], dtype=np.float32)
        loc.db[name] = {
            "id": idx,
            "keypoints": torch.zeros((1, 2, 2), dtype=torch.float32),
            "descriptors": torch.zeros((1, 2, 2), dtype=torch.float32),
            "size": (64, 48),
            "global": g_vec,
            "center_model": np.array(center_xyz, dtype=np.float64),
            "points3D_ids": np.array([p3d_id, -1]),
        }
        loc.db_names.append(name)
        globals_list.append(g_vec)

    loc.db_global = np.stack(globals_list)
    loc.matched_names = []

    loc.megaloc = lambda inp: {
        "global_descriptor": torch.tensor([[1.0, 0.0]], dtype=torch.float32).repeat(
            inp["image"].shape[0], 1
        )
    }

    def fake_aliked(inp):
        b = inp["image"].shape[0]
        return {
            "keypoints": [torch.tensor([[10.0, 10.0], [20.0, 20.0]]) for _ in range(b)],
            "descriptors": [torch.ones((2, 2)) for _ in range(b)],
        }

    loc.aliked = fake_aliked

    # Petakan keypoint tensor identity untuk melacak nama gambar yang dicocokkan
    kp_to_name = {id(d["keypoints"]): name for name, d in loc.db.items()}

    def fake_lightglue(inp):
        name = kp_to_name.get(id(inp["keypoints1"]), "?")
        loc.matched_names.append(name)
        return {"matches0": torch.tensor([[0, -1]], dtype=torch.long)}

    loc.lightglue = fake_lightglue

    class FakePnP:
        def localize(self, pts2d_all, mkp, mp3d, camera):
            if any(pid in good_point_ids for pid in mp3d):
                return {
                    "cam_from_world": pycolmap.Rigid3d(),
                    "num_inliers": 80,
                    "inlier_mask": np.ones(len(mp3d), dtype=bool),
                }
            return {
                "cam_from_world": pycolmap.Rigid3d(),
                "num_inliers": 5,
                "inlier_mask": np.zeros(len(mp3d), dtype=bool),
            }

    loc.pnp = FakePnP()
    return loc


def test_clamp_prior_radius():
    assert PRIOR_RADIUS_DEFAULT_M == 20.0
    assert PRIOR_RADIUS_MIN_M == 5.0
    assert PRIOR_RADIUS_MAX_M == 50.0
    assert DEEP_SEARCH_K == 10
    assert clamp_prior_radius(None) == 20.0
    assert clamp_prior_radius(1.0) == 5.0
    assert clamp_prior_radius(15.0) == 15.0
    assert clamp_prior_radius(99.0) == 50.0


def test_filter_prior_indices_uses_horizontal_building_distance():
    centers = [
        np.array([5.0, 0.0, 100.0]),  # z jauh tetapi xy (5, 0) berjarak 5 m dari (0, 0) -> masuk
        np.array([25.0, 0.0, 0.0]),  # xy berjarak 25 m > 20 m -> keluar
        np.array([0.0, 10.0, 1.3]),  # xy berjarak 10 m -> masuk
    ]
    align = _identity_align(scale=1.0)
    assert filter_prior_indices(centers, align, (0.0, 0.0), 20.0) == [0, 2]
    assert filter_prior_indices(centers, None, (0.0, 0.0), 20.0) == []


def test_prior_restricts_retrieval_when_aligned():
    specs = [
        ("far_high.jpg", 0.95, [100.0, 0.0, 1.3]),
        ("near_ok.jpg", 0.80, [10.0, 0.0, 1.3]),
    ]
    loc = _make_synthetic_localizer(specs, align=_identity_align(), k=1, good_names={"near_ok.jpg"})
    rgb = np.zeros((48, 64, 3), dtype=np.float32)
    res = loc.localize(rgb, loc.map_camera, prior_xy=(10.0, 0.0), prior_radius_m=20.0)
    assert res.ok is True
    assert res.prior_used is True
    assert res.outside_prior is False
    assert res.deep_search is False
    assert loc.matched_names == ["near_ok.jpg"]


def test_soft_prior_falls_back_unfiltered_and_sets_outside_prior():
    specs = [
        ("far_ok.jpg", 0.95, [100.0, 0.0, 1.3]),
        ("near_bad.jpg", 0.80, [10.0, 0.0, 1.3]),
    ]
    loc = _make_synthetic_localizer(specs, align=_identity_align(), k=1, good_names={"far_ok.jpg"})
    rgb = np.zeros((48, 64, 3), dtype=np.float32)
    res = loc.localize(rgb, loc.map_camera, prior_xy=(10.0, 0.0), prior_radius_m=20.0)
    assert res.ok is True
    assert res.prior_used is True
    assert res.outside_prior is True
    assert res.deep_search is False
    assert "prior_fallback" in res.t
    assert loc.matched_names == ["near_bad.jpg", "far_ok.jpg"]


def test_prior_ignored_when_map_not_aligned():
    specs = [
        ("far_ok.jpg", 0.95, [100.0, 0.0, 1.3]),
        ("near_bad.jpg", 0.80, [10.0, 0.0, 1.3]),
    ]
    loc = _make_synthetic_localizer(specs, align=None, k=1, good_names={"far_ok.jpg"})
    rgb = np.zeros((48, 64, 3), dtype=np.float32)
    res = loc.localize(rgb, loc.map_camera, prior_xy=(10.0, 0.0), prior_radius_m=20.0)
    assert res.ok is True
    assert res.prior_used is False
    assert res.outside_prior is False
    assert loc.matched_names == ["far_ok.jpg"]


def test_deep_search_retries_with_k10_when_no_prior_and_k5_fails():
    specs = [(f"img_{i}.jpg", 0.95 - i * 0.01, [float(i), 0.0, 1.3]) for i in range(10)]
    loc = _make_synthetic_localizer(specs, align=_identity_align(), k=5, good_names={"img_7.jpg"})
    rgb = np.zeros((48, 64, 3), dtype=np.float32)
    res = loc.localize(rgb, loc.map_camera)
    assert res.ok is True
    assert res.deep_search is True
    assert res.prior_used is False
    assert res.outside_prior is False
    assert "deep_search" in res.t
    assert "img_7.jpg" in loc.matched_names


def test_localize_endpoint_accepts_prior_and_rejects_partial(monkeypatch):
    from server.app import app

    specs = [
        ("far_ok.jpg", 0.95, [100.0, 0.0, 1.3]),
        ("near_bad.jpg", 0.80, [10.0, 0.0, 1.3]),
    ]
    loc = _make_synthetic_localizer(specs, align=_identity_align(), k=1, good_names={"far_ok.jpg"})
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app.state.lock = threading.Lock()
    app.state.area_id, app.state.map_version = "floor10", 2
    app.state.localizer = loc

    buf = io.BytesIO()
    Image.new("RGB", (64, 48)).save(buf, "PNG")
    client = TestClient(app)

    # partial prior -> 422
    bad = client.post(
        "/localize",
        files={"image": ("q.png", buf.getvalue(), "image/png")},
        data={"prior_x": "10.0"},
    )
    assert bad.status_code == 422

    # full prior -> fallback outside_prior=True
    ok = client.post(
        "/localize",
        files={"image": ("q.png", buf.getvalue(), "image/png")},
        data={"prior_x": "10.0", "prior_y": "0.0", "prior_radius_m": "1.0"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["status"] == "ok"
    assert body["prior_used"] is True
    assert body["outside_prior"] is True
    assert body["deep_search"] is False
    assert "prior_fallback" in body["t_s"]
