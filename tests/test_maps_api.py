"""Uji API dashboard dengan SQLite, mode autentikasi uji, dan pemuat peta palsu."""

import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server import active_map, auth, jobs, maps_api, uploads
from server.db import Alignment, MapJob, publish, register


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
    monkeypatch.setattr(active_map, "load_localizer", lambda path, **kw: f"loc:{path.name}")
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
        {
            "name": "a.mp4",
            "role": "peta",
            "size": None,
            "uploaded": None,
            "recorded_at": None,
            "received": None,
            "activity_at": None,
        }
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
    expected = "upload is still receiving data" if status == "uploading" else f"job is {status}"
    assert r.status_code == 409 and expected in r.json()["detail"]


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


def version_ids(client):
    return [v["id"] for v in client.get("/api/versions").json()]


def as_guest(client, monkeypatch):
    monkeypatch.setenv("EUTOPOS_ADMINS", "boss@x.id")
    client.app.dependency_overrides[auth.current_user] = lambda: "tamu@x.id"


def test_delete_version_needs_admin(client, monkeypatch):
    v = make_version(client)
    as_guest(client, monkeypatch)
    assert client.delete(f"/api/versions/{v.id}").status_code == 403
    assert v.id in version_ids(client)


def test_delete_unknown_version_is_404(client):
    assert client.delete("/api/versions/999").status_code == 404


def test_delete_refuses_the_published_version(client):
    v = make_version(client)
    publish(client.db, v.id, by="dev@local")
    r = client.delete(f"/api/versions/{v.id}")
    assert r.status_code == 409 and "published" in r.json()["detail"]
    assert v.id in version_ids(client)


def test_delete_refuses_a_published_version_that_has_no_job(client):
    # Versi dari CLI tidak punya job yang bisa menolak: pengaman milik versi satu-satunya penjaga.
    v = make_version(client, job=False)
    publish(client.db, v.id, by="dev@local")
    r = client.delete(f"/api/versions/{v.id}")
    assert r.status_code == 409 and "published" in r.json()["detail"]
    assert v.id in version_ids(client)


def test_delete_version_with_a_job_hands_the_job_to_the_worker(client):
    # Sama dengan Delete di Jobs: api memasang /maps hanya-baca, pekerja yang menghapus berkas.
    v = make_version(client)
    jid = only_job_id(client)
    r = client.delete(f"/api/versions/{v.id}")
    assert r.status_code == 202 and r.json() == {"status": "deleting", "job_id": jid}
    assert client.get(f"/api/jobs/{jid}").json()["status"] == "deleting"
    assert v.id in version_ids(client)  # barisnya baru hilang setelah pekerja selesai
    assert client.delete(f"/api/versions/{v.id}").status_code == 202  # diulang aman


def test_delete_version_of_a_retired_map_with_a_job(client):
    old = make_version(client)
    new = make_version(client)
    publish(client.db, old.id, by="dev@local")
    publish(client.db, new.id, by="dev@local")  # old menjadi retired
    assert client.delete(f"/api/versions/{old.id}").status_code == 202


def test_delete_version_without_a_job_removes_only_the_row(client):
    # Peta dari CLI milik pemiliknya: barisnya hilang, berkasnya tidak pernah disentuh.
    v = make_version(client, job=False)
    r = client.delete(f"/api/versions/{v.id}")
    assert r.status_code == 200 and r.json() == {"status": "deleted"}
    assert v.id not in version_ids(client)
    assert any((client.maps / "floor10").rglob("report.html"))


def test_deleted_version_cannot_be_published(client):
    v = make_version(client, job=False)
    client.delete(f"/api/versions/{v.id}")
    r = client.post(
        f"/api/versions/{v.id}/publish", json={}, headers={"content-type": "application/json"}
    )
    assert r.status_code == 404


def test_has_splat_false_when_missing_and_404(client):
    v = make_version(client)
    rows = {r["id"]: r for r in client.get("/api/versions").json()}
    assert rows[v.id]["has_splat"] is False
    r = client.get(f"/api/versions/{v.id}/splat")
    assert r.status_code == 404
    assert r.json()["detail"] == "splat not found"


