"""Uji R5 server: server/align4dof.py, ekstraksi batch, dan POST /localize-multi."""

import io
import json
import math
import threading

import numpy as np
import pycolmap
import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, create_engine, select

from server import localize_log
from server.align4dof import (
    CONSENSUS_MIN_FRAMES,
    CONSENSUS_TRANSLATION_M,
    CONSENSUS_YAW_DEG,
    Alignment4Dof,
    FrameAlignment,
    consensus,
    forward_b,
    g_to_b,
    rot_y,
    solve_from_poses,
    wrap_deg,
    yaw_deg,
    yaw_diff_deg,
)
from server.db import LocalizeRequest
from server.localizer import Localizer, Result


def _png_bytes(w=64, h=48) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (50, 90, 120)).save(buf, "PNG")
    return buf.getvalue()


def _quat_axis_angle_xyzw(axis: np.ndarray, deg: float) -> list[float]:
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    half = math.radians(deg) / 2.0
    s = math.sin(half)
    return [float(a[0] * s), float(a[1] * s), float(a[2] * s), float(math.cos(half))]


def test_align4dof_frame_conventions_match_mobile_app():
    assert np.allclose(g_to_b([1.0, 2.0, 3.0]), [1.0, 3.0, 2.0])
    # +90 deg di sekitar y_G memutar +z_cam ke +x_G -> +x_B -> yaw 90
    q_x = _quat_axis_angle_xyzw([0, 1, 0], 90.0)
    f_x = forward_b(q_x)
    assert np.allclose(f_x, [1.0, 0.0, 0.0], atol=1e-5)
    assert yaw_deg(f_x) == pytest.approx(90.0, abs=1e-4)

    # -90 deg di sekitar x_G memutar +z_cam ke +y_G -> +z_B -> yaw 0
    q_y = _quat_axis_angle_xyzw([1, 0, 0], -90.0)
    f_y = forward_b(q_y)
    assert np.allclose(f_y, [0.0, 0.0, 1.0], atol=1e-5)
    assert yaw_deg(f_y) == pytest.approx(0.0, abs=1e-4)

    # Kamera terlalu tegak lurus -> None
    assert yaw_deg([0.1, -1.0, 0.1]) is None
    assert wrap_deg(190.0) == pytest.approx(-170.0)
    assert yaw_diff_deg(170.0, -170.0) == pytest.approx(20.0)


def test_solve_from_poses_recovers_true_4dof_alignment():
    # Alignment sejati: yaw = 35 deg, translation = [2.0, -0.3, 4.5]
    true_yaw = 35.0
    true_t = np.array([2.0, -0.3, 4.5])
    # Kamera di G berada di [3.0, 5.0, 1.4] menghadap +y_G (yaw_B = 0)
    b_pos_g = [3.0, 5.0, 1.4]
    b_rot_g = _quat_axis_angle_xyzw([1, 0, 0], -90.0)
    cam_pos_b = g_to_b(b_pos_g)
    ar_pos = (rot_y(true_yaw, cam_pos_b) + true_t).tolist()
    ar_rot = _quat_axis_angle_xyzw([0, 1, 0], true_yaw)  # di Unity yaw +35 dari +Z

    solved = solve_from_poses(ar_pos, ar_rot, b_pos_g, b_rot_g)
    assert solved is not None
    assert yaw_diff_deg(solved.yaw_deg, true_yaw) < 1e-4
    assert np.allclose(solved.translation, true_t, atol=1e-5)


def test_consensus_clusters_with_outlier_circular_yaw_and_tiebreak():
    assert CONSENSUS_TRANSLATION_M == pytest.approx(0.5)
    assert CONSENSUS_YAW_DEG == pytest.approx(5.0)
    assert CONSENSUS_MIN_FRAMES == 2

    # 3 frame setuju lintas batas +-180 deg + 1 pencilan 6 m
    items = [
        FrameAlignment(0, Alignment4Dof(179.0, np.array([1.0, 0.0, 2.0])), inliers=100),
        FrameAlignment(1, Alignment4Dof(-179.0, np.array([1.1, 0.0, 2.0])), inliers=200),
        FrameAlignment(2, Alignment4Dof(180.0, np.array([1.05, 0.0, 2.0])), inliers=100),
        FrameAlignment(3, Alignment4Dof(10.0, np.array([7.0, 0.0, 2.0])), inliers=300),
    ]
    c = consensus(items)
    assert c is not None
    assert sorted(c.agreeing_indices) == [0, 1, 2]
    assert yaw_diff_deg(c.alignment.yaw_deg, -179.75) < 0.05
    assert c.alignment.translation[0] == pytest.approx((100 * 1.0 + 200 * 1.1 + 100 * 1.05) / 400)

    # Seri jumlah anggota (2 vs 2): menang total inlier lebih tinggi
    tie_items = [
        FrameAlignment(0, Alignment4Dof(0.0, np.array([0.0, 0.0, 0.0])), inliers=60),
        FrameAlignment(1, Alignment4Dof(1.0, np.array([0.1, 0.0, 0.0])), inliers=60),
        FrameAlignment(2, Alignment4Dof(90.0, np.array([5.0, 0.0, 0.0])), inliers=150),
        FrameAlignment(3, Alignment4Dof(91.0, np.array([5.1, 0.0, 0.0])), inliers=150),
    ]
    c_tie = consensus(tie_items)
    assert c_tie is not None
    assert sorted(c_tie.agreeing_indices) == [2, 3]

    # Kurang dari 2 frame setuju -> None
    no_agree = [
        FrameAlignment(0, Alignment4Dof(0.0, np.array([0.0, 0.0, 0.0])), inliers=100),
        FrameAlignment(1, Alignment4Dof(0.0, np.array([2.0, 0.0, 0.0])), inliers=100),
        FrameAlignment(2, Alignment4Dof(20.0, np.array([0.0, 0.0, 0.0])), inliers=100),
    ]
    assert consensus(no_agree) is None


