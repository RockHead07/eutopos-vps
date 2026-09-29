"""Catat lingkungan eksekusi di setiap hasil supaya bisa direproduksi (spike-plan.md, 5.1)."""

import os
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

import hloc
import pycolmap
import torch


def git_commit(path: Path):
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def env() -> dict:
    return {
        "eutopos_commit": git_commit(Path(__file__).parent),
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu": platform.processor(),
        "cpu_count": os.cpu_count(),
        "torch": torch.__version__,
        "torch_threads": torch.get_num_threads(),
        # run.py memakai GPU kalau ada (bawaan hloc); bench_localize.py mengikuti --device
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "pycolmap": pycolmap.__version__,
        "hloc": version("hloc"),
        "hloc_commit": git_commit(Path(hloc.__file__).parent),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(env(), indent=2))