def test_splat_served_when_present(client):
    v = make_version(client)
    splat_dir = Path(v.path) / "splat"
    splat_dir.mkdir(parents=True, exist_ok=True)
    content = b"PK\x03\x04dummy-sog-bytes"
    (splat_dir / "scene.sog").write_bytes(content)
    rows = {r["id"]: r for r in client.get("/api/versions").json()}
    assert rows[v.id]["has_splat"] is True
    r = client.get(f"/api/versions/{v.id}/splat")
    assert r.status_code == 200
    assert r.content == content


def test_splat_requires_auth(client, monkeypatch):
    v = make_version(client)
    splat_dir = Path(v.path) / "splat"
    splat_dir.mkdir(parents=True, exist_ok=True)
    (splat_dir / "scene.sog").write_bytes(b"splat-data")
    monkeypatch.delenv("EUTOPOS_DEV_NO_AUTH", raising=False)
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "https://test.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", "test-aud")
    assert client.get(f"/api/versions/{v.id}/splat").status_code == 401
    assert client.get(f"/api/versions/{v.id}/splat/placement").status_code == 401


def test_placement_404_not_aligned(client):
    v = make_version(client)
    r = client.get(f"/api/versions/{v.id}/splat/placement")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_aligned"


def test_placement_200_when_aligned_in_db(client):
    v = make_version(client)
    align_params = {
        "meter_from_model": {
            "scale": 1.0,
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
            "translation": [0.0, 0.0, 0.0],
        },
        "reference_points": 4,
        "residual_median_m": 0.05,
    }
    row = Alignment(
        map_version_id=v.id,
        params=align_params,
        stats={},
        status="applied",
        source="fit",
        created_by="dev@local",
    )
    client.db.add(row)
    client.db.commit()
    r = client.get(f"/api/versions/{v.id}/splat/placement")
    assert r.status_code == 200
    data = r.json()
    assert data["scale"] == 1.0
    assert len(data["position"]) == 3
    assert len(data["rotation_xyzw"]) == 4


# --- Tiket agy 13: Task 7 tests ---


@pytest.mark.parametrize("status", ["queued", "running", "failed", "done"])
def test_splat_status_is_null_without_a_row_and_reflects_the_row(client, status):
    from server import splat_jobs

    v = make_version(client)
    row = client.get("/api/versions").json()[0]
    assert row["splat_status"] is None
    assert row["splat_stage"] is None
    assert row["splat_error"] is None

    sj = splat_jobs.enqueue(client.db, v.id)
    splat_jobs.set_stage(client.db, sj, "prepare")
    if status == "running":
        splat_jobs.claim_next(client.db)
        splat_jobs.set_stage(client.db, sj, "train")
    elif status == "failed":
        claimed = splat_jobs.claim_next(client.db)
        splat_jobs.set_stage(client.db, claimed, "train")
        splat_jobs.fail(client.db, claimed, "train failed")
    elif status == "done":
        claimed = splat_jobs.claim_next(client.db)
        splat_jobs.set_stage(client.db, claimed, "place")
        splat_jobs.finish(client.db, claimed, {"out": 1})

    row = client.get("/api/versions").json()[0]
    assert row["splat_status"] == status
    if status == "running":
        assert row["splat_stage"] == "train"
    elif status == "failed":
        assert row["splat_stage"] == "train"
    elif status == "done":
        assert row["splat_stage"] == "place"
    elif status == "queued":
        assert row["splat_stage"] == "prepare"


def test_splat_error_only_for_failed_rows(client):
    from server import splat_jobs

    v = make_version(client)
    splat_jobs.enqueue(client.db, v.id)
    claimed = splat_jobs.claim_next(client.db)
    splat_jobs.fail(client.db, claimed, "oom error")
    row = client.get("/api/versions").json()[0]
    assert row["splat_status"] == "failed"
    assert row["splat_error"] == "oom error"

    # Done row with old error column content must yield splat_error = None
    claimed.status = "done"
    claimed.error = "old error string"
    client.db.add(claimed)
    client.db.commit()

    row = client.get("/api/versions").json()[0]
    assert row["splat_status"] == "done"
    assert row["splat_error"] is None


