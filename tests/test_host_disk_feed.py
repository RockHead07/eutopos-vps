"""Umpan drive tuan rumah yang ditulis deploy/autodeploy.sh dan dibaca server/system.py."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from server import system

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "autodeploy.sh"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="butuh bash")


def run_feed(tmp_path: Path, env_file: str | None, drive: Path | None):
    """Jalankan hanya write_host_disk dari skrip asli (skrip penuh akan mem-pull dan deploy)."""
    body = re.search(r"^write_host_disk\(\) \{\n.*?^\}\n", SCRIPT.read_text(), re.S | re.M)
    assert body, "write_host_disk tidak ada di autodeploy.sh"
    (tmp_path / "deploy").mkdir()
    if env_file is not None:
        (tmp_path / "deploy" / ".env").write_text(env_file, encoding="utf-8")
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOST_DRIVE": str(drive or tmp_path / "tidak-ada"),
    }
    return subprocess.run(
        # Jalur lengkap: di Windows "bash" polos jatuh ke launcher WSL di System32.
        [shutil.which("bash"), "-c", body.group(0) + "\nset -e\nwrite_host_disk"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def test_feed_is_written_next_to_the_maps_and_the_server_can_read_it(tmp_path: Path):
    maps = tmp_path / "maps"
    maps.mkdir()
    done = run_feed(tmp_path, f"POSTGRES_PASSWORD=x\nEUTOPOS_MAPS_DIR={maps}\n", tmp_path)
    assert done.returncode == 0, done.stderr
    feed = json.loads((maps / ".host-disk.json").read_text(encoding="utf-8"))
    assert feed["mount"] == "C:" and feed["total_bytes"] > feed["free_bytes"] > 0
    host = system.read_host_disk(maps / ".host-disk.json")
    assert host is not None and host.stale is False and host.free_bytes == feed["free_bytes"]
    assert not (maps / ".host-disk.json.tmp").exists()


def test_quoted_value_in_env_is_handled(tmp_path: Path):
    maps = tmp_path / "maps"
    maps.mkdir()
    assert run_feed(tmp_path, f'EUTOPOS_MAPS_DIR="{maps}"\n', tmp_path).returncode == 0
    assert (maps / ".host-disk.json").exists()


@pytest.mark.parametrize(
    "env_file", [None, "EUTOPOS_DATA_DIR=/x\n", "EUTOPOS_MAPS_DIR=/tidak/ada\n"]
)
def test_missing_env_or_folder_is_a_quiet_no_op_that_never_fails_the_deploy(tmp_path, env_file):
    done = run_feed(tmp_path, env_file, tmp_path)
    assert done.returncode == 0 and not list(tmp_path.rglob(".host-disk.json*"))


def test_not_on_wsl_writes_nothing(tmp_path: Path):
    maps = tmp_path / "maps"
    maps.mkdir()
    done = run_feed(tmp_path, f"EUTOPOS_MAPS_DIR={maps}\n", drive=None)  # HOST_DRIVE tidak ada
    assert done.returncode == 0 and not (maps / ".host-disk.json").exists()
