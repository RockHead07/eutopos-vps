"""Uji API pekerjaan dan hook tusd, dengan SQLite dan mode autentikasi uji."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server import uploads
from server.db import MapJob

SECRET = "rahasia-hook"
BODY = {
    "area_id": "floor10",
    "area_name": "Lantai 10",
    "videos": [
        {"name": "loop.mp4", "role": "peta", "size": 100},
        {"name": "uji.mp4", "role": "uji", "size": 50},
    ],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'u.db'}"
    eng = create_engine(url)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        from server.db import Area
        from tests.conftest import make_building

        bld = make_building(s)
        s.add(Area(id="floor10", name="Lantai 10", building_id=bld.id))
        s.commit()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.setenv("TUS_HOOK_SECRET", SECRET)
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(uploads, "UPLOADS", tmp_path / "uploads")
    app = FastAPI()
    app.include_router(uploads.router)
    with TestClient(app) as c:
        c.db_url = url
        c.uploads = tmp_path / "uploads"
        yield c


def post_hook(client, kind, upload, key=SECRET, headers=None):
    event = {"Upload": upload, "HTTPRequest": {"Header": headers or {}}}
    url = "/internal/tus-hook" + (f"?key={key}" if key is not None else "")
    return client.post(url, json={"Type": kind, "Event": event})


def hook(client, kind, job_id, name, size, upload_id=None, deferred=False):
    upload = {
        "ID": upload_id,
        "Size": size,
        "SizeIsDeferred": deferred,
        "MetaData": {"job_id": str(job_id), "name": name},
    }
    r = post_hook(client, kind, upload, headers={"Cf-Access-Jwt-Assertion": ["token"]})
    assert r.status_code == 200, r.text
    return r.json()


def finish(client, job_id, name, size, upload_id):
    (client.uploads / upload_id).write_bytes(b"x" * size)  # yang ditulis tusd
    return hook(client, "pre-finish", job_id, name, size, upload_id=upload_id)


def job_row(client, job_id):
    with Session(create_engine(client.db_url)) as s:
        return s.get(MapJob, job_id)


def test_full_upload_flow_queues_after_last_video(client):
    job = client.post("/api/jobs", json=BODY).json()
    assert job["status"] == "uploading" and job["created_by"] == "dev@local"

    ids = []
    for name, size in [("loop.mp4", 100), ("uji.mp4", 50)]:
        res = hook(client, "pre-create", job["id"], name, size)
        assert "RejectUpload" not in res
        ids.append(res["ChangeFileInfo"]["ID"])
    assert all(i.startswith(f"job{job['id']}-v") for i in ids)

    finish(client, job["id"], "loop.mp4", 100, ids[0])
    assert job_row(client, job["id"]).status == "uploading"  # masih menunggu video kedua
    finish(client, job["id"], "uji.mp4", 50, ids[1])

    row = job_row(client, job["id"])
    assert row.status == "queued"
    assert [v["path"] for v in row.videos] == [str(client.uploads / i) for i in ids]
    out = client.get(f"/api/jobs/{job['id']}").json()
    assert out["status"] == "queued"
    # ID unggahan dan path tidak dibocorkan ke klien: dengan ID itu orang bisa mengganggu unggahan
    assert all(
        set(v)
        == {"name", "role", "size", "uploaded", "recorded_at", "received", "activity_at", "kind"}
        for v in out["videos"]
    )


@pytest.mark.parametrize(
    "name,size,deferred,status",
    [
        ("loop.mp4", 999, False, 400),  # ukuran berbeda dari yang didaftarkan
        ("loop.mp4", 0, True, 400),  # panjang tus ditunda
        ("lain.mp4", 100, False, 404),  # nama tidak terdaftar
    ],
    ids=["ukuran-beda", "panjang-ditunda", "nama-asing"],
)
def test_pre_create_rejects(client, name, size, deferred, status):
    job = client.post("/api/jobs", json=BODY).json()
    res = hook(client, "pre-create", job["id"], name, size, deferred=deferred)
    assert res["RejectUpload"] is True and res["HTTPResponse"]["StatusCode"] == status


def test_pre_create_rejects_other_user(client, monkeypatch):
    job = client.post("/api/jobs", json=BODY).json()
    monkeypatch.setattr(uploads.auth, "email_from_token", lambda token: "orang-lain@x.id")
    res = hook(client, "pre-create", job["id"], "loop.mp4", 100)
    assert res["RejectUpload"] is True and res["HTTPResponse"]["StatusCode"] == 403


@pytest.mark.parametrize("key,status", [(None, 403), ("salah", 403)], ids=["tanpa", "salah"])
def test_hook_requires_secret(client, key, status):
    job = client.post("/api/jobs", json=BODY).json()
    upload = {"ID": None, "MetaData": {"job_id": str(job["id"])}}  # pre-finish palsu tanpa ID
    assert post_hook(client, "pre-finish", upload, key=key).status_code == status
    assert job_row(client, job["id"]).status == "uploading"


def test_hook_closed_without_secret_config(client, monkeypatch):
    monkeypatch.delenv("TUS_HOOK_SECRET")
    assert post_hook(client, "pre-finish", {}).status_code == 503


def test_pre_finish_requires_known_id(client):
    job = client.post("/api/jobs", json=BODY).json()
    res = post_hook(client, "pre-finish", {"ID": None, "MetaData": {"job_id": str(job["id"])}})
    assert res.json()["HTTPResponse"]["StatusCode"] == 404
    assert job_row(client, job["id"]).status == "uploading"


def test_pre_finish_rejects_incomplete_file(client):
    job = client.post("/api/jobs", json=BODY).json()
    uid = hook(client, "pre-create", job["id"], "loop.mp4", 100)["ChangeFileInfo"]["ID"]
    (client.uploads / uid).write_bytes(b"x" * 40)  # baru sebagian
    res = hook(client, "pre-finish", job["id"], "loop.mp4", 100, upload_id=uid)
    assert res["HTTPResponse"]["StatusCode"] == 409
    assert job_row(client, job["id"]).videos[0]["uploaded"] is False


def test_pre_finish_ignores_storage_path_from_hook(client):
    job = client.post("/api/jobs", json=BODY).json()
    uid = hook(client, "pre-create", job["id"], "loop.mp4", 100)["ChangeFileInfo"]["ID"]
    (client.uploads / uid).write_bytes(b"x" * 100)
    upload = {"ID": uid, "Size": 100, "MetaData": {"job_id": str(job["id"])}}
    upload["Storage"] = {"Path": "/etc/passwd"}
    post_hook(client, "pre-finish", upload)
    assert job_row(client, job["id"]).videos[0]["path"] == str(client.uploads / uid)


def test_create_job_validation(client):
    bad = {**BODY, "videos": [{"name": "a.mp4", "role": "uji", "size": 1}]}
    assert client.post("/api/jobs", json=bad).status_code == 422  # tanpa video peta
    twins = {**BODY, "videos": [BODY["videos"][0], BODY["videos"][0]]}
    assert client.post("/api/jobs", json=twins).status_code == 422  # nama kembar
    big = {**BODY, "videos": [{"name": "a.mp4", "role": "peta", "size": 3 * 1024**3}]}
    assert client.post("/api/jobs", json=big).status_code == 422  # lebih dari 2 GiB


def test_api_without_auth_config_is_closed(client, monkeypatch):
    monkeypatch.delenv("EUTOPOS_DEV_NO_AUTH")
    assert client.post("/api/jobs", json=BODY).status_code == 503


def test_post_receive_updates_received_and_activity_at_throttled(client, monkeypatch):
    from datetime import datetime, timedelta

    job = client.post("/api/jobs", json=BODY).json()
    uid = hook(client, "pre-create", job["id"], "loop.mp4", 100)["ChangeFileInfo"]["ID"]

    # First post-receive updates received and activity_at
    res = post_hook(
        client,
        "post-receive",
        {"ID": uid, "Offset": 30, "MetaData": {"job_id": str(job["id"])}},
    )
    assert res.status_code == 200 and res.json() == {}
    row = job_row(client, job["id"])
    v0 = row.videos[0]
    assert v0.get("received") == 30
    first_activity = v0.get("activity_at")
    assert first_activity is not None

    out = client.get(f"/api/jobs/{job['id']}").json()
    assert out["videos"][0]["received"] == 30
    assert datetime.fromisoformat(out["videos"][0]["activity_at"]) == datetime.fromisoformat(
        first_activity
    )
    assert out["stalled"] is False

    # Second post-receive within 5 seconds is throttled (db not updated)
    res2 = post_hook(
        client,
        "post-receive",
        {"ID": uid, "Offset": 60, "MetaData": {"job_id": str(job["id"])}},
    )
    assert res2.status_code == 200 and res2.json() == {}
    row = job_row(client, job["id"])
    assert row.videos[0].get("received") == 30
    assert row.videos[0].get("activity_at") == first_activity

    # After 5 seconds elapsed, post-receive writes the new progress
    t_later = datetime.fromisoformat(first_activity) + timedelta(seconds=6)
    monkeypatch.setattr(uploads, "_utc_now", lambda: t_later)

    res3 = post_hook(
        client,
        "post-receive",
        {"ID": uid, "Offset": 80, "MetaData": {"job_id": str(job["id"])}},
    )
    assert res3.status_code == 200 and res3.json() == {}
    row = job_row(client, job["id"])
    assert row.videos[0].get("received") == 80
    assert datetime.fromisoformat(row.videos[0].get("activity_at")) == t_later


def test_post_receive_ignores_unknown_finished_or_non_uploading(client):
    job = client.post("/api/jobs", json=BODY).json()
    uid = hook(client, "pre-create", job["id"], "loop.mp4", 100)["ChangeFileInfo"]["ID"]

    # Unknown ID returns {} without error
    res = post_hook(client, "post-receive", {"ID": "unknown-id", "Offset": 10})
    assert res.status_code == 200 and res.json() == {}

    # Complete the job to queued
    finish(client, job["id"], "loop.mp4", 100, uid)
    uid2 = hook(client, "pre-create", job["id"], "uji.mp4", 50)["ChangeFileInfo"]["ID"]
    finish(client, job["id"], "uji.mp4", 50, uid2)
    assert job_row(client, job["id"]).status == "queued"

    # Post-receive on a queued job is ignored
    res = post_hook(
        client,
        "post-receive",
        {"ID": uid, "Offset": 50, "MetaData": {"job_id": str(job["id"])}},
    )
    assert res.status_code == 200 and res.json() == {}


def test_delete_stalled_upload_flow(client, monkeypatch):
    monkeypatch.setattr(uploads.auth, "is_admin", lambda user: True)
    job = client.post("/api/jobs", json=BODY).json()
    uid = hook(client, "pre-create", job["id"], "loop.mp4", 100)["ChangeFileInfo"]["ID"]
    post_hook(
        client,
        "post-receive",
        {"ID": uid, "Offset": 10, "MetaData": {"job_id": str(job["id"])}},
    )

    # While receiving data (not stalled), delete returns 409
    del_res = client.delete(f"/api/jobs/{job['id']}")
    assert del_res.status_code == 409
    assert del_res.json()["detail"] == "upload is still receiving data"

    # Mark stalled by setting activity_at to 15 minutes ago
    from datetime import UTC, datetime, timedelta

    row = job_row(client, job["id"])
    vids = list(row.videos)
    vids[0]["activity_at"] = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()
    with Session(create_engine(client.db_url)) as s:
        j = s.get(MapJob, job["id"])
        j.videos = vids
        s.add(j)
        s.commit()

    # Now it is stalled, delete is allowed (status deleting)
    del_res2 = client.delete(f"/api/jobs/{job['id']}")
    assert del_res2.status_code == 202
    assert del_res2.json() == {"status": "deleting"}


def test_create_job_building_id_rules(client):
    from server.db import Building
    from tests.conftest import make_building

    with Session(create_engine(client.db_url)) as s:
        bld = make_building(s)
        bld_id = bld.id
        other_bld = Building(org_id=bld.org_id, slug="other-bld", name="Other Bld")
        s.add(other_bld)
        s.commit()
        s.refresh(other_bld)
        other_bld_id = other_bld.id

    # 1. Area baru dengan building_id -> 201
    body_new = {
        "area_id": "new-area",
        "area_name": "New Area",
        "videos": [{"name": "loop.mp4", "role": "peta", "size": 100}],
        "building_id": bld_id,
    }
    r1 = client.post("/api/jobs", json=body_new)
    assert r1.status_code == 201

    # 2. Area baru tanpa building_id -> 422
    body_new_no_bld = {
        "area_id": "new-area-no-bld",
        "area_name": "New Area No Bld",
        "videos": [{"name": "loop.mp4", "role": "peta", "size": 100}],
    }
    r2 = client.post("/api/jobs", json=body_new_no_bld)
    assert r2.status_code == 422
    assert "building_id is required for a new area" in r2.text

    # 3. Area lama tanpa building_id -> 201 (Review Focus 2)
    body_existing = {
        "area_id": "floor10",
        "area_name": "Lantai 10",
        "videos": [{"name": "loop.mp4", "role": "peta", "size": 100}],
    }
    r3 = client.post("/api/jobs", json=body_existing)
    assert r3.status_code == 201

    # 4. Area lama dengan gedung lain -> 422 (Review Focus 1)
    body_wrong_bld = {
        "area_id": "floor10",
        "area_name": "Lantai 10",
        "videos": [{"name": "loop.mp4", "role": "peta", "size": 100}],
        "building_id": other_bld_id,
    }
    r4 = client.post("/api/jobs", json=body_wrong_bld)
    assert r4.status_code == 422
    assert "belongs to another building" in r4.text


def test_kind_defaults_to_video_in_api_and_existing_job(client):
    created = client.post("/api/jobs", json=BODY)
    assert created.status_code == 201
    job_id = created.json()["id"]
    assert [video["kind"] for video in created.json()["videos"]] == ["video", "video"]
    row = job_row(client, job_id)
    assert [video["kind"] for video in row.videos] == ["video", "video"]
    with Session(create_engine(client.db_url)) as s:
        job = s.get(MapJob, job_id)
        job.videos = [{k: v for k, v in video.items() if k != "kind"} for video in job.videos]
        s.commit()
    assert [v["kind"] for v in client.get(f"/api/jobs/{job_id}").json()["videos"]] == [
        "video",
        "video",
    ]


@pytest.mark.parametrize("other_kind", ["frames", "video"])
def test_one_role_cannot_mix_or_duplicate_frame_packages(client, other_kind):
    videos = [
        {"name": "scan.zip", "role": "peta", "size": 10, "kind": "frames"},
        {"name": "other", "role": "peta", "size": 10, "kind": other_kind},
    ]
    response = client.post("/api/jobs", json={**BODY, "videos": videos})
    assert response.status_code == 422
    assert client.get("/api/jobs").json() == []


def test_roles_can_use_different_upload_kinds(client):
    videos = [dict(BODY["videos"][0], name="scan.zip", kind="frames"), BODY["videos"][1]]
    response = client.post("/api/jobs", json={**BODY, "videos": videos})
    assert response.status_code == 201
    assert [v["kind"] for v in response.json()["videos"]] == ["frames", "video"]


@pytest.fixture
def capture_bearer(client):
    from server.app_tokens import create_token

    engine = create_engine(client.db_url)
    try:
        with Session(engine) as session:
            return {
                "Authorization": f"Bearer {create_token(session, 'rekam-1', 'admin@example.test')}"
            }
    finally:
        engine.dispose()


def test_app_token_creates_job_and_uploads(client, capture_bearer):
    response = client.post("/api/jobs", json=BODY, headers=capture_bearer)
    assert response.status_code == 201
    job = response.json()
    assert job["created_by"] == "app:rekam-1"
    for name, size in [("loop.mp4", 100), ("uji.mp4", 50)]:
        upload = {"MetaData": {"job_id": str(job["id"]), "name": name}, "Size": size}
        response = post_hook(
            client, "pre-create", upload, headers={"authorization": list(capture_bearer.values())}
        )
        assert response.status_code == 200
        assert "RejectUpload" not in response.json()
        upload_id = response.json()["ChangeFileInfo"]["ID"]
        finish(client, job["id"], name, size, upload_id)
    assert job_row(client, job["id"]).status == "queued"


def test_app_token_cannot_read_other_jobs(client, capture_bearer, monkeypatch):
    monkeypatch.setattr(uploads.auth, "email_from_token", lambda _: "a@x.id")
    other = client.post("/api/jobs", json=BODY).json()
    own = client.post("/api/jobs", json=BODY, headers=capture_bearer).json()
    assert client.get(f"/api/jobs/{other['id']}", headers=capture_bearer).status_code == 404
    assert client.get(f"/api/jobs/{own['id']}", headers=capture_bearer).status_code == 200


@pytest.mark.parametrize("with_access_config", [True, False], ids=["access", "dev"])
def test_app_token_rejected_on_non_capture_routes(
    client, capture_bearer, monkeypatch, with_access_config
):
    from server.app import app

    job = client.post("/api/jobs", json=BODY).json()
    if with_access_config:
        monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "https://team.invalid")
        monkeypatch.setenv("CF_ACCESS_AUD", "synthetic")
    actual = TestClient(app)
    for method, path in [
        ("GET", "/api/jobs"),
        ("DELETE", f"/api/jobs/{job['id']}"),
        ("GET", "/api/me"),
        ("GET", "/api/areas/floor10/graph"),
        ("GET", "/api/app-tokens"),
        ("POST", "/localize"),
    ]:
        assert actual.request(method, path, headers=capture_bearer).status_code == 401


def test_pre_create_rejects_app_token_for_email_job(client, capture_bearer):
    job = client.post("/api/jobs", json=BODY).json()
    upload = {"MetaData": {"job_id": str(job["id"]), "name": "loop.mp4"}, "Size": 100}
    response = post_hook(
        client, "pre-create", upload, headers={"Authorization": list(capture_bearer.values())}
    )
    assert response.status_code == 200
    assert response.json()["RejectUpload"] is True
    assert response.json()["HTTPResponse"]["StatusCode"] == 403


def _real_app_with_access(monkeypatch):
    from server.app import app

    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "https://team.invalid")
    monkeypatch.setenv("CF_ACCESS_AUD", "synthetic")
    return TestClient(app)


def test_app_token_can_list_buildings(client, capture_bearer, monkeypatch):
    actual = _real_app_with_access(monkeypatch)
    response = actual.get("/api/buildings", headers=capture_bearer)
    assert response.status_code == 200
    body = response.json()
    assert {"id", "slug", "name", "area_ids"} <= set(body[0])
    assert any("floor10" in b["area_ids"] for b in body)


def test_app_token_cannot_create_building(client, capture_bearer, monkeypatch):
    actual = _real_app_with_access(monkeypatch)
    payload = {"slug": "gedung-x", "name": "Gedung X"}
    assert actual.post("/api/buildings", json=payload, headers=capture_bearer).status_code == 401


def test_revoked_app_token_cannot_list_buildings(client, capture_bearer, monkeypatch):
    from server import app_tokens

    engine = create_engine(client.db_url)
    try:
        with Session(engine) as session:
            assert app_tokens.revoke_token(session, "rekam-1")
    finally:
        engine.dispose()
    actual = _real_app_with_access(monkeypatch)
    assert actual.get("/api/buildings", headers=capture_bearer).status_code == 403


def test_upload_times_recorded(client, monkeypatch):
    from datetime import UTC, datetime

    t0 = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 11, 25, 10, 1, 20, tzinfo=UTC)
    job = client.post("/api/jobs", json=BODY).json()

    monkeypatch.setattr(uploads, "_utc_now", lambda: t0)
    ids = []
    for name, size in [("loop.mp4", 100), ("uji.mp4", 50)]:
        res = hook(client, "pre-create", job["id"], name, size)
        ids.append(res["ChangeFileInfo"]["ID"])

    monkeypatch.setattr(uploads, "_utc_now", lambda: t1)
    finish(client, job["id"], "loop.mp4", 100, ids[0])
    finish(client, job["id"], "uji.mp4", 50, ids[1])

    row = job_row(client, job["id"])
    assert row.status == "queued"
    for video in row.videos:
        assert video["upload_started_at"] == t0.isoformat()
        assert video["uploaded_at"] == t1.isoformat()


def test_restart_from_zero_resets_start(client, monkeypatch):
    from datetime import UTC, datetime

    t0 = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 25, 10, 5, 0, tzinfo=UTC)
    job = client.post("/api/jobs", json=BODY).json()

    monkeypatch.setattr(uploads, "_utc_now", lambda: t0)
    hook(client, "pre-create", job["id"], "loop.mp4", 100)
    assert job_row(client, job["id"]).videos[0]["upload_started_at"] == t0.isoformat()

    monkeypatch.setattr(uploads, "_utc_now", lambda: t2)
    hook(client, "pre-create", job["id"], "loop.mp4", 100)
    assert job_row(client, job["id"]).videos[0]["upload_started_at"] == t2.isoformat()


def test_upload_times_ignore_non_uploading_job(client, monkeypatch):
    from datetime import UTC, datetime

    t0 = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 11, 25, 10, 1, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 25, 10, 9, 0, tzinfo=UTC)
    job = client.post("/api/jobs", json=BODY).json()

    monkeypatch.setattr(uploads, "_utc_now", lambda: t0)
    id0 = hook(client, "pre-create", job["id"], "loop.mp4", 100)["ChangeFileInfo"]["ID"]
    id1 = hook(client, "pre-create", job["id"], "uji.mp4", 50)["ChangeFileInfo"]["ID"]

    monkeypatch.setattr(uploads, "_utc_now", lambda: t1)
    finish(client, job["id"], "loop.mp4", 100, id0)
    finish(client, job["id"], "uji.mp4", 50, id1)

    before = job_row(client, job["id"]).videos
    assert job_row(client, job["id"]).status == "queued"

    monkeypatch.setattr(uploads, "_utc_now", lambda: t2)
    res_create = hook(client, "pre-create", job["id"], "loop.mp4", 100)
    assert res_create["RejectUpload"] is True
    res_finish = finish(client, job["id"], "loop.mp4", 100, id0)
    assert res_finish == {}  # pengulangan hook untuk job yang sudah antre tidak ditolak
    assert job_row(client, job["id"]).videos == before


def test_usage_splits_served_and_candidate(client):
    from datetime import UTC, datetime, timedelta

    from server.db import LocalizeRequest, MapVersion

    job = client.post("/api/jobs", json=BODY).json()
    t0 = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
    engine = create_engine(client.db_url)
    try:
        with Session(engine) as s:
            v = MapVersion(area_id="floor10", version=2, path="/maps/floor10/job-1")
            s.add(v)
            s.commit()
            s.refresh(v)
            row = s.get(MapJob, job["id"])
            row.map_version_id = v.id
            s.add(row)
            s.add_all(
                [
                    LocalizeRequest(
                        created_at=t0,
                        result="ok",
                        http_status=200,
                        candidate=False,
                        area_id="floor10",
                        map_version=2,
                        inliers=120,
                        wall_s=1.0,
                    ),
                    LocalizeRequest(
                        created_at=t0 + timedelta(seconds=10),
                        result="ok",
                        http_status=200,
                        candidate=False,
                        area_id="floor10",
                        map_version=2,
                        inliers=180,
                        wall_s=2.0,
                    ),
                    LocalizeRequest(
                        created_at=t0 + timedelta(seconds=20),
                        result="failed",
                        http_status=200,
                        candidate=False,
                        area_id="floor10",
                        map_version=2,
                        inliers=10,
                        wall_s=3.0,
                    ),
                    LocalizeRequest(
                        created_at=t0 + timedelta(seconds=30),
                        result="ok",
                        http_status=200,
                        candidate=True,
                        area_id="floor10",
                        map_version=2,
                        inliers=90,
                        wall_s=1.5,
                    ),
                    # Versi lain dan area lain: tidak boleh ikut terhitung.
                    LocalizeRequest(
                        created_at=t0 + timedelta(seconds=40),
                        result="ok",
                        http_status=200,
                        candidate=False,
                        area_id="floor10",
                        map_version=1,
                        inliers=200,
                        wall_s=9.9,
                    ),
                    LocalizeRequest(
                        created_at=t0 + timedelta(seconds=50),
                        result="ok",
                        http_status=200,
                        candidate=False,
                        area_id="other",
                        map_version=2,
                        inliers=200,
                        wall_s=9.9,
                    ),
                ]
            )
            s.commit()
    finally:
        engine.dispose()

    res = client.get(f"/api/jobs/{job['id']}/usage")
    assert res.status_code == 200
    body = res.json()
    assert body["map_version"] == 2
    served = body["served"]
    assert served["requests"] == 3
    assert served["ok_ratio"] == pytest.approx(2 / 3)
    assert served["wall_s_p50"] == pytest.approx(2.0)
    assert served["wall_s_p95"] == pytest.approx(2.9)
    assert served["inliers_median"] == pytest.approx(120.0)
    assert served["first_at"] == t0.isoformat()
    assert served["last_at"] == (t0 + timedelta(seconds=20)).isoformat()

    cand = body["candidate"]
    assert cand["requests"] == 1
    assert cand["ok_ratio"] == 1.0
    assert cand["wall_s_p50"] == 1.5
    assert cand["wall_s_p95"] == 1.5
    assert cand["inliers_median"] == 90.0


def test_usage_empty(client):
    job = client.post("/api/jobs", json=BODY).json()
    res = client.get(f"/api/jobs/{job['id']}/usage")
    assert res.status_code == 200
    empty = {
        "requests": 0,
        "ok_ratio": None,
        "wall_s_p50": None,
        "wall_s_p95": None,
        "inliers_median": None,
        "first_at": None,
        "last_at": None,
    }
    assert res.json() == {"map_version": None, "served": empty, "candidate": empty}
    assert client.get("/api/jobs/999999/usage").status_code == 404


def test_usage_rejects_app_token(client, capture_bearer, monkeypatch):
    job = client.post("/api/jobs", json=BODY).json()
    actual = _real_app_with_access(monkeypatch)
    assert actual.get(f"/api/jobs/{job['id']}/usage", headers=capture_bearer).status_code == 401
