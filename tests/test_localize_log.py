"""Catatan permintaan /localize (roadmap M1-6): hasil dan waktu, tanpa gambar dan tanpa pose."""

import io
import threading

import pycolmap
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, create_engine, select

from server import localize_log
from server.db import LocalizeRequest
from server.localizer import Result


@pytest.fixture
def db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'log.db'}"
    SQLModel.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    return url


def rows(url):
    with Session(create_engine(url)) as s:
        return s.exec(select(LocalizeRequest).order_by(LocalizeRequest.id)).all()


def test_record_stores_the_entry(db):
    localize_log.record(
        {
            "result": "ok",
            "http_status": 200,
            "area_id": "floor10",
            "map_version": 3,
            "inliers": 215,
            "correspondences": 400,
            "intrinsics_source": "client",
            "t_s": {"prep": 0.01, "total": 0.38},
            "wall_s": 0.5,
            "image_w": 640,
            "image_h": 480,
        }
    )
    [r] = rows(db)
    assert (r.result, r.http_status, r.area_id, r.map_version) == ("ok", 200, "floor10", 3)
    assert (r.inliers, r.t_s["total"], r.wall_s, r.image_w) == (215, 0.38, 0.5, 640)
    assert r.created_at is not None


def test_record_without_database_does_nothing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    localize_log.record({"result": "ok", "http_status": 200})  # tidak melempar


def test_record_never_breaks_the_request_when_the_database_is_broken(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'nope' / 'x.db'}")
    localize_log.record({"result": "ok", "http_status": 200})  # tidak melempar


def test_old_rows_are_pruned(db, monkeypatch):
    monkeypatch.setattr(localize_log, "KEEP", 5)
    monkeypatch.setattr(localize_log, "PRUNE_EVERY", 4)
    for _ in range(12):
        localize_log.record({"result": "ok", "http_status": 200})
    assert [r.id for r in rows(db)] == [8, 9, 10, 11, 12]


def png(w=64, h=48) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 80, 40)).save(buf, "PNG")
    return buf.getvalue()


class FakeLocalizer:
    def __init__(self, result):
        self.result = result

    def same_size_as_map(self, w, h):
        return False

    def localize(self, rgb, camera):
        return self.result

    def to_building(self, cam_from_world):
        return None


@pytest.fixture
def client(db):
    from server.app import app

    st = app.state
    st.lock = threading.Lock()
    st.area_id, st.map_version = "floor10", 2
    st.localizer = FakeLocalizer(Result(False, 7, 30, None, None, {"total": 0.2}))
    return TestClient(app)


def post(client, data, **form):
    return client.post("/localize", files={"image": ("q.png", data, "image/png")}, data=form)


FX = {"fx": "100", "fy": "100", "cx": "32", "cy": "24"}


def test_failed_localization_is_logged(client, db):
    assert post(client, png(), **FX).json()["status"] == "failed"
    [r] = rows(db)
    assert (r.result, r.http_status, r.area_id, r.map_version) == ("failed", 200, "floor10", 2)
    assert (r.inliers, r.correspondences, r.intrinsics_source) == (7, 30, "client")
    assert (r.image_w, r.image_h) == (64, 48) and r.t_s == {"total": 0.2}
    assert r.wall_s >= 0


def test_successful_localization_is_logged_without_the_pose(client, db):
    client.app.state.localizer = FakeLocalizer(
        Result(True, 215, 400, pycolmap.Rigid3d(), [1.0, 2.0, 3.0], {"total": 0.4})
    )
    assert post(client, png(), **FX).json()["status"] == "ok"
    [r] = rows(db)
    assert (r.result, r.inliers) == ("ok", 215)
    assert "1.0" not in str(r.model_dump())  # posisi pengguna tidak disimpan


def test_rejected_requests_are_logged_with_the_reason(client, db):
    assert post(client, b"bukan gambar").status_code == 400
    assert post(client, png(), fx="100").status_code == 422
    client.app.state.localizer = None
    assert post(client, png(), **FX).status_code == 503
    assert [(r.result, r.http_status) for r in rows(db)] == [
        ("rejected", 400),
        ("rejected", 422),
        ("rejected", 503),
    ]
    assert "no published map" in rows(db)[2].reason


def test_localization_still_answers_when_the_log_fails(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db mati")

    monkeypatch.setattr(localize_log, "Session", boom)
    assert post(client, png(), **FX).status_code == 200


def test_api_lists_newest_first_and_honours_the_limit(client, db):
    for _ in range(3):
        post(client, png(), **FX)
    got = client.get("/api/localize-log?limit=2").json()
    assert [g["id"] for g in got] == [3, 2]
    assert "t_s" in got[0] and "pose_model" not in got[0]


def test_api_rejects_a_silly_limit(client, db):
    assert client.get("/api/localize-log?limit=0").status_code == 422
    assert client.get("/api/localize-log?limit=100000").status_code == 422
