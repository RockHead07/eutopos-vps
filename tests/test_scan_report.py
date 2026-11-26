"""Uji fungsi murni penyusun kartu laporan scan (server/scan_report.py)."""

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from server import scan_report
from server.db import MapJob

RUN = {
    "features": "aliked",
    "matcher": "lightglue",
    "max_keypoints": 1024,
    "resize_max": 1024,
    "sequential_pairs": 10,
    "detection_threshold": 0.01,
    "map_images": 4,
    "map_registered": 4,
    "map_points3D": 1200,
    "queries": 8,
    "t_map_s": {"local_extract": 1.2, "match": 2.3, "reconstruction": 4.5},
    "env": {"gpu": "RTX 3060", "commit": "14085e0"},
}

# Segmen 0: dua foto 1 s, 3 m di X.
# Segmen 1 mulai 100 s kemudian: dua foto 2 s, 4 m di Z, Y naik 5 m.
FRAMES_TWO_SEGMENTS = [
    {"file": "000001.jpg", "t_ns": 0, "segment": 0, "position": [0.0, 1.0, 0.0]},
    {"file": "000002.jpg", "t_ns": 1_000_000_000, "segment": 0, "position": [3.0, 1.0, 0.0]},
    {"file": "000003.jpg", "t_ns": 101_000_000_000, "segment": 1, "position": [0.0, 1.0, 0.0]},
    {"file": "000004.jpg", "t_ns": 103_000_000_000, "segment": 1, "position": [0.0, 6.0, 4.0]},
]


def test_straight_line_footprint():
    line = np.array([[0.0, 0.0], [10.0, 0.0]])
    area = scan_report.footprint_m2([line], 1.0, 0.25)
    assert abs(area - (20 + math.pi)) <= 2 * 10.5 * 0.25  # toleransi satu lapis sel di keliling


def test_back_and_forth_does_not_double():
    there = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 0.0]])
    assert scan_report.footprint_m2([there], 1.0, 0.25) == scan_report.footprint_m2(
        [there[:2]], 1.0, 0.25
    )


def test_duration_and_path_per_segment():
    r = scan_report.recording(FRAMES_TWO_SEGMENTS, None, None, None, RUN)
    assert r["source"] == "arcore"
    assert r["map_photos"] == 4
    assert r["query_photos"] == 8
    assert r["duration_s"] == 3.0
    assert r["path_length_m"] == 7.0
    assert r["segments"] == 2
    assert r["mean_speed_m_s"] == pytest.approx(7.0 / 3.0)


def test_per_segment_footprint_is_flagged_upper_bound():
    frames = [
        {"file": "000001.jpg", "t_ns": 0, "segment": 0, "position": [0.0, 1.0, 0.0]},
        {"file": "000002.jpg", "t_ns": 1_000_000_000, "segment": 0, "position": [5.0, 1.0, 0.0]},
        {"file": "000003.jpg", "t_ns": 20_000_000_000, "segment": 1, "position": [50.0, 1.0, 0.0]},
        {"file": "000004.jpg", "t_ns": 21_000_000_000, "segment": 1, "position": [55.0, 1.0, 0.0]},
    ]
    r = scan_report.recording(frames, None, None, None, RUN)
    assert r["footprint"]["frame"] == "arcore_per_segment"
    assert r["footprint"]["method"] == "trajectory_buffer"
    assert r["footprint"]["radius_m"] == 1.0
    assert r["footprint"]["cell_m"] == 0.25
    assert r["footprint_upper_bound"] is True
    seg0 = scan_report.footprint_m2([np.array([[0.0, 0.0], [5.0, 0.0]])], 1.0, 0.25)
    seg1 = scan_report.footprint_m2([np.array([[50.0, 0.0], [55.0, 0.0]])], 1.0, 0.25)
    assert r["footprint_m2"] == pytest.approx(seg0 + seg1)


def test_aligned_frame_used_when_available():
    frames = [
        {"file": "images/000001.jpg", "t_ns": 0, "segment": 0, "position": [0.0, 1.0, 0.0]},
        {
            "file": "images/000002.jpg",
            "t_ns": 1_000_000_000,
            "segment": 0,
            "position": [1.0, 1.0, 0.0],
        },
        {
            "file": "images/000003.jpg",
            "t_ns": 2_000_000_000,
            "segment": 0,
            "position": [2.0, 1.0, 0.0],
        },
    ]
    aligned = {
        "000001.jpg": np.array([0.0, 0.0, 1.2]),
        "000002.jpg": np.array([5.0, 0.0, 1.5]),
        "000003.jpg": np.array([10.0, 0.0, 2.0]),
    }
    r = scan_report.recording(frames, None, aligned, None, RUN)
    assert r["footprint"]["frame"] == "aligned_sfm"
    assert r.get("footprint_upper_bound") is not True
    assert r["height_range_m"] == pytest.approx(0.8)
    expected = scan_report.footprint_m2(
        [np.array([[0.0, 0.0], [5.0, 0.0], [10.0, 0.0]])], 1.0, 0.25
    )
    assert r["footprint_m2"] == pytest.approx(expected)


