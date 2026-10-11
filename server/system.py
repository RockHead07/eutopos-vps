"""Pengukuran diagnostik sistem: penyimpanan (storage), komputasi GPU, suhu, dan uptime.

Digunakan oleh endpoint GET /api/system untuk memberikan data telemetri nyata
ke dashboard operator tanpa nilai karangan.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

_START_TIME = time.time()

# autodeploy.sh menulis umpan ini tiap 5 menit. Tiga putaran terlewat berarti timer mati: tandai
# basi, jangan perlihatkan angka lama seolah terkini.
HOST_DISK_MAX_AGE_S = 15 * 60


class StorageLocation(BaseModel):
    total_bytes: int
    used_bytes: int
    free_bytes: int
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


class HostDisk(BaseModel):
    """Drive fisik yang memuat disk virtual WSL; tak terlihat dari container, dibaca dari umpan."""

    mount: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float
    age_s: float
    stale: bool


class StorageDiagnostics(BaseModel):
    maps: StorageLocation | None = None
    data: StorageLocation | None = None
    host: HostDisk | None = None


class GpuTelemetry(BaseModel):
    name: str | None = None
    temperature_c: int | None = None
    vram_used_mb: int | None = None
    vram_total_mb: int | None = None


class SystemDiagnostics(BaseModel):
    storage: StorageDiagnostics
    gpu: GpuTelemetry | None = None
    device: Literal["cuda", "cpu"]
    uptime_s: float
    area_id: str | None = None
    map_version: int | None = None
    reloading: bool = False
    reload_error: str | None = None


def read_storage_path(path: Path | None) -> StorageLocation | None:
    """Mengukur kapasitas penyimpanan pada path yang diberikan jika ada di filesystem."""
    if path is None:
        return None
    try:
        target = path.resolve()
        if not target.exists():
            return None
        usage = shutil.disk_usage(target)
        total = usage.total
        free = usage.free
        used = usage.used
        percent = round((used / total) * 100, 1) if total > 0 else 0.0
        return StorageLocation(
            total_bytes=total,
            used_bytes=used,
            free_bytes=free,
            total_gb=round(total / (1024**3), 1),
            used_gb=round(used / (1024**3), 1),
            free_gb=round(free / (1024**3), 1),
            percent=percent,
        )
    except Exception:
        return None


def read_host_disk(path: Path | None, now: float | None = None) -> HostDisk | None:
    """Baca umpan drive tuan rumah ({"mount", "total_bytes", "free_bytes", "updated_at"}).

    Berkas hilang atau isinya tidak masuk akal berarti None: lebih baik tidak menampilkan angka
    daripada menampilkan angka yang salah.
    """
    if path is None:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        mount, total, free, stamp = (
            raw["mount"],
            raw["total_bytes"],
            raw["free_bytes"],
            raw["updated_at"],
        )
        ints = all(isinstance(v, int) and not isinstance(v, bool) for v in (total, free, stamp))
        if not (isinstance(mount, str) and ints and total > 0 and 0 <= free <= total):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    age = max(0.0, (time.time() if now is None else now) - stamp)
    used = total - free
    gb = 1024**3
    return HostDisk(
        mount=mount,
        total_bytes=total,
        used_bytes=used,
        free_bytes=free,
        total_gb=round(total / gb, 1),
        used_gb=round(used / gb, 1),
        free_gb=round(free / gb, 1),
        percent=round(used / total * 100, 1),
        age_s=age,
        stale=age > HOST_DISK_MAX_AGE_S,
    )


def get_host_disk_path(maps_path: Path | None) -> Path | None:
    """Umpan ada di samping peta (folder yang sudah di-bind), kecuali diganti lewat lingkungan."""
    env_file = os.environ.get("EUTOPOS_HOST_DISK_FILE")
    if env_file:
        return Path(env_file)
    return maps_path / ".host-disk.json" if maps_path else None


def get_maps_path() -> Path | None:
    """Mendapatkan path penyimpanan peta yang valid jika tersedia."""
    # 1. Jalur standar di dalam container Linux
    p = Path("/maps")
    if p.exists():
        return p
    # 2. Variabel lingkungan
    env_dir = os.environ.get("EUTOPOS_MAPS_DIR") or os.environ.get("EUTOPOS_MAP_DIR")
    if env_dir:
        ep = Path(env_dir)
        if ep.exists():
            return ep
    return None


def get_data_path() -> Path | None:
    """Mendapatkan path penyimpanan data aplikasi/unggahan jika tersedia."""
    # 1. Jalur standar di dalam container Linux
    for candidate in (Path("/data"), Path("/data/uploads")):
        if candidate.exists():
            return candidate
    # 2. Variabel lingkungan
    env_dir = os.environ.get("EUTOPOS_DATA_DIR")
    if env_dir:
        ep = Path(env_dir)
        if ep.exists():
            return ep
    return None


def read_gpu_telemetry() -> GpuTelemetry | None:
    """Membaca telemetri GPU nyata dari nvidia-smi atau PyTorch jika tersedia."""
    # 1. Coba baca via nvidia-smi CLI jika biner tersedia di PATH
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            res = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=name,temperature.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if res.returncode == 0 and res.stdout.strip():
                line = res.stdout.strip().splitlines()[0]
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    name = parts[0] or None
                    temp = int(parts[1]) if parts[1].isdigit() else None
                    vram_used = int(parts[2]) if parts[2].isdigit() else None
                    vram_total = int(parts[3]) if parts[3].isdigit() else None
                    return GpuTelemetry(
                        name=name,
                        temperature_c=temp,
                        vram_used_mb=vram_used,
                        vram_total_mb=vram_total,
                    )
        except Exception:
            pass

    # 2. Fallback via PyTorch jika CUDA tersedia di proses ini
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            free_b, total_b = torch.cuda.mem_get_info(0)
            vram_total = round(total_b / (1024 * 1024))
            vram_used = round((total_b - free_b) / (1024 * 1024))
            return GpuTelemetry(
                name=name,
                temperature_c=None,  # PyTorch tidak mengekspos sensor suhu
                vram_used_mb=vram_used,
                vram_total_mb=vram_total,
            )
    except Exception:
        pass

    return None


def get_compute_device() -> Literal["cuda", "cpu"]:
    """Menentukan perangkat komputasi aktif berdasarkan konfigurasi lingkungan."""
    env_dev = os.environ.get("EUTOPOS_DEVICE", "").lower()
    if env_dev == "cuda":
        return "cuda"
    if env_dev == "cpu":
        return "cpu"
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def get_system_diagnostics(
    area_id: str | None = None,
    map_version: int | None = None,
    reloading: bool = False,
    reload_error: str | None = None,
    maps_path: Path | None = None,
    data_path: Path | None = None,
) -> SystemDiagnostics:
    """Mengumpulkan status sistem lengkap."""
    m_path = maps_path if maps_path is not None else get_maps_path()
    d_path = data_path if data_path is not None else get_data_path()

    storage = StorageDiagnostics(
        maps=read_storage_path(m_path),
        data=read_storage_path(d_path),
        host=read_host_disk(get_host_disk_path(m_path)),
    )

    gpu = read_gpu_telemetry()
    device = get_compute_device()
    uptime = round(time.time() - _START_TIME, 1)

    return SystemDiagnostics(
        storage=storage,
        gpu=gpu,
        device=device,
        uptime_s=uptime,
        area_id=area_id,
        map_version=map_version,
        reloading=reloading,
        reload_error=reload_error,
    )
