"""Uji API pekerjaan dan hook tusd, dengan SQLite dan mode autentikasi uji."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server import uploads
from server.db import MapJob

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
    SQLModel.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.setattr(uploads, "UPLOADS", tmp_path / "uploads")
    app = FastAPI()
    app.include_router(uploads.router)
    with TestClient(app) as c:
        c.db_url = url
        yield c


def hook(client, kind, job_id, name, size, upload_id=None, deferred=False):
    event = {
        "Upload": {
            "ID": upload_id,
            "Size": size,
            "SizeIsDeferred": deferred,
            "MetaData": {"job_id": str(job_id), "name": name},
        },
        "HTTPRequest": {"Header": {"Cf-Access-Jwt-Assertion": ["token"]}},
    }
    r = client.post("/internal/tus-hook", json={"Type": kind, "Event": event})
    assert r.status_code == 200, r.text
    return r.json()


def job_row(client, job_id):
    with Session(create_engine(client.db_url)) as s:
        return s.get(MapJob, job_id)


def test_full_upload_flow_queues_after_last_video(client, tmp_path):
    job = client.post("/api/jobs", json=BODY).json()
    assert job["status"] == "uploading" and job["created_by"] == "dev@local"

    ids = []
    for name, size in [("loop.mp4", 100), ("uji.mp4", 50)]:
        res = hook(client, "pre-create", job["id"], name, size)
        assert "RejectUpload" not in res
        ids.append(res["ChangeFileInfo"]["ID"])
    assert all(i.startswith(f"job{job['id']}-v") for i in ids)

    hook(client, "pre-finish", job["id"], "loop.mp4", 100, upload_id=ids[0])
    assert job_row(client, job["id"]).status == "uploading"  # masih menunggu video kedua
    hook(client, "pre-finish", job["id"], "uji.mp4", 50, upload_id=ids[1])

    row = job_row(client, job["id"])
    assert row.status == "queued"
    assert [v["path"] for v in row.videos] == [str(tmp_path / "uploads" / i) for i in ids]
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "queued"


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


def test_pre_finish_ignores_storage_path_from_hook(client, tmp_path):
    job = client.post("/api/jobs", json=BODY).json()
    uid = hook(client, "pre-create", job["id"], "loop.mp4", 100)["ChangeFileInfo"]["ID"]
    event = {
        "Upload": {"ID": uid, "Size": 100, "MetaData": {"job_id": str(job["id"])}},
        "Storage": {"Path": "/etc/passwd"},
    }
    client.post("/internal/tus-hook", json={"Type": "pre-finish", "Event": event})
    assert job_row(client, job["id"]).videos[0]["path"] == str(tmp_path / "uploads" / uid)


def test_create_job_validation(client):
    bad = {**BODY, "videos": [{"name": "a.mp4", "role": "uji", "size": 1}]}
    assert client.post("/api/jobs", json=bad).status_code == 422  # tanpa video peta
    twins = {**BODY, "videos": [BODY["videos"][0], BODY["videos"][0]]}
    assert client.post("/api/jobs", json=twins).status_code == 422  # nama kembar
    big = {**BODY, "videos": [{"name": "a.mp4", "role": "peta", "size": 3 * 1024**3}]}
    assert client.post("/api/jobs", json=big).status_code == 422  # lebih dari 2 GiB


def test_api_without_auth_config_is_closed(client, monkeypatch):
    monkeypatch.delenv("EUTOPOS_DEV_NO_AUTH")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    assert client.post("/api/jobs", json=BODY).status_code == 503
