"""Uji API dashboard dengan SQLite, mode autentikasi uji, dan pemuat peta palsu."""

import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server import active_map, auth, jobs, maps_api, uploads
from server.db import MapJob, publish, register


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
    raise AssertionError("pemuatan ulang tidak selesai")


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
    r = client.post(f"/api/versions/{v.id}/publish", json={}).json()
    assert r["reload"] == "started"
    wait_reload(client.st)
    row = client.get("/api/versions").json()[0]
    assert (row["status"], row["published_by"]) == ("published", "dev@local")
    s = client.get("/api/service").json()
    assert (s["area_id"], s["map_version"], s["reload_error"]) == ("floor10", v.version, None)
    assert client.st.localizer.startswith("loc:job-")


def test_publish_other_area_does_not_reload(client):
    v = make_version(client, area="floor9")
    r = client.post(f"/api/versions/{v.id}/publish", json={}).json()
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
    assert client.post(f"/api/versions/{v.id}/publish", json={}).status_code == 409
    assert client.get("/api/versions").json()[0]["status"] == "candidate"


def test_publish_rejects_cross_site_form(client):
    # Formulir lintas situs tidak bisa mengirim application/json tanpa preflight CORS (yang tidak
    # diizinkan), jadi tipe isi ini menutup CSRF lewat cookie Access.
    v = make_version(client, area="floor9")
    form = client.post(f"/api/versions/{v.id}/publish", data={"x": "1"})
    empty = client.post(f"/api/versions/{v.id}/publish")
    assert (form.status_code, empty.status_code) == (415, 415)
    assert client.get("/api/versions").json()[0]["status"] == "candidate"
    ok = client.post(f"/api/versions/{v.id}/publish", json={})
    assert ok.json()["reload"] == "other_area"


def test_jobs_from_cli_are_listed(client):
    # manage job (CLI) menyimpan video hanya dengan path dan role. Satu baris lama seperti ini
    # sempat membuat seluruh GET /api/jobs gagal 500 di PC lab (2026-10-03).
    jobs.create_job(
        client.db,
        "floor10",
        "L10",
        "cli",
        [{"path": "/data/inbox/a.mp4", "role": "peta"}],
        "queued",
    )
    videos = client.get("/api/jobs").json()[0]["videos"]
    assert videos == [
        {"name": "a.mp4", "role": "peta", "size": None, "uploaded": None, "recorded_at": None}
    ]


def only_job_id(client):
    return client.get("/api/jobs").json()[0]["id"]


def test_jobs_expose_dates(client):
    make_version(client)
    j = client.get("/api/jobs").json()[0]
    assert j["created_at"] and j["finished_at"]
    assert "started_at" in j  # null untuk pekerjaan yang tidak lewat pekerja


def test_me_reports_email_and_admin(client):
    assert client.get("/api/me").json() == {"email": "dev@local", "is_admin": True}


def test_me_for_a_non_admin(client, monkeypatch):
    monkeypatch.setenv("EUTOPOS_ADMINS", "boss@x.id")
    client.app.dependency_overrides[auth.current_user] = lambda: "tamu@x.id"
    assert client.get("/api/me").json() == {"email": "tamu@x.id", "is_admin": False}


def test_delete_needs_admin(client, monkeypatch):
    make_version(client)
    jid = only_job_id(client)
    monkeypatch.setenv("EUTOPOS_ADMINS", "boss@x.id")
    client.app.dependency_overrides[auth.current_user] = lambda: "tamu@x.id"
    assert client.delete(f"/api/jobs/{jid}").status_code == 403
    assert client.get(f"/api/jobs/{jid}").json()["status"] == "done"


def test_delete_only_marks_the_job_and_never_touches_disk(client):
    # api memasang /maps hanya-baca: penghapusan sungguhan dikerjakan pekerja.
    v = make_version(client)
    jid = only_job_id(client)
    r = client.delete(f"/api/jobs/{jid}")
    assert r.status_code == 202 and r.json() == {"status": "deleting"}
    assert client.get(f"/api/jobs/{jid}").json()["status"] == "deleting"
    assert (client.maps / "floor10").exists() and v.path
    assert client.delete(f"/api/jobs/{jid}").status_code == 202  # diulang aman


