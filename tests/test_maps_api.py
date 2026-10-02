"""Uji API dashboard dengan SQLite, mode autentikasi uji, dan pemuat peta palsu."""

import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server import active_map, jobs, maps_api, uploads
from server.db import register


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    SQLModel.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.setenv("EUTOPOS_AREA", "floor10")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    monkeypatch.setattr(maps_api, "MAPS_ROOT", tmp_path / "maps")
    monkeypatch.setattr(active_map, "load_localizer", lambda path: f"loc:{path.name}")
    app = FastAPI()
    app.include_router(uploads.router)
    app.include_router(maps_api.router)
    st = app.state
    st.localizer, st.area_id, st.map_version, st.lock = None, None, None, threading.Lock()
    st.reloading, st.reload_error = False, None
    with TestClient(app) as c:
        c.db = Session(create_engine(url))
        c.maps = tmp_path / "maps"
        c.st = st
        yield c


def make_version(client, area="floor10", job=True, report=True):
    d = client.maps / area / f"job-{len(list(client.maps.glob('*/*'))) + 1}"
    d.mkdir(parents=True)
    if report:
        (d / "report.html").write_text("<html>laporan</html>")
    v = register(client.db, area, "Lantai 10", str(d))
    if job:
        j = jobs.create_job(
            client.db, area, "L10", "dev@local", [{"name": "a.mp4", "role": "peta", "size": 1}]
        )
        jobs.finish(client.db, j, v.id, {"inspect": {"parts": []}})
    return v


def wait_reload(st):
    for _ in range(100):
        if not st.reloading:
            return
        time.sleep(0.02)


def test_lists_jobs_newest_first(client):
    make_version(client)
    make_version(client)
    ids = [j["id"] for j in client.get("/api/jobs").json()]
    assert ids == sorted(ids, reverse=True) and len(ids) == 2


def test_versions_have_job_and_report(client):
    v = make_version(client)
    make_version(client, job=False, report=False)
    rows = {r["id"]: r for r in client.get("/api/versions").json()}
    assert rows[v.id]["job_id"] is not None and rows[v.id]["has_report"] is True
    assert client.get(f"/api/versions/{v.id}/report").text == "<html>laporan</html>"


def test_report_outside_maps_root_is_404(client, tmp_path):
    outside = tmp_path / "rahasia"
    outside.mkdir()
    (outside / "report.html").write_text("jangan")
    v = register(client.db, "floor10", "L10", str(outside))
    assert client.get(f"/api/versions/{v.id}/report").status_code == 404


def test_publish_reloads_served_area(client):
    v = make_version(client)
    r = client.post(f"/api/versions/{v.id}/publish").json()
    assert r["reload"] == "started" and r["version"]["published_by"] == "dev@local"
    wait_reload(client.st)
    s = client.get("/api/service").json()
    assert (s["area_id"], s["map_version"], s["reload_error"]) == ("floor10", v.version, None)
    assert client.st.localizer.startswith("loc:job-")


def test_publish_other_area_does_not_reload(client):
    v = make_version(client, area="floor9")
    r = client.post(f"/api/versions/{v.id}/publish").json()
    assert r["reload"] == "other_area" and r["version"]["status"] == "published"
    assert client.st.localizer is None


def test_plotly_asset_is_served(client):
    r = client.get("/assets/plotly.min.js")
    assert r.status_code == 200 and len(r.content) > 1_000_000


def test_publish_while_reloading_is_409(client):
    # Dua pemuatan bersamaan bisa saling timpa: yang gagal mengembalikan versi lama di database
    # sementara yang lain sudah menukar peta.
    v = make_version(client)
    client.st.reloading = True
    assert client.post(f"/api/versions/{v.id}/publish").status_code == 409
    assert client.get("/api/versions").json()[0]["status"] == "candidate"