def test_meta_fields_and_missing_meta():
    frames = [
        {"file": "000001.jpg", "t_ns": 0, "position": [0.0, 1.0, 0.0]},
    ]
    meta = {"tracking_losses": 2, "device_model": "TECNO KL7"}
    with_meta = scan_report.recording(frames, meta, None, None, RUN)
    assert with_meta["tracking_losses"] == 2
    assert with_meta["device_model"] == "TECNO KL7"
    assert "tracking_losses_reason" not in with_meta
    assert "device_model_reason" not in with_meta

    without_meta = scan_report.recording(frames, None, None, None, RUN)
    assert without_meta["tracking_losses"] is None
    assert without_meta["tracking_losses_reason"] == "no_meta"
    assert without_meta["device_model"] is None
    assert without_meta["device_model_reason"] == "no_meta"


def test_single_photo():
    frames = [{"file": "000001.jpg", "t_ns": 5_000_000_000, "position": [2.0, 1.3, 3.0]}]
    r = scan_report.recording(frames, None, None, None, RUN)
    assert r["duration_s"] == 0.0
    assert r["path_length_m"] == 0.0
    assert r["mean_speed_m_s"] is None
    assert r["height_range_m"] == 0.0
    assert abs(r["footprint_m2"] - math.pi) <= 2 * math.pi * 0.25


def test_empty_frames_jsonl():
    r = scan_report.recording([], None, None, None, RUN)
    assert r["source"] == "arcore"
    assert r["map_photos"] == 0
    assert r["segments"] == 0
    assert r["duration_s"] is None and r["duration_s_reason"] == "not_recorded"
    assert r["path_length_m"] is None and r["path_length_m_reason"] == "not_recorded"
    assert r["footprint_m2"] is None and r["footprint_m2_reason"] == "not_recorded"
    assert r["mean_speed_m_s"] is None
    assert r["height_range_m"] is None


def test_video_job_recording():
    r = scan_report.recording(None, None, None, 95.0, RUN)
    assert r["source"] == "video"
    assert r["duration_s"] == 95.0
    assert r["map_photos"] == 4
    assert r["path_length_m"] is None and r["path_length_m_reason"] == "no_arcore"
    assert r["footprint_m2"] is None and r["footprint_m2_reason"] == "no_arcore"
    assert r["tracking_losses"] is None and r["tracking_losses_reason"] == "no_arcore"
    assert r["device_model"] is None and r["device_model_reason"] == "no_arcore"
    assert r["height_range_m"] is None and r["height_range_m_reason"] == "no_arcore"

    deleted = scan_report.recording(None, None, None, None, RUN)
    assert deleted["duration_s"] is None
    assert deleted["duration_s_reason"] == "video_deleted"


def test_multi_floor_warning():
    frames = [
        {"file": "000001.jpg", "t_ns": 0, "position": [0.0, 0.0, 0.0]},
        {"file": "000002.jpg", "t_ns": 1_000_000_000, "position": [1.0, 3.0, 0.0]},
    ]
    r = scan_report.recording(frames, None, None, None, RUN)
    assert r["height_range_m"] == 3.0
    assert "multi_floor" in r["warnings"]


def test_network_mbps():
    t0 = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(seconds=80)
    videos = [
        {
            "role": "peta",
            "kind": "frames",
            "size": 100_000_000,
            "upload_started_at": t0.isoformat(),
            "uploaded_at": t1.isoformat(),
        }
    ]
    net = scan_report.network(videos)
    assert net["total_bytes"] == 100_000_000
    assert net["seconds"] == 80.0
    assert net["mbps"] == pytest.approx(10.0)
    assert len(net["uploads"]) == 1
    assert net["uploads"][0]["mbps"] == pytest.approx(10.0)

    cli = scan_report.network([{"path": "/data/v.mp4", "role": "peta"}])
    assert cli["uploads"] is None and cli["uploads_reason"] == "cli_job"
    assert cli["total_bytes"] is None and cli["seconds"] is None and cli["mbps"] is None

    old = scan_report.network([{"name": "a.mp4", "role": "peta", "size": 100}])
    assert old["uploads"] is None and old["uploads_reason"] == "not_recorded"
    assert old["total_bytes"] is None and old["seconds"] is None and old["mbps"] is None


def test_queue_and_total():
    t_up = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
    t_start = t_up + timedelta(seconds=10)
    t_now = t_start + timedelta(seconds=45)
    job = MapJob(
        area_id="floor10",
        created_by="a@x.id",
        status="running",
        videos=[
            {"name": "a.mp4", "role": "peta", "size": 100, "uploaded_at": t_up.isoformat()},
        ],
        created_at=t_up - timedelta(seconds=60),
        started_at=t_start,
    )
    live = {"stage_seconds": {"gpu_wait": 0.5, "build": 40.0}, "gpu_wait_s": 0.5}
    proc = scan_report.processing(job, t_now, live, RUN)
    assert proc["queue_s"] == 10.0
    assert proc["total_s"] == 45.0
    assert proc["gpu_wait_s"] == 0.5
    assert proc["stage_seconds"] == {"gpu_wait": 0.5, "build": 40.0}
    assert proc["map_stage_seconds"] == RUN["t_map_s"]
    assert proc["env"] == RUN["env"]


