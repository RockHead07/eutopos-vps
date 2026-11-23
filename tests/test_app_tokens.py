import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from server import app_tokens, auth
from server.db import AppToken


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'tokens.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    app = FastAPI()
    app.include_router(app_tokens.router)
    with TestClient(app) as c:
        c.engine = engine
        yield c
    engine.dispose()


def test_create_returns_raw_token_once_and_stores_hash(client):
    created = client.post("/api/app-tokens", json={"name": "rekam-1"})
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {"name", "token"}
    assert body["token"].startswith("eut_")
    listing = client.get("/api/app-tokens")
    assert listing.status_code == 200
    [token] = listing.json()
    assert token["name"] == "rekam-1"
    assert "token" not in token and "token_hash" not in token
    with Session(client.engine) as session:
        row = session.exec(select(AppToken)).one()
        assert row.token_hash == app_tokens.hash_token(body["token"])
        assert row.created_by == auth.DEV_USER
    revoked = client.delete("/api/app-tokens/rekam-1")
    assert revoked.json() == {"name": "rekam-1", "revoked": True}
    assert client.get("/api/app-tokens").json()[0]["revoked_at"] is not None
    assert client.delete("/api/app-tokens/missing").status_code == 404


def test_non_admin_cannot_manage_tokens(client):
    client.app.dependency_overrides[auth.current_user] = lambda: "visitor@example.test"
    assert client.post("/api/app-tokens", json={"name": "rekam-1"}).status_code == 403
    assert client.get("/api/app-tokens").status_code == 403
    assert client.delete("/api/app-tokens/rekam-1").status_code == 403


def test_duplicate_or_invalid_name_rejected(client):
    assert client.post("/api/app-tokens", json={"name": "rekam-1"}).status_code == 201
    assert client.post("/api/app-tokens", json={"name": "rekam-1"}).status_code == 422
    assert client.delete("/api/app-tokens/rekam-1").status_code == 200
    assert client.post("/api/app-tokens", json={"name": "rekam-1"}).status_code == 422
    assert client.post("/api/app-tokens", json={"name": "Bad Name"}).status_code == 422


def test_identity_from_bearer(client):
    with Session(client.engine) as session:
        raw = app_tokens.create_token(session, "rekam-1", auth.DEV_USER)
        assert app_tokens.identity_from_bearer(session, f"bEaReR {raw}") == "app:rekam-1"
        assert session.exec(select(AppToken)).one().last_used_at is not None
        with pytest.raises(auth.AuthError) as unknown:
            app_tokens.identity_from_bearer(session, "Bearer eut_unknown")
        assert unknown.value.status == 401
        assert app_tokens.revoke_token(session, "rekam-1")
        with pytest.raises(auth.AuthError) as revoked:
            app_tokens.identity_from_bearer(session, f"Bearer {raw}")
        assert revoked.value.status == 403
        assert app_tokens.identity_from_bearer(session, "Basic x") is None


def test_capture_identity_validates_bearer_even_in_dev_mode(client):
    with Session(client.engine) as session, pytest.raises(auth.AuthError) as unknown:
        app_tokens.capture_identity(session, {"aUtHoRiZaTiOn": "Bearer eut_unknown"})
    assert unknown.value.status == 401


def test_revoked_token_rejected_even_with_access_jwt(client, monkeypatch):
    monkeypatch.setattr(auth, "email_from_token", lambda _token: "edge@example.test")
    with Session(client.engine) as session:
        raw = app_tokens.create_token(session, "rekam-1", auth.DEV_USER)
        app_tokens.revoke_token(session, "rekam-1")
        headers = {auth.HEADER: "synthetic-access-header", "Authorization": f"Bearer {raw}"}
        with pytest.raises(auth.AuthError) as revoked:
            app_tokens.capture_identity(session, headers)
    assert revoked.value.status == 403