def test_has_splat_is_file_based_and_independent_of_status(client):
    from server import splat_jobs

    v = make_version(client)
    splat_dir = Path(v.path) / "splat"
    splat_dir.mkdir(parents=True, exist_ok=True)
    (splat_dir / "scene.sog").write_bytes(b"PK\x03\x04old-sog")
    splat_jobs.enqueue(client.db, v.id)
    splat_jobs.claim_next(client.db)
    row = client.get("/api/versions").json()[0]
    assert row["has_splat"] is True
    assert row["splat_status"] == "running"

    v2 = make_version(client, area="floor9")
    splat_jobs.enqueue(client.db, v2.id)
    claimed2 = splat_jobs.claim_next(client.db)
    splat_jobs.fail(client.db, claimed2, "failed")
    rows = {r["id"]: r for r in client.get("/api/versions").json()}
    assert rows[v2.id]["has_splat"] is False
    assert rows[v2.id]["splat_status"] == "failed"


@pytest.mark.parametrize("prev_status", ["failed", "done"])
def test_rebuild_queues_a_failed_or_done_job(client, prev_status):
    from sqlmodel import select

    from server import splat_jobs
    from server.db import SplatJob

    v = make_version(client)
    splat_jobs.enqueue(client.db, v.id)
    claimed = splat_jobs.claim_next(client.db)
    if prev_status == "failed":
        splat_jobs.fail(client.db, claimed, "bad run")
    else:
        splat_jobs.finish(client.db, claimed, {"ok": 1})

    r = client.post(f"/api/versions/{v.id}/splat/rebuild", json={})
    assert r.status_code == 202
    assert r.json() == {"status": "queued"}

    client.db.expire_all()
    updated = client.db.exec(select(SplatJob).where(SplatJob.map_version_id == v.id)).first()
    assert updated.status == "queued"
    assert updated.error is None


def test_rebuild_creates_a_row_when_none_exists(client):
    from sqlmodel import select

    from server.db import SplatJob

    v = make_version(client)
    assert client.db.exec(select(SplatJob).where(SplatJob.map_version_id == v.id)).first() is None

    r = client.post(f"/api/versions/{v.id}/splat/rebuild", json={})
    assert r.status_code == 202
    assert r.json() == {"status": "queued"}

    client.db.expire_all()
    rows = client.db.exec(select(SplatJob).where(SplatJob.map_version_id == v.id)).all()
    assert len(rows) == 1
    assert rows[0].status == "queued"
    assert rows[0].params == {"steps": 30000, "min_opacity": 0.02}


@pytest.mark.parametrize("status", ["queued", "running"])
def test_rebuild_409_when_queued_or_running(client, status):
    from sqlmodel import select

    from server import splat_jobs
    from server.db import SplatJob

    v = make_version(client)
    splat_jobs.enqueue(client.db, v.id)
    if status == "running":
        splat_jobs.claim_next(client.db)

    r = client.post(f"/api/versions/{v.id}/splat/rebuild", json={})
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["code"] == "splat_busy"

    client.db.expire_all()
    row = client.db.exec(select(SplatJob).where(SplatJob.map_version_id == v.id)).first()
    assert row.status == status


def test_rebuild_404_for_unknown_version(client):
    from sqlmodel import select

    from server.db import SplatJob

    r = client.post("/api/versions/999/splat/rebuild", json={})
    assert r.status_code == 404
    assert client.db.exec(select(SplatJob)).all() == []


def test_rebuild_requires_login(client, monkeypatch):
    v = make_version(client)
    monkeypatch.delenv("EUTOPOS_DEV_NO_AUTH", raising=False)
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "https://test.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", "test-aud")
    r = client.post(f"/api/versions/{v.id}/splat/rebuild", json={})
    assert r.status_code == 401


def test_rebuild_needs_admin(client, monkeypatch):
    from sqlmodel import select

    from server.db import SplatJob

    v = make_version(client)
    as_guest(client, monkeypatch)
    r = client.post(f"/api/versions/{v.id}/splat/rebuild", json={})
    assert r.status_code == 403
    assert client.db.exec(select(SplatJob)).all() == []


