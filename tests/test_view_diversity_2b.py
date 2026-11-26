"""Uji fase 2b server: view_spread_deg dan view_diverse pada /localize-multi."""

import io
import json
import math
import threading

import numpy as np
import pycolmap
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, create_engine, select

from server import localize_log
from server.align4dof import (
    MIN_VIEW_SPREAD_DEG,
    ar_heading_deg,
    g_to_b,
    is_view_diverse,
    rot_y,
    view_spread_deg,
)
from server.db import LocalizeRequest
from server.localizer import Result


def _png_bytes(w=64, h=48) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (50, 90, 120)).save(buf, "PNG")
    return buf.getvalue()


def _q_axis(axis, deg: float) -> list[float]:
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    h = math.radians(deg) / 2.0
    s = math.sin(h)
    return [float(a[0] * s), float(a[1] * s), float(a[2] * s), float(math.cos(h))]


def test_view_spread_deg_handles_wrap_vertical_and_threshold():
    assert MIN_VIEW_SPREAD_DEG == pytest.approx(20.0)
    # Kurang dari 2 heading sah -> None, tidak diverse
    assert view_spread_deg([]) is None
    assert view_spread_deg([10.0]) is None
    assert view_spread_deg([10.0, None]) is None
    assert is_view_diverse(None) is False

    # Lintas batas +-180: 170 dan -170 berjarak 20 deg (>= 20 -> diverse)
    spread = view_spread_deg([170.0, -170.0, 175.0])
    assert spread == pytest.approx(20.0, abs=1e-4)
    assert is_view_diverse(spread) is True

    # Arah hampir sama (selisih 12 deg < 20 -> tidak diverse)
    narrow = view_spread_deg([10.0, 15.0, 22.0])
    assert narrow == pytest.approx(12.0, abs=1e-4)
    assert is_view_diverse(narrow) is False

    # Kamera terlalu vertikal tidak punya heading
    assert ar_heading_deg(_q_axis([1, 0, 0], 85.0)) is None
    assert ar_heading_deg(_q_axis([0, 1, 0], 35.0)) == pytest.approx(35.0, abs=1e-4)


def test_localize_multi_reports_and_logs_view_diversity(tmp_path, monkeypatch):
    from server.app import app

    url = f"sqlite:///{tmp_path / 'multi2b.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)

    true_yaw = 20.0
    true_t = np.array([1.0, 0.0, 3.0])

    def build_request(yaws_u: list[float]):
        # Untuk setiap yaw_u, hitung rotasi gedung b_rot_g yang konsisten dengan true_yaw
        b_poses = []
        frames_meta = []
        for idx, yu in enumerate(yaws_u):
            yb = yu - true_yaw
            # Di G: rotasi Z sebesar -yb dari +Y_G (q_x(-90)) memutar +Z_cam ke arah yaw_B = yb
            # RotZ(-yb) pada +Y_G = (sin(yb), cos(yb), 0) -> B = (sin(yb), 0, cos(yb)) -> yaw = yb
            b_yaw_rot = pycolmap.Rotation3d(np.array(_q_axis([0, 0, 1], -yb)))
            b_base = pycolmap.Rotation3d(np.array(_q_axis([1, 0, 0], -90.0)))
            b_rot_g = (b_yaw_rot * b_base).quat.tolist()
            b_pos = [float(idx) * 0.5, 0.0, 1.3]
            ar_pos = (rot_y(true_yaw, g_to_b(b_pos)) + true_t).tolist()
            ar_rot = _q_axis([0, 1, 0], yu)
            b_poses.append((b_pos, b_rot_g, 100 + idx * 10))
            frames_meta.append(
                {
                    "fx": 100.0,
                    "fy": 100.0,
                    "cx": 32.0,
                    "cy": 24.0,
                    "ar_position": ar_pos,
                    "ar_rotation": ar_rot,
                }
            )
        return b_poses, frames_meta

    class FakeLoc:
        def __init__(self, poses):
            self.align = {"meter_from_model": {"scale": 1.0}}
            self.poses = poses

        def same_size_as_map(self, w, h):
            return False

        def localize_batch(self, rgbs, cameras):
            out = []
            for pos, rot, inl in self.poses:
                pose = pycolmap.Rigid3d(pycolmap.Rotation3d(np.array(rot)), np.array(pos)).inverse()
                out.append(Result(True, inl, inl + 50, pose, pos, {"total": 0.05}))
            return out

        def to_building(self, cam_from_world):
            wfc = cam_from_world.inverse()
            return wfc.translation.tolist(), wfc.rotation.quat.tolist()

    app.state.lock = threading.Lock()
    app.state.area_id, app.state.map_version = "floor10", 5
    client = TestClient(app)
    png = _png_bytes()
    files = [(f"image_{i}", (f"f{i}.png", png, "image/png")) for i in range(3)]

    # 1. Diverse: 0, 15, 32 deg -> spread 32 deg >= 20 -> view_diverse True, status ok
    poses_div, meta_div = build_request([0.0, 15.0, 32.0])
    app.state.localizer = FakeLoc(poses_div)
    r1 = client.post("/localize-multi", files=files, data={"frames": json.dumps(meta_div)})
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["status"] == "ok"
    assert b1["view_spread_deg"] == pytest.approx(32.0, abs=0.1)
    assert b1["view_diverse"] is True

    # 2. Non-diverse: 10, 14, 18 deg -> spread 8 deg < 20 -> view_diverse False, status tetap ok
    poses_nar, meta_nar = build_request([10.0, 14.0, 18.0])
    app.state.localizer = FakeLoc(poses_nar)
    r2 = client.post("/localize-multi", files=files, data={"frames": json.dumps(meta_nar)})
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["status"] == "ok"
    assert b2["view_spread_deg"] == pytest.approx(8.0, abs=0.1)
    assert b2["view_diverse"] is False

    with Session(engine) as s:
        logged = s.exec(select(LocalizeRequest).order_by(LocalizeRequest.id)).all()
    assert len(logged) == 2
    assert logged[0].t_s["view_spread_deg"] == pytest.approx(32.0, abs=0.1)
    assert logged[0].t_s["view_diverse"] is True
    assert logged[1].t_s["view_spread_deg"] == pytest.approx(8.0, abs=0.1)
    assert logged[1].t_s["view_diverse"] is False

    localize_log._engine(url).dispose()
    engine.dispose()
