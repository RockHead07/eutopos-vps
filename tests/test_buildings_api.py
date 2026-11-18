"""Uji endpoint API /api/buildings."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server import auth, buildings_api
from server.db import Area
from tests.conftest import make_building


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'b.db'}"
    eng = create_engine(url)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        bld = make_building(s)
        s.add(Area(id="floor10", name="Lantai 10", building_id=bld.id))
        s.commit()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.setenv("EUTOPOS_ADMINS", "admin@x.id")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    app = FastAPI()
    app.include_router(buildings_api.router)
    with TestClient(app) as c:
        c.db = Session(eng)
        yield c
        app.dependency_overrides.clear()


def test_list_buildings_shows_hcm_and_areas(client):
    r = client.get("/api/buildings")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    hcm = next((b for b in data if b["slug"] == "hcm"), None)
    assert hcm is not None
    assert hcm["name"] == "HCM"
    assert "floor10" in hcm["area_ids"]


def test_create_building_admin_success_and_conflict(client):
    client.app.dependency_overrides[auth.current_user] = lambda: "admin@x.id"
    headers = {"Cf-Access-Authenticated-User-Email": "admin@x.id"}
    r = client.post("/api/buildings", json={"slug": "pens", "name": "PENS"}, headers=headers)
    assert r.status_code == 201
    created = r.json()
    assert created["slug"] == "pens"
    assert created["name"] == "PENS"
    assert created["area_ids"] == []

    # Kedua kalinya: 409 building_exists
    r2 = client.post(
        "/api/buildings", json={"slug": "pens", "name": "PENS Duplicate"}, headers=headers
    )
    assert r2.status_code == 409
    assert r2.json() == {"code": "building_exists"}


def test_create_building_non_admin_forbidden(client):
    client.app.dependency_overrides[auth.current_user] = lambda: "user@x.id"
    headers = {"Cf-Access-Authenticated-User-Email": "user@x.id"}
    r = client.post("/api/buildings", json={"slug": "other", "name": "Other"}, headers=headers)
    assert r.status_code == 403


def test_create_building_non_json_unsupported(client):
    client.app.dependency_overrides[auth.current_user] = lambda: "admin@x.id"
    headers = {
        "Cf-Access-Authenticated-User-Email": "admin@x.id",
        "Content-Type": "text/plain",
    }
    r = client.post("/api/buildings", content="not json", headers=headers)
    assert r.status_code == 415


def test_create_building_invalid_slug_unprocessable(client):
    client.app.dependency_overrides[auth.current_user] = lambda: "admin@x.id"
    headers = {"Cf-Access-Authenticated-User-Email": "admin@x.id"}
    r = client.post("/api/buildings", json={"slug": "PENS!", "name": "PENS"}, headers=headers)
    assert r.status_code == 422
