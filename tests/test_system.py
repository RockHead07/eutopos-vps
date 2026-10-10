"""Unit test untuk pengukuran diagnostik sistem dan endpoint GET /api/system."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import maps_api, system, uploads


def test_read_storage_path_existing(tmp_path: Path):
    """Path yang ada harus mengembalikan StorageLocation dengan nilai valid."""
    loc = system.read_storage_path(tmp_path)
    assert loc is not None
    assert loc.total_bytes > 0
    assert loc.free_bytes >= 0
    assert loc.used_bytes >= 0
    assert loc.total_gb > 0
    assert 0.0 <= loc.percent <= 100.0


def test_read_storage_path_nonexistent(tmp_path: Path):
    """Path yang tidak ada harus mengembalikan None secara anggun."""
    missing = tmp_path / "does_not_exist" / "deep_folder"
    loc = system.read_storage_path(missing)
    assert loc is None


def test_read_storage_path_none():
    """None path harus mengembalikan None."""
    assert system.read_storage_path(None) is None


def test_read_gpu_telemetry_nvidia_smi_success():
    """Membaca telemetri GPU dari output nvidia-smi."""
    fake_stdout = "NVIDIA GeForce RTX 4090, 52, 2400, 24576\n"
    with (
        patch("shutil.which", return_value="/usr/bin/nvidia-smi"),
        patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["nvidia-smi"],
                returncode=0,
                stdout=fake_stdout,
                stderr="",
            ),
        ),
    ):
        gpu = system.read_gpu_telemetry()
        assert gpu is not None
        assert gpu.name == "NVIDIA GeForce RTX 4090"
        assert gpu.temperature_c == 52
        assert gpu.vram_used_mb == 2400
        assert gpu.vram_total_mb == 24576


def test_read_gpu_telemetry_nvidia_smi_partial_temp():
    """Jika suhu tidak dapat dibaca dari nvidia-smi (misalnya [Not Supported]), temp harus None."""
    fake_stdout = "Tesla T4, N/A, 1024, 16384\n"
    with (
        patch("shutil.which", return_value="/usr/bin/nvidia-smi"),
        patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["nvidia-smi"],
                returncode=0,
                stdout=fake_stdout,
                stderr="",
            ),
        ),
    ):
        gpu = system.read_gpu_telemetry()
        assert gpu is not None
        assert gpu.name == "Tesla T4"
        assert gpu.temperature_c is None
        assert gpu.vram_used_mb == 1024
        assert gpu.vram_total_mb == 16384


def test_read_gpu_telemetry_unavailable():
    """Jika nvidia-smi dan torch cuda tidak tersedia, mengembalikan None."""
    with (
        patch("shutil.which", return_value=None),
        patch.dict("sys.modules", {"torch": None}),
    ):
        gpu = system.read_gpu_telemetry()
        assert gpu is None


def test_get_compute_device(monkeypatch: pytest.MonkeyPatch):
    """Menentukan perangkat komputasi dari variabel lingkungan."""
    monkeypatch.setenv("EUTOPOS_DEVICE", "cuda")
    assert system.get_compute_device() == "cuda"

    monkeypatch.setenv("EUTOPOS_DEVICE", "cpu")
    assert system.get_compute_device() == "cpu"


def test_get_system_diagnostics_structure(tmp_path: Path):
    """Memastikan get_system_diagnostics menghasilkan model SystemDiagnostics lengkap."""
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    diag = system.get_system_diagnostics(
        area_id="lantai-10",
        map_version=2,
        reloading=False,
        maps_path=maps_dir,
        data_path=data_dir,
    )
    assert diag.area_id == "lantai-10"
    assert diag.map_version == 2
    assert diag.reloading is False
    assert diag.reload_error is None
    assert diag.uptime_s >= 0.0
    assert diag.device in ("cuda", "cpu")
    assert diag.storage.maps is not None
    assert diag.storage.data is not None
    assert diag.storage.maps.total_bytes > 0


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)

    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    monkeypatch.setattr(system, "get_maps_path", lambda: maps_dir)
    monkeypatch.setattr(system, "get_data_path", lambda: data_dir)

    app = FastAPI()
    app.include_router(uploads.router)
    app.include_router(maps_api.router)
    st = app.state
    st.localizer, st.area_id, st.map_version, st.lock = None, "floor10", 3, threading.Lock()
    st.reloading, st.reload_error = False, None
    with TestClient(app) as c:
        c.st = st
        yield c


def test_api_system_endpoint_authenticated(client: TestClient):
    """GET /api/system harus mengembalikan 200 OK dengan format yang benar."""
    resp = client.get("/api/system")
    assert resp.status_code == 200
    data = resp.json()
    assert "storage" in data
    assert "maps" in data["storage"]
    assert "data" in data["storage"]
    assert data["storage"]["maps"]["total_bytes"] > 0
    assert "device" in data
    assert data["device"] in ("cuda", "cpu")
    assert "uptime_s" in data
    assert data["uptime_s"] >= 0
    assert data["area_id"] == "floor10"
    assert data["map_version"] == 3
    assert data["reloading"] is False


def test_api_system_endpoint_unauthenticated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """GET /api/system harus menolak permintaan tanpa autentikasi jika auth aktif."""
    monkeypatch.delenv("EUTOPOS_DEV_NO_AUTH", raising=False)
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "example.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", "fake-aud-tag")

    app = FastAPI()
    app.include_router(maps_api.router)
    st = app.state
    st.area_id, st.map_version, st.reloading, st.reload_error = None, None, False, None
    with TestClient(app) as c:
        resp = c.get("/api/system")
        assert resp.status_code == 401
