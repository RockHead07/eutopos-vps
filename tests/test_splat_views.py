from types import SimpleNamespace

import numpy as np
import pycolmap
import pytest

from server.splat_views import level_rotation, training_views


def fake(name, center):
    pose = SimpleNamespace(rotation=SimpleNamespace(matrix=lambda: np.eye(3)))
    return SimpleNamespace(
        name=name,
        projection_center=lambda: np.array(center, dtype=float),
        cam_from_world=lambda: pose,
    )


def test_views_sorted_by_name_with_unit_forward():
    imgs = [fake(n, c) for n, c in [("b.jpg", [1, 0, 0]), ("a.jpg", [0, 0, 0])]]
    out = training_views(imgs)
    assert [v["name"] for v in out["views"]] == ["a.jpg", "b.jpg"]
    assert all(abs(np.linalg.norm(v["forward"]) - 1) < 1e-9 for v in out["views"])


def test_start_is_view_nearest_centroid():
    out = training_views([fake(f"{i}.jpg", [i, 0, 0]) for i in range(5)])
    assert out["start"] == 2


def test_subsamples_above_max_views_and_keeps_valid_start():
    out = training_views([fake(f"{i:04d}.jpg", [i, 0, 0]) for i in range(1000)], max_views=300)
    assert len(out["views"]) == 300
    assert out["views"][0]["name"] == "0000.jpg"
    assert out["views"][-1]["name"] == "0999.jpg"
    assert 0 <= out["start"] < 300


def test_level_rotation_maps_up_to_plus_y():
    for up in ([0, -1, 0.2], [0.3, 0.1, 0.9], [0, 1, 0]):
        up = np.array(up, dtype=float) / np.linalg.norm(up)
        q = level_rotation(up)
        assert abs(np.linalg.norm(q) - 1) < 1e-9
        assert np.allclose(pycolmap.Rotation3d(q) * up, [0, 1, 0], atol=1e-9)


def test_level_rotation_opposite_up_is_valid():
    q = level_rotation(np.array([0.0, -1.0, 0.0]))
    assert not np.any(np.isnan(q))
    assert np.allclose(pycolmap.Rotation3d(q) * np.array([0.0, -1.0, 0.0]), [0, 1, 0])


def test_empty_raises():
    with pytest.raises(ValueError, match="no registered images"):
        training_views([])
