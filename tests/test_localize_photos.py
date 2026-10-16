"""spike/localize_photos.py: jawaban /localize menjadi baris results.csv seperti spike/run.py."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spike"))
import localize_photos as lp


def ok_body(q_xyzw, position=(1.0, 2.0, 3.0), inliers=120):
    return {
        "status": "ok",
        "inliers": inliers,
        "correspondences": 300,
        "pose_model": {"position": list(position), "rotation_xyzw": list(q_xyzw)},
        "t_s": {"total": 0.5},
    }


def near(a, b):
    return all(abs(x - y) < 1e-9 for x, y in zip(a, b, strict=True))


def test_identity_rotation_looks_along_model_z():
    assert near(lp.view_dir([0, 0, 0, 1]), [0, 0, 1])


def test_quarter_turn_about_y_looks_along_x():
    s = math.sin(math.pi / 4)
    assert near(lp.view_dir([0, s, 0, s]), [1, 0, 0])


def test_ok_answer_becomes_a_row_eval_meter_reads():
    r = lp.row("P07_xp.jpg", 200, ok_body([0, 0, 0, 1]))
    assert r["ok"] is True and r["inliers"] == 120
    assert r["center_xyz_model"] == "[1.0, 2.0, 3.0]"
    assert r["view_dir_model"] == "[0.0, 0.0, 1.0]"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, {"status": "failed", "inliers": 12, "pose_model": None}),
        (503, {"detail": "no active map"}),
        (500, None),
    ],
)
def test_failures_are_rows_without_pose(status, body):
    r = lp.row("P07_yn.jpg", status, body)
    assert r["ok"] is False and r["center_xyz_model"] == "" and r["view_dir_model"] == ""


def test_access_redirect_stops_the_run():
    with pytest.raises(SystemExit, match="token"):
        lp.row("P01_xp.jpg", 302, None)


def test_eval_meter_reads_the_written_csv(tmp_path):
    pytest.importorskip("pycolmap")
    import csv

    import eval_meter

    path = tmp_path / "results.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=lp.COLUMNS)
        w.writeheader()
        w.writerow(lp.row("P07_xp.jpg", 200, ok_body([0, 0, 0, 1])))
        w.writerow(lp.row("P07_yn.jpg", 200, {"status": "failed", "inliers": 12}))
    rows, inliers, dirs = eval_meter.read_results(path)
    assert rows == {"P07_xp.jpg": [1.0, 2.0, 3.0], "P07_yn.jpg": None}
    assert inliers == {"P07_xp.jpg": 120, "P07_yn.jpg": 12}
    assert dirs["P07_xp.jpg"] == [0.0, 0.0, 1.0] and dirs["P07_yn.jpg"] is None