def test_localizer_localize_batch_batches_megaloc_and_aliked():
    loc = object.__new__(Localizer)
    loc.dev = torch.device("cpu")
    loc.resize = 64
    loc.global_resize = 32
    loc.k = 1
    loc.min_inliers = 50
    loc._align_source = lambda: None
    loc._align = type("NoAlign", (), {"get": lambda self: None})()
    loc.model = pycolmap.Reconstruction()
    p3d_id = loc.model.add_point3D(np.array([0.0, 0.0, 2.0]), pycolmap.Track())
    cam = pycolmap.Camera(model="PINHOLE", width=64, height=48, params=[50.0, 50.0, 32.0, 24.0])
    loc.map_camera = cam
    loc.db = {
        "a.jpg": {
            "id": 1,
            "keypoints": torch.zeros((1, 2, 2), dtype=torch.float32),
            "descriptors": torch.zeros((1, 2, 2), dtype=torch.float32),
            "size": (64, 48),
            "global": np.array([1.0, 0.0], dtype=np.float32),
            "center_model": np.array([0.0, 0.0, 0.0]),
            "points3D_ids": np.array([p3d_id, -1]),
        }
    }
    loc.db_names = ["a.jpg"]
    loc.db_global = np.array([[1.0, 0.0]], dtype=np.float32)

    mega_batches = []
    aliked_batches = []

    def fake_mega(inp):
        b = inp["image"].shape[0]
        mega_batches.append(b)
        return {"global_descriptor": torch.tensor([[1.0, 0.0]]).repeat(b, 1)}

    def fake_aliked(inp):
        b = inp["image"].shape[0]
        aliked_batches.append(b)
        return {
            "keypoints": [torch.tensor([[10.0, 10.0], [20.0, 20.0]]) for _ in range(b)],
            "descriptors": [torch.ones((2, 2)) for _ in range(b)],
        }

    loc.megaloc = fake_mega
    loc.aliked = fake_aliked
    loc.lightglue = lambda inp: {"matches0": torch.tensor([[0, -1]], dtype=torch.long)}
    loc.pnp = type(
        "FakePnP",
        (),
        {
            "localize": lambda self, pts2d, mkp, mp3d, camera: {
                "cam_from_world": pycolmap.Rigid3d(),
                "num_inliers": 80,
                "inlier_mask": np.ones(len(mp3d), dtype=bool),
            }
        },
    )()

    rgbs = [np.zeros((48, 64, 3), dtype=np.float32) for _ in range(4)]
    cams = [cam for _ in range(4)]
    results = loc.localize_batch(rgbs, cams)
    assert len(results) == 4
    assert all(r.ok for r in results)
    assert mega_batches == [4]
    assert aliked_batches == [4]