def test_delete_unknown_job_is_404(client):
    assert client.delete("/api/jobs/999").status_code == 404


@pytest.mark.parametrize("status", ["uploading", "queued", "running"])
def test_delete_refuses_unfinished_jobs(client, status):
    j = jobs.create_job(
        client.db,
        "floor10",
        "L10",
        "dev@local",
        [{"name": "a.mp4", "role": "peta", "size": 1}],
        status=status,
    )
    r = client.delete(f"/api/jobs/{j.id}")
    assert r.status_code == 409 and status in r.json()["detail"]


def test_delete_refuses_a_published_version(client):
    v = make_version(client)
    publish(client.db, v.id, by="dev@local")
    jid = only_job_id(client)
    r = client.delete(f"/api/jobs/{jid}")
    assert r.status_code == 409 and "published" in r.json()["detail"]
    assert client.get(f"/api/jobs/{jid}").json()["status"] == "done"


def test_publish_is_refused_while_its_job_is_being_deleted(client):
    v = make_version(client)
    client.delete(f"/api/jobs/{only_job_id(client)}")
    r = client.post(
        f"/api/versions/{v.id}/publish", json={}, headers={"content-type": "application/json"}
    )
    assert r.status_code == 409 and "deleted" in r.json()["detail"]


WHEN_ISO = "2026-10-01T04:15:49+00:00"
JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"preview" * 20


def job_with_preview(client, area="floor10", write=True):
    j = jobs.create_job(
        client.db, area, "L10", "dev@local", [{"name": "a.mp4", "role": "peta", "size": 1}]
    )
    if write:
        d = client.maps / area / f"job-{j.id}"
        d.mkdir(parents=True)
        (d / "preview.jpg").write_bytes(JPEG)
    return j


def test_preview_is_served_as_a_cached_jpeg(client):
    j = job_with_preview(client)
    r = client.get(f"/api/jobs/{j.id}/preview")
    assert r.status_code == 200 and r.content == JPEG
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "private, max-age=3600"


def test_preview_is_404_when_missing_or_job_unknown(client):
    j = job_with_preview(client, write=False)
    assert client.get(f"/api/jobs/{j.id}/preview").status_code == 404
    assert client.get("/api/jobs/999/preview").status_code == 404


def test_preview_never_leaves_the_maps_folder(client):
    # area_id dari baris yang rusak (atau CLI) tidak boleh menyeret berkas di luar /maps.
    outside = client.maps.parent / "outside"
    j = MapJob(area_id="../outside", created_by="a@x.id", status="done", videos=[])
    client.db.add(j)
    client.db.commit()
    (outside / f"job-{j.id}").mkdir(parents=True)
    (outside / f"job-{j.id}" / "preview.jpg").write_bytes(b"rahasia")
    assert client.get(f"/api/jobs/{j.id}/preview").status_code == 404
    assert client.get(f"/api/jobs/{j.id}").json()["has_preview"] is False


def test_jobs_say_whether_they_have_a_preview(client):
    with_p = job_with_preview(client)
    without = job_with_preview(client, write=False)
    flags = {j["id"]: j["has_preview"] for j in client.get("/api/jobs").json()}
    assert flags == {with_p.id: True, without.id: False}
    assert client.get(f"/api/jobs/{with_p.id}").json()["has_preview"] is True


def test_recorded_time_is_exposed_per_video(client):
    jobs.create_job(
        client.db,
        "floor10",
        "L10",
        "dev@local",
        [
            {"name": "a.mp4", "role": "peta", "size": 1, "recorded_at": WHEN_ISO},
            {"name": "b.mp4", "role": "uji", "size": 1, "recorded_at": None},
            {"name": "c.mp4", "role": "uji", "size": 1},  # pekerjaan lama: tanpa kunci sama sekali
        ],
    )
    videos = client.get("/api/jobs").json()[0]["videos"]
    assert videos[0]["recorded_at"].startswith("2026-10-01T04:15:49")
    assert videos[1]["recorded_at"] is None and videos[2]["recorded_at"] is None
