"""Uji R9: skor kepercayaan lebih kaya pada hasil lokalisasi dan log."""

import io
import threading

import numpy as np
import pycolmap
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, create_engine, select

from server import localize_log
from server.db import LocalizeRequest
from server.localizer import (
    AMBIGUOUS_DISTANCE_M,
    AMBIGUOUS_SCORE_DELTA,
    Result,
    compute_inlier_ratio,
    median_reprojection_error_px,
    retrieval_is_ambiguous,
)


def test_inlier_ratio_null_when_zero_correspondences():
    assert compute_inlier_ratio(0, 0) is None
    assert compute_inlier_ratio(50, 100) == pytest.approx(0.5)
    assert compute_inlier_ratio(25, 100) == pytest.approx(0.25)


def test_median_reprojection_error_over_pnp_inliers():
    cam = pycolmap.Camera(
        model="PINHOLE", width=640, height=480, params=[500.0, 500.0, 320.0, 240.0]
    )
    pose = pycolmap.Rigid3d()
    pts3d = np.array(
        [[0.0, 0.0, 2.0], [0.5, 0.0, 2.0], [0.0, 0.5, 2.0], [-0.5, -0.5, 2.0]], dtype=np.float64
    )
    proj = cam.img_from_cam(pts3d)
    # 3 inlier dengan galat 1 px, 2 px, 3 px + 1 outlier dengan galat 50 px
    offsets = np.array([[1.0, 0.0], [0.0, 2.0], [3.0, 0.0], [50.0, 0.0]], dtype=np.float64)
    pts2d = proj + offsets
    mask = np.array([True, True, True, False])

    med = median_reprojection_error_px(pose, pts2d, pts3d, mask, cam)
    assert med == pytest.approx(2.0, abs=1e-4)
    assert median_reprojection_error_px(None, pts2d, pts3d, mask, cam) is None
    assert median_reprojection_error_px(pose, pts2d, pts3d, np.zeros(4, dtype=bool), cam) is None


def test_retrieval_ambiguity_threshold_with_and_without_alignment():
    assert AMBIGUOUS_SCORE_DELTA == pytest.approx(0.02)
    assert AMBIGUOUS_DISTANCE_M == pytest.approx(5.0)

    scores = np.array([0.85, 0.84, 0.60], dtype=np.float32)
    far_centers = [np.array([0.0, 0.0, 0.0]), np.array([3.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])]
    # Skala 2.0 -> jarak 6 m (> 5 m) dan selisih skor 0.01 (<= 0.02) -> ambigu
    assert retrieval_is_ambiguous(scores, far_centers, scale_m=2.0) is True
    # Skala 1.0 -> jarak 3 m (<= 5 m) -> tidak ambigu
    assert retrieval_is_ambiguous(scores, far_centers, scale_m=1.0) is False
    # Tidak selaras (scale None) -> tidak bisa dihitung dalam meter -> False
    assert retrieval_is_ambiguous(scores, far_centers, scale_m=None) is False
    # Selisih skor > 0.02 -> tidak ambigu walau jauh
    distinct_scores = np.array([0.85, 0.80, 0.60], dtype=np.float32)
    assert retrieval_is_ambiguous(distinct_scores, far_centers, scale_m=2.0) is False


def test_localize_response_and_log_include_r9_fields(tmp_path, monkeypatch):
    from server.app import app

    url = f"sqlite:///{tmp_path / 'r9.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)

    class StubLoc:
        align = None

        def same_size_as_map(self, w, h):
            return False

        def localize(self, rgb, camera, **kwargs):
            return Result(
                True,
                100,
                200,
                pycolmap.Rigid3d(),
                [1.0, 2.0, 3.0],
                {"prep": 0.01, "total": 0.25},
                inlier_ratio=0.5,
                reprojection_error_px_median=1.42,
                retrieval_top1=0.8123,
                ambiguous=True,
            )

        def to_building(self, cam_from_world):
            return None

    st = app.state
    st.lock = threading.Lock()
    st.area_id, st.map_version = "floor10", 3
    st.localizer = StubLoc()

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 20, 30)).save(buf, "PNG")
    resp = TestClient(app).post(
        "/localize",
        files={"image": ("q.png", buf.getvalue(), "image/png")},
        data={"fx": "100", "fy": "100", "cx": "32", "cy": "24"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["inlier_ratio"] == pytest.approx(0.5)
    assert body["reprojection_error_px_median"] == pytest.approx(1.42)
    assert body["retrieval_top1"] == pytest.approx(0.8123)
    assert body["ambiguous"] is True
    # t_s di respons API tetap murni timing float
    assert "inlier_ratio" not in body["t_s"]
    assert "ambiguous" not in body["t_s"]

    with Session(engine) as s:
        [row] = s.exec(select(LocalizeRequest)).all()
    assert row.t_s["inlier_ratio"] == pytest.approx(0.5)
    assert row.t_s["ambiguous"] is True

    localize_log._engine(url).dispose()
    engine.dispose()
