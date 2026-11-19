import numpy as np
import pycolmap
import pytest

from server import alignment, quick_align, sim3


def test_unity_to_building_changes_handedness_and_maps_y_to_up():
    axes = quick_align.unity_to_building(np.eye(3))
    np.testing.assert_array_equal(axes, [[1, 0, 0], [0, 0, 1], [0, 1, 0]])
    assert np.linalg.det(axes) == -1


def test_load_model_returns_registered_centers_and_world_image_up(tmp_path):
    model = pycolmap.synthesize_dataset(pycolmap.SyntheticDatasetOptions())
    registered = model.reg_image_ids()
    first = model.images[registered[0]]
    name = first.name.rsplit("/", 1)[-1]
    first.name = "mapping/" + name
    model.write(str(tmp_path))

    centers, ups = quick_align.load_model(tmp_path)

    assert len(centers) == len(ups) == len(registered)
    pose = first.cam_from_world()
    world_from_cam = pose.inverse()
    np.testing.assert_allclose(centers[name], world_from_cam.translation)
    np.testing.assert_allclose(ups[name], world_from_cam.rotation.matrix()[:, 1] * -1)


def test_load_model_rejects_duplicate_registered_basenames(tmp_path):
    model = pycolmap.synthesize_dataset(pycolmap.SyntheticDatasetOptions())
    first, second, *_ = model.reg_image_ids()
    model.images[first].name = "a/frame.jpg"
    model.images[second].name = "b/frame.jpg"
    model.write(str(tmp_path))

    with pytest.raises(ValueError, match=r"frame\.jpg"):
        quick_align.load_model(tmp_path)


def test_arcore_recovers_known_sim3_from_left_handed_unity_poses():
    src = np.random.default_rng(91).normal(size=(16, 3))
    rotation = np.array([[0, -1, 0], [0, 0, 1], [-1, 0, 0]])
    translation = np.array([4.0, -7.0, 1.3 - np.median(2.25 * (src @ rotation.T)[:, 2])])
    building = 2.25 * (src @ rotation.T) + translation
    unity = building[:, [0, 2, 1]]
    unity[:, 1] += 19
    keys = [f"{i:06}.jpg" for i in range(len(src))]
    centers = dict(zip(keys, src, strict=True))
    frames = [
        {"file": f"images\\{name}", "position": p.tolist()}
        for name, p in zip(keys, unity, strict=True)
    ]
    frames.reverse()
    frames.append({"file": "unmatched.jpg", "position": [0, 0, 0]})

    result = quick_align.from_arcore(centers, frames)

    assert result["method"] == "arcore_pose"
    assert result["matched_frames"] == 16
    assert result["phone_height_m"] == 1.3
    assert result["residual_median_m"] == result["residual_max_m"] == 0
    transform = sim3.from_align(result["meter_from_model"])
    assert transform.scale == pytest.approx(2.25)
    np.testing.assert_allclose(transform.rotation.matrix(), rotation, atol=1e-8)
    np.testing.assert_allclose(transform.translation, translation, atol=1e-8)
    np.testing.assert_allclose(transform * src, building, atol=1e-8)
    assert alignment.validate_align(result) is result


def test_arcore_needs_at_least_ten_matches():
    centers = {f"{i}.jpg": np.zeros(3) for i in range(9)}
    frames = [{"file": name, "position": [0, 0, 0]} for name in centers]
    frames.append({"file": "unmatched.jpg", "position": [0, 0, 0]})
    with pytest.raises(ValueError, match="10"):
        quick_align.from_arcore(centers, frames)


@pytest.mark.parametrize("bad", ["not JSON", "{}", '{"file":"b.jpg","position":[1,2,NaN]}'])
def test_read_frames_reports_line_number(tmp_path, bad):
    path = tmp_path / "frames.jsonl"
    path.write_text('{"file":"a.jpg","position":[0,1,2]}\n' + bad + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="baris 2"):
        quick_align.read_frames(path)


