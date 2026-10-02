"""Dashboard statis dipasang di / tanpa menutup rute API yang terdaftar lebih dulu."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.app import mount_web


def test_static_mount_keeps_api_routes(tmp_path):
    (tmp_path / "job").mkdir()
    (tmp_path / "index.html").write_text("beranda")
    (tmp_path / "job" / "index.html").write_text("detail")
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    assert mount_web(app, tmp_path) is True
    c = TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}
    assert c.get("/").text == "beranda"
    assert c.get("/job/?id=3").text == "detail"


def test_missing_build_is_skipped(tmp_path):
    assert mount_web(FastAPI(), tmp_path / "tidak-ada") is False