def test_quality_copies_summary():
    summary = {
        "run": RUN,
        "inspect": {"parts": [{"label": "utama"}], "queries": 8, "accepted": 7},
        "align": {
            "status": "applied",
            "residual_median_m": 0.11,
            "residual_max_m": 0.24,
            "scale": 1.02,
            "matched_frames": 4,
        },
        "gate": {"decision": "publish", "reasons": [], "queries": 8, "accepted": 7},
    }
    stats = {
        "mean_reprojection_error_px": 0.92,
        "mean_track_length": 4.5,
        "mean_observations_per_image": 320.0,
    }
    q = scan_report.quality(summary, stats)
    assert q["registered"] == 4
    assert q["images"] == 4
    assert q["points3d"] == 1200
    assert q["parts"] == 1
    assert q["mean_reprojection_error_px"] == 0.92
    assert q["mean_track_length"] == 4.5
    assert q["mean_observations_per_image"] == 320.0
    assert q["align"] == {
        "status": "applied",
        "residual_median_m": 0.11,
        "residual_max_m": 0.24,
        "scale": 1.02,
    }
    assert q["gate"] == summary["gate"]
    assert q["params"] == {
        "features": "aliked",
        "matcher": "lightglue",
        "max_keypoints": 1024,
        "resize_max": 1024,
        "sequential_pairs": 10,
        "detection_threshold": 0.01,
    }

    q_no_stats = scan_report.quality(summary, None)
    assert q_no_stats["mean_reprojection_error_px"] is None
    assert q_no_stats["mean_track_length"] is None
    assert q_no_stats["mean_observations_per_image"] is None

    card = scan_report.build(
        recording={"source": "arcore"},
        network={"mbps": 10.0},
        processing={"total_s": 45.0},
        quality=q,
        now=datetime(2026, 11, 25, 10, 5, 0, tzinfo=UTC),
    )
    assert card["version"] == 1
    assert card["computed_at"] == "2026-11-25T10:05:00+00:00"
    assert set(card) == {"version", "computed_at", "recording", "network", "processing", "quality"}


def test_corrupt_frames_only_nulls_recording(tmp_path):
    map_dir = tmp_path / "maps" / "floor10" / "job-1"
    (map_dir / "capture").mkdir(parents=True)
    (map_dir / "capture" / "frames.jsonl").write_text(
        '{"file":"000001.jpg","position":[0,1,2]}\nnot-json\n', encoding="utf-8"
    )
    t0 = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
    job = MapJob(
        id=1,
        area_id="floor10",
        created_by="cli",
        status="done",
        videos=[{"path": "/data/scan.zip", "role": "peta", "kind": "frames"}],
        created_at=t0,
        started_at=t0 + timedelta(seconds=2),
    )
    summary = {
        "run": RUN,
        "inspect": {"parts": [{"label": "utama"}], "queries": 8, "accepted": 7},
        "align": {"status": "skipped", "reason": "no_frames"},
        "gate": {"decision": "publish", "reasons": [], "queries": 8, "accepted": 7},
    }
    card = scan_report.from_disk(
        job,
        map_dir,
        summary,
        {"stage_seconds": {"build": 1.0}, "gpu_wait_s": 0.0},
        t0 + timedelta(seconds=10),
    )
    assert card["version"] == 1
    assert "error" in card["recording"]
    assert card["quality"]["registered"] == 4
    assert card["quality"]["parts"] == 1


def test_model_stats_and_aligned_centers_from_pycolmap(tmp_path):
    import json

    import pycolmap

    from server import pipeline

    map_dir = tmp_path / "maps" / "floor10" / "job-2"
    run_path = pipeline.run_dir(map_dir)
    sfm_dir = run_path / "sfm"
    sfm_dir.mkdir(parents=True)
    model = pycolmap.synthesize_dataset(pycolmap.SyntheticDatasetOptions())
    model.write(str(sfm_dir))

    stats = scan_report.model_stats(sfm_dir)
    assert stats is not None
    assert stats["mean_reprojection_error_px"] >= 0
    assert stats["mean_track_length"] > 0
    assert stats["mean_observations_per_image"] > 0

    (run_path / "align.json").write_text(
        json.dumps(
            {
                "meter_from_model": {
                    "scale": 2.0,
                    "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
                    "translation": [1.0, 2.0, 3.0],
                }
            }
        ),
        encoding="utf-8",
    )
    centers = scan_report.aligned_centers(map_dir, {"align": {"status": "applied"}})
    assert centers is not None
    assert len(centers) == model.num_reg_images()
    assert scan_report.aligned_centers(map_dir, {"align": {"status": "skipped"}}) is None
