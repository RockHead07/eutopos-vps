"""Uji spike/eval_meter.py lewat self-test sintetisnya (posisi meter dan arah hadap)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spike"))
pytest.importorskip("pycolmap")
import eval_meter


def test_self_test_recovers_position_and_heading_errors():
    eval_meter.self_test()


def test_old_results_without_view_column_still_load(tmp_path):
    f = tmp_path / "results.csv"
    f.write_text(
        "query,ok,inliers,correspondences,t_pose_s,center_xyz_model\n"
        'query/P01_a.jpg,True,120,300,0.5,"[1.0, 2.0, 3.0]"\n',
        encoding="utf-8",
    )
    rows, inliers, dirs = eval_meter.read_results(f)
    assert rows["query/P01_a.jpg"] == [1.0, 2.0, 3.0] and inliers["query/P01_a.jpg"] == 120
    assert dirs["query/P01_a.jpg"] is None


def _straight_map(n=8):
    """Titik zig-zag, foto tepat di atas titik, peta = Sim3 diketahui dari dunia meter."""
    import numpy as np
    import pycolmap

    gt = {f"P{i:02d}": (i * 1.5, 0.3 if i % 2 else 1.7) for i in range(n)}
    q = np.array([0.1, 0.7, 0.2, 0.68])
    model_from_world = pycolmap.Sim3d(
        4.0, pycolmap.Rotation3d(q / np.linalg.norm(q)), np.array([3.0, -1, 2])
    ).inverse()
    rows = {
        f"query/{p}_a.jpg": (model_from_world * np.array([[x, y, 1.3]]))[0].tolist()
        for p, (x, y) in gt.items()
    }
    return gt, rows, model_from_world


def test_holdout_points_stay_out_of_the_alignment_the_app_uses():
    # Uji navigasi di lapangan memakai align.json; titik ujinya tidak boleh ikut menaksirnya.
    import numpy as np

    gt, rows, model_from_world = _straight_map()
    x, y = gt["P07"]
    rows["query/P07_a.jpg"] = (model_from_world * np.array([[x + 0.8, y, 1.3]]))[0].tolist()
    _, s, _ = eval_meter.evaluate(rows, gt, 1.3, 1.0, holdout={"P07"})
    assert s["alignment_points"] == 7 and s["holdout_points"] == ["P07"], s
    assert s["residual_max_m"] < 1e-3, s  # sisa hanya dari titik penyelarasan, yang tepat
    assert abs(s["holdout_median_error_m"] - 0.8) < 1e-2, s


def test_holdout_must_name_known_points_and_leave_enough_to_align():
    gt, rows, _ = _straight_map(5)
    with pytest.raises(SystemExit, match="tidak ada"):
        eval_meter.evaluate(rows, gt, 1.3, 1.0, holdout={"P99"})
    with pytest.raises(SystemExit, match="penyelarasan"):
        eval_meter.evaluate(rows, gt, 1.3, 1.0, holdout={"P00", "P01"})