@pytest.fixture
def tilted_track():
    tilt = np.deg2rad(31)
    yaw = np.deg2rad(38)
    around_x = np.array(
        [[1, 0, 0], [0, np.cos(tilt), -np.sin(tilt)], [0, np.sin(tilt), np.cos(tilt)]]
    )
    around_z = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
    model_from_building = around_x @ around_z
    building = np.array([[0, 0, 1.0], [10, 0, 1.8], [20, 0, 1.3], [30, 0, 1.3]])
    src = building @ model_from_building.T / 2.5 + [5, -6, 3]
    keys = ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]
    centers = dict(zip(reversed(keys), reversed(src), strict=True))
    up = model_from_building[:, 2]
    return centers, dict.fromkeys(keys, up), src, building, model_from_building


def test_known_distance_recovers_scale_up_yaw_origin_and_phone_height(tilted_track):
    centers, ups, src, building, rotation = tilted_track
    result = quick_align.from_known_distance(centers, ups, [("mapping/a.jpg", "b.jpg", 10)])
    assert result["method"] == "known_distance"
    assert result["known_distances"][0] == {
        "frame_a": "a.jpg",
        "frame_b": "b.jpg",
        "distance_m": 10,
        "model_distance": pytest.approx(4),
    }
    assert result["gravity_spread_deg"] == pytest.approx(0, abs=1e-6)
    assert "scale_spread_percent" not in result
    transform = sim3.from_align(result["meter_from_model"])
    assert transform.scale == pytest.approx(2.5)
    np.testing.assert_allclose(transform.rotation.matrix(), rotation.T, atol=1e-8)
    np.testing.assert_allclose(transform * src, building, atol=1e-8)
    assert alignment.validate_align(result) is result


def test_known_distance_two_pairs_reports_symmetric_scale_spread(tilted_track):
    centers, ups, *_ = tilted_track
    result = quick_align.from_known_distance(
        centers, ups, [("a.jpg", "b.jpg", 10), ("c.jpg", "d.jpg", 12)]
    )
    assert result["meter_from_model"]["scale"] == pytest.approx(2.75)
    assert result["scale_spread_percent"] == pytest.approx(100 * 0.5 / 2.75)


@pytest.mark.parametrize(
    "pair", [("a.jpg", "missing.jpg", 10), ("a.jpg", "a.jpg", 10), ("a.jpg", "b.jpg", 0)]
)
def test_known_distance_rejects_unregistered_or_invalid_pairs(tilted_track, pair):
    centers, ups, *_ = tilted_track
    with pytest.raises(ValueError):
        quick_align.from_known_distance(centers, ups, [pair])


def test_warnings_flag_a_single_distance_and_each_quality_threshold():
    data = {
        "method": "known_distance",
        "known_distances": [{"distance_m": 10}, {"distance_m": 10}],
        "gravity_spread_deg": 10,
        "scale_spread_percent": 5,
    }
    assert quick_align.warnings(data) == []
    assert len(quick_align.warnings(dict(data, known_distances=[{"distance_m": 10}]))) == 1
    assert len(quick_align.warnings(dict(data, known_distances=[{"distance_m": 9.99}] * 2))) == 1
    assert len(quick_align.warnings(dict(data, gravity_spread_deg=10.01))) == 1
    assert len(quick_align.warnings(dict(data, scale_spread_percent=5.01))) == 1
    arcore = {"method": "arcore_pose", "residual_median_m": 0.25}
    assert quick_align.warnings(arcore) == []
    assert len(quick_align.warnings(dict(arcore, residual_median_m=0.251))) == 1


def test_known_distance_rejects_scale_that_underflows_to_zero(tilted_track):
    centers, ups, *_ = tilted_track
    with pytest.raises(ValueError, match="skala"):
        quick_align.from_known_distance(
            centers, ups, [("a.jpg", "b.jpg", 5e-324), ("c.jpg", "d.jpg", 5e-324)]
        )
