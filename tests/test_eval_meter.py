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
