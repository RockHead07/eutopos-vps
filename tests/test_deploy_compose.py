"""Compose produksi: splat-worker harus opt-in lewat profil.

Deploy otomatis menjalankan `docker compose build` dan `up` untuk SEMUA layanan tanpa profil, dan
splat-worker adalah image 24 GB yang memakai GPU: jangan menyala sampai Bagus mengaktifkannya.
"""

import re
from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[1] / "deploy" / "compose.yaml"


def services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def test_splat_worker_is_opt_in_so_autodeploy_does_not_build_or_start_it():
    assert services()["splat-worker"]["profiles"] == ["splat"]


def test_existing_services_still_start_by_default():
    assert {name for name, s in services().items() if "profiles" in s} == {"splat-worker"}


DOCKERFILE_SPLAT = Path(__file__).resolve().parents[1] / "deploy" / "Dockerfile.splat"


def test_trainer_layer_apt_packages_match_the_proven_image():
    """Mengubah daftar paket apt pertama membatalkan cache semua lapisan pelatih (±11 menit)."""
    text = DOCKERFILE_SPLAT.read_text(encoding="utf-8")
    pattern = r"apt-get install -y --no-install-recommends\s*\\((?:\s+[\w.+-]+\s*\\)+)"
    match = re.search(pattern, text)
    assert match, "RUN apt-get install pertama tidak ditemukan"
    assert re.findall(r"[\w.+-]+", match.group(1)) == ["git", "libgl1", "libglib2.0-0"]


def test_splat_worker_has_a_memory_limit_so_a_runaway_job_cannot_take_the_vm():
    s = services()["splat-worker"]
    assert (s["mem_limit"], s["memswap_limit"]) == ("8g", "8g")


def test_worker_has_the_splat_auto_switch_off_by_default():
    env = services()["worker"]["environment"]
    assert env["EUTOPOS_SPLAT_AUTO"] == "${EUTOPOS_SPLAT_AUTO:-0}"


def test_the_auto_switch_is_only_on_the_worker():
    with_switch = {
        name
        for name, s in services().items()
        if "EUTOPOS_SPLAT_AUTO" in (s.get("environment") or {})
    }
    assert with_switch == {"worker"}