def test_rebuild_rejects_a_version_without_a_build_job(client):
    from sqlmodel import select

    from server.db import SplatJob

    v = make_version(client, job=False)
    r = client.post(f"/api/versions/{v.id}/splat/rebuild", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "splat_no_frames"
    assert client.db.exec(select(SplatJob)).all() == []


def test_rebuild_is_refused_while_its_job_is_being_deleted(client):
    from sqlmodel import select

    from server.db import SplatJob

    v = make_version(client)
    j = client.db.exec(select(MapJob).where(MapJob.map_version_id == v.id)).first()
    jobs.request_delete(client.db, j)
    r = client.post(f"/api/versions/{v.id}/splat/rebuild", json={})
    assert r.status_code == 409
    assert "deleted" in r.json()["detail"]
    assert client.db.exec(select(SplatJob)).all() == []


def test_rebuild_rejects_a_cross_site_form(client):
    from sqlmodel import select

    from server.db import SplatJob

    v = make_version(client)
    r = client.post(
        f"/api/versions/{v.id}/splat/rebuild",
        content=b"{}",
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 415
    assert client.db.exec(select(SplatJob)).all() == []


def test_rebuild_accepts_json_with_a_charset(client):
    v = make_version(client)
    r = client.post(
        f"/api/versions/{v.id}/splat/rebuild",
        content=b"{}",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert r.status_code == 202


def test_rebuild_ignores_the_request_body(client):
    from sqlmodel import select

    from server.db import SplatJob

    v = make_version(client)
    r = client.post(f"/api/versions/{v.id}/splat/rebuild", json={"steps": 1, "min_opacity": 0.9})
    assert r.status_code == 202
    row = client.db.exec(select(SplatJob).where(SplatJob.map_version_id == v.id)).first()
    assert row.params == {"steps": 30000, "min_opacity": 0.02}


def test_rebuild_touches_nothing_else(client):
    from sqlmodel import select

    v = make_version(client)
    splat_dir = Path(v.path) / "splat"
    splat_dir.mkdir(parents=True, exist_ok=True)
    content = b"PK\x03\x04original-scene-sog"
    (splat_dir / "scene.sog").write_bytes(content)

    map_job = client.db.exec(select(MapJob).where(MapJob.map_version_id == v.id)).first()
    job_status_before = map_job.status
    version_status_before = v.status

    r = client.post(f"/api/versions/{v.id}/splat/rebuild", json={})
    assert r.status_code == 202

    client.db.expire_all()
    map_job_after = client.db.exec(select(MapJob).where(MapJob.map_version_id == v.id)).first()
    v_after = client.db.get(type(v), v.id)
    assert map_job_after.status == job_status_before
    assert v_after.status == version_status_before
    assert (splat_dir / "scene.sog").read_bytes() == content

    row = client.get("/api/versions").json()[0]
    assert row["has_splat"] is True


def test_rebuild_unexpected_value_error_is_not_reported_as_busy(client, monkeypatch):
    from server import splat_jobs

    v = make_version(client)

    def raise_unexpected(*args, **kwargs):
        raise ValueError("something unexpected")

    monkeypatch.setattr(splat_jobs, "enqueue", raise_unexpected)
    c = TestClient(client.app, raise_server_exceptions=False)
    r = c.post(f"/api/versions/{v.id}/splat/rebuild", json={})
    assert r.status_code == 500


def test_rebuild_non_admin_gets_403_even_for_an_unknown_version(client, monkeypatch):
    """403 sebelum 404: yang bukan admin tidak bisa menebak id versi lewat bedanya kode."""
    as_guest(client, monkeypatch)
    assert client.post("/api/versions/999/splat/rebuild", json={}).status_code == 403


def test_rebuild_maps_a_version_that_vanishes_before_queueing_to_404(client, monkeypatch):
    from sqlmodel import select

    from server import splat_jobs
    from server.db import SplatJob

    v = make_version(client)

    def vanished(*args, **kwargs):
        raise ValueError("map version not found")

    monkeypatch.setattr(splat_jobs, "enqueue", vanished)
    r = client.post(f"/api/versions/{v.id}/splat/rebuild", json={})
    assert r.status_code == 404
    assert client.db.exec(select(SplatJob)).all() == []