def test_localize_multi_endpoint_consensus_no_consensus_unaligned_and_logging(
    tmp_path, monkeypatch
):
    from server.app import app

    url = f"sqlite:///{tmp_path / 'multi.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)

    true_yaw = 20.0
    true_t = np.array([1.0, 0.0, 3.0])
    b_rot_g = _quat_axis_angle_xyzw([1, 0, 0], -90.0)  # menghadap +y_G -> +z_B
    ar_rot = _quat_axis_angle_xyzw([0, 1, 0], true_yaw)

    building_poses = [
        ([0.0, 0.0, 1.3], b_rot_g, 100),
        ([1.0, 0.0, 1.3], b_rot_g, 150),
        ([2.0, 0.0, 1.3], b_rot_g, 120),
        ([8.0, 0.0, 1.3], b_rot_g, 200),  # pencilan 6 m dari posisi AR sejati frame 3
    ]
    ar_positions = [
        (rot_y(true_yaw, g_to_b([0.0, 0.0, 1.3])) + true_t).tolist(),
        (rot_y(true_yaw, g_to_b([1.0, 0.0, 1.3])) + true_t).tolist(),
        (rot_y(true_yaw, g_to_b([2.0, 0.0, 1.3])) + true_t).tolist(),
        (rot_y(true_yaw, g_to_b([2.0, 0.0, 1.3])) + true_t).tolist(),  # pose gedung meleset 6 m
    ]

    class FakeMultiLoc:
        def __init__(self, aligned=True, poses=None):
            self.align = {"meter_from_model": {"scale": 1.0}} if aligned else None
            self.poses = poses or building_poses
            self._idx = 0

        def same_size_as_map(self, w, h):
            return False

        def localize_batch(self, rgbs, cameras):
            out = []
            for i in range(len(rgbs)):
                pos, rot, inl = self.poses[i]
                pose = pycolmap.Rigid3d(pycolmap.Rotation3d(np.array(rot)), np.array(pos)).inverse()
                out.append(
                    Result(
                        True,
                        inl,
                        inl + 50,
                        pose,
                        pos,
                        {"prep": 0.01, "total": 0.1},
                        reprojection_error_px_median=1.2,
                        retrieval_top1=0.88,
                        ambiguous=False,
                    )
                )
            return out

        def to_building(self, cam_from_world):
            if self.align is None:
                return None
            wfc = cam_from_world.inverse()
            return wfc.translation.tolist(), wfc.rotation.quat.tolist()

    app.state.lock = threading.Lock()
    app.state.area_id, app.state.map_version = "floor10", 5
    client = TestClient(app)

    frames_meta = [
        {
            "fx": 100.0,
            "fy": 100.0,
            "cx": 32.0,
            "cy": 24.0,
            "ar_position": ar_positions[i],
            "ar_rotation": ar_rot,
        }
        for i in range(4)
    ]
    png = _png_bytes()
    files = [(f"image_{i}", (f"f{i}.png", png, "image/png")) for i in range(4)]

    # 1. Peta belum selaras -> 409
    app.state.localizer = FakeMultiLoc(aligned=False)
    r409 = client.post("/localize-multi", files=files, data={"frames": json.dumps(frames_meta)})
    assert r409.status_code == 409

    # 2. Kurang dari 2 gambar -> 422
    app.state.localizer = FakeMultiLoc(aligned=True)
    r422 = client.post(
        "/localize-multi",
        files=[("image_0", ("f0.png", png, "image/png"))],
        data={"frames": json.dumps(frames_meta[:1])},
    )
    assert r422.status_code == 422

    # 3. 3 dari 4 setuju -> 200 ok + konsensus + 1 baris log
    r_ok = client.post("/localize-multi", files=files, data={"frames": json.dumps(frames_meta)})
    assert r_ok.status_code == 200
    body = r_ok.json()
    assert body["status"] == "ok"
    assert body["frames_agreeing"] == 3
    assert body["frames_total"] == 4
    assert yaw_diff_deg(body["alignment"]["yaw_deg"], true_yaw) < 1e-2
    assert np.allclose(body["alignment"]["translation"], true_t, atol=1e-2)
    assert len(body["frames"]) == 4
    assert body["inliers"] == 150  # frame terbaik di dalam klaster yang setuju (bukan pencilan 200)
    assert body["pose_building"] is not None
    assert body["inlier_ratio"] == pytest.approx(150 / 200, abs=1e-3)

    # 4. Tidak ada konsensus -> status not_found, reason no_consensus
    scattered = [
        ([0.0, 0.0, 1.3], b_rot_g, 100),
        ([10.0, 0.0, 1.3], b_rot_g, 100),
        ([20.0, 0.0, 1.3], b_rot_g, 100),
        ([30.0, 0.0, 1.3], b_rot_g, 100),
    ]
    app.state.localizer = FakeMultiLoc(aligned=True, poses=scattered)
    r_nc = client.post("/localize-multi", files=files, data={"frames": json.dumps(frames_meta)})
    assert r_nc.status_code == 200
    nc_body = r_nc.json()
    assert nc_body["status"] == "not_found"
    assert nc_body["reason"] == "no_consensus"
    assert nc_body["alignment"] is None
    assert nc_body["frames_agreeing"] == 0

    with Session(engine) as s:
        logged = s.exec(select(LocalizeRequest).order_by(LocalizeRequest.id)).all()
    ok_rows = [row for row in logged if row.result == "ok"]
    nc_rows = [row for row in logged if row.result == "not_found"]
    assert len(ok_rows) == 1
    assert ok_rows[0].inliers == 100 + 150 + 120 + 200
    assert ok_rows[0].t_s["frames_agreeing"] == 3
    assert len(nc_rows) == 1
    assert nc_rows[0].t_s["frames_agreeing"] == 0

    localize_log._engine(url).dispose()
    engine.dispose()
