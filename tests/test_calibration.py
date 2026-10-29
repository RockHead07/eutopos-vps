"""server/calibration: urai results.csv, agregasi, dan penaksiran penyelarasan (roadmap M1-3a)."""

import numpy as np
import pycolmap
import pytest

from server import alignment, calibration
from server.calibration import CalibrationError, CalPoint, Observation


def truth():
    """Model = truth * dunia (skala 4,0), jadi meter_from_model punya skala 0,25."""
    q = np.array([0.1, 0.7, 0.2, 0.68])
    return pycolmap.Sim3d(4.0, pycolmap.Rotation3d(q / np.linalg.norm(q)), np.array([3.0, -1, 2]))


def zigzag(n=8):
    return {f"P{i:02d}": (i * 1.5, 0.3 if i % 2 else 1.7) for i in range(n)}


def model_xyz(x, y, h=1.3):
    return tuple(float(v) for v in (truth() * np.array([[x, y, h]]))[0])


def refs(n=8):
    return [CalPoint(p, x, y, "reference") for p, (x, y) in zigzag(n).items()]


def observed_for(points, shift=None):
    shift = shift or {}
    out = {}
    for p in points:
        dx, dy = shift.get(p.point_id, (0.0, 0.0))
        out[p.point_id] = model_xyz(p.x_m + dx, p.y_m + dy)
    return out


def test_fit_recovers_scale_and_has_tiny_residuals():
    pts = refs()
    r = calibration.fit_alignment(pts, observed_for(pts))
    assert abs(r.stats["scale"] - 0.25) < 1e-6
    assert r.stats["residual_max_m"] < 1e-6
    assert r.stats["reference_points"] == 8 and r.stats["test_points"] == 0
    assert r.stats["test_median_m"] is None and r.stats["test_max_m"] is None
    alignment.validate_align(r.align)
    assert r.align["phone_height_m"] == 1.3 and r.align["holdout_points"] == []
    assert len(r.rows) == 8 and r.rows[0]["role"] == "reference"
    assert r.rows[0]["observed_x"] == pytest.approx(r.rows[0]["x_m"], abs=1e-6)


def test_test_points_never_influence_the_fit():
    base = refs()
    test_pt = CalPoint("T1", 4.0, 1.0, "test")
    with_test = calibration.fit_alignment(
        [*base, test_pt], observed_for([*base, test_pt], shift={"T1": (5.0, 0.0)})
    )
    without = calibration.fit_alignment(base, observed_for(base))
    a, b = with_test.align["meter_from_model"], without.align["meter_from_model"]
    assert a["scale"] == pytest.approx(b["scale"], abs=1e-6)
    np.testing.assert_allclose(a["translation"], b["translation"], atol=1e-6)
    np.testing.assert_allclose(a["rotation_xyzw"], b["rotation_xyzw"], atol=1e-6)
    assert with_test.align["holdout_points"] == ["T1"]
    assert with_test.stats["test_points"] == 1
    assert with_test.stats["test_max_m"] == pytest.approx(5.0, abs=1e-3)
    assert with_test.stats["reference_points"] == 8


def test_one_gross_outlier_among_references_is_survived():
    pts = refs()
    r = calibration.fit_alignment(pts, observed_for(pts, shift={"P03": (50.0, 0.0)}))
    assert abs(r.stats["scale"] - 0.25) < 1e-3
    worst = max(r.rows, key=lambda row: row["error_m"])
    assert worst["point_id"] == "P03" and worst["error_m"] > 10


def test_collinear_reference_points_are_rejected():
    pts = [CalPoint(f"L{i}", float(i), 0.0, "reference") for i in range(5)]
    with pytest.raises(CalibrationError) as e:
        calibration.fit_alignment(pts, observed_for(pts))
    assert e.value.code == "collinear"


def test_fewer_than_four_reference_points_are_rejected():
    pts = refs(3)
    with pytest.raises(CalibrationError) as e:
        calibration.fit_alignment(pts, observed_for(pts))
    assert e.value.code == "too_few_reference"


def test_a_reference_without_an_observation_does_not_count():
    pts = refs(4)
    seen = observed_for(pts[:3])
    with pytest.raises(CalibrationError) as e:
        calibration.fit_alignment(pts, seen)
    assert e.value.code == "no_observation"


def test_aggregate_drops_low_inlier_observations_and_takes_the_median():
    obs = [
        Observation("P01", (1.0, 2.0, 3.0), 120),
        Observation("P01", (3.0, 4.0, 5.0), 130),
        Observation("P01", (99.0, 99.0, 99.0), 40),
        Observation("P02", (7.0, 7.0, 7.0), 49),
    ]
    got = calibration.aggregate(obs)
    assert got == {"P01": (2.0, 3.0, 4.0)}


def test_parse_results_csv_reads_old_and_new_columns():
    old = (
        "query,ok,inliers,center_xyz_model\n"
        'query/P07_xp.jpg,True,120,"[1.0, 2.0, 3.0]"\n'
        "query/P08_a.jpg,False,0,\n"
        'query/P09_a.jpg,True,abc,"[1, 2]"\n'
    )
    got = calibration.parse_results_csv(old)
    assert got == [Observation("P07", (1.0, 2.0, 3.0), 120)]
    new = (
        "query,ok,inliers,center_xyz_model,view_dir_model\n"
        'C:\\x\\P12_yp.jpg,True,80,"[4, 5, 6]","[0, 0, 1]"\n'
    )
    assert calibration.parse_results_csv(new) == [Observation("P12", (4.0, 5.0, 6.0), 80)]


def test_parse_results_csv_requires_the_columns_it_reads():
    with pytest.raises(CalibrationError) as e:
        calibration.parse_results_csv("query,ok\nq/P01_a.jpg,True\n")
    assert e.value.code == "bad_input"
    with pytest.raises(CalibrationError):
        calibration.parse_results_csv("")


def test_nan_or_degenerate_input_never_yields_an_alignment():
    pts = refs(4)
    bad = observed_for(pts)
    bad["P01"] = (float("nan"), 0.0, 0.0)
    with pytest.raises(CalibrationError) as e:
        calibration.fit_alignment(pts, bad)
    assert e.value.code == "bad_input"

    nan_pt = [CalPoint("P00", float("nan"), 0.0, "reference"), *pts[1:]]
    with pytest.raises(CalibrationError) as e:
        calibration.fit_alignment(nan_pt, observed_for(pts))
    assert e.value.code == "bad_input"

    same = {p.point_id: (1.0, 1.0, 1.0) for p in pts}  # semua pengamatan di satu lokasi
    with pytest.raises(CalibrationError) as e:
        calibration.fit_alignment(pts, same)
    assert e.value.code in ("fit_failed", "bad_scale")


def test_duplicate_ids_and_unknown_roles_are_bad_input():
    pts = refs(4)
    with pytest.raises(CalibrationError) as e:
        calibration.fit_alignment([*pts, CalPoint("P00", 9, 9, "reference")], observed_for(pts))
    assert e.value.code == "bad_input"
    with pytest.raises(CalibrationError) as e:
        calibration.fit_alignment([CalPoint("X", 1, 1, "x"), *pts], observed_for(pts))
    assert e.value.code == "bad_input"
