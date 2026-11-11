"""Penyusun jalur dan argv splat. Tidak menjalankan alat atau mengakses filesystem."""

import sys
from pathlib import Path

from server.pipeline import SPIKE, run_dir

TRAIN_PYTHON = "/opt/conda/bin/python"
TRAINER = "/opt/gsplat/examples/simple_trainer.py"
# Lokasi CLI terbukti dari instalasi npm @playcanvas/splat-transform@3.10.3
# (README dan bin/cli.mjs).
SPLAT_TRANSFORM_CLI = "/opt/splat-transform/node_modules/@playcanvas/splat-transform/bin/cli.mjs"


def work_dir(data: Path, job_id: int) -> Path:
    """Folder kerja splat; job_id adalah id MapJob, bukan SplatJob."""
    return data / "jobs" / str(job_id) / "splat"


def dataset_dir(data: Path, job_id: int) -> Path:
    """Akar dataset hasil ekstraksi; job_id adalah id MapJob, bukan SplatJob."""
    return data / "jobs" / str(job_id) / "dataset"


def sfm_dir(map_dir: Path) -> Path:
    return run_dir(map_dir) / "sfm"


def prepare_command(sfm: Path, images: Path, out: Path) -> list[str]:
    """images adalah akar dataset, karena nama gambar COLMAP berawalan mapping/."""
    return [
        sys.executable,
        str(SPIKE / "splat_prepare.py"),
        "--sfm",
        str(sfm),
        "--images",
        str(images),
        "--out",
        str(out),
    ]


def _validate_steps(steps: int) -> None:
    if isinstance(steps, bool) or not isinstance(steps, int) or steps <= 0:
        raise ValueError("steps must be an integer greater than zero, not bool")


def train_command(prepared: Path, result: Path, steps: int) -> list[str]:
    _validate_steps(steps)
    return [
        TRAIN_PYTHON,
        TRAINER,
        "default",
        "--data-dir",
        str(prepared),
        "--data-factor",
        "1",
        "--result-dir",
        str(result),
        "--max-steps",
        str(steps),
        "--eval-steps",
        str(steps),
        "--save-steps",
        str(steps),
        "--ply-steps",
        str(steps),
        "--save-ply",
        "--no-normalize-world-space",
        "--disable-viewer",
        "--disable-video",
    ]


def ply_path(result: Path, steps: int) -> Path:
    _validate_steps(steps)
    # Jalur ply/point_cloud_<steps-1>.ply terbukti pada pelatihan 30.000 langkah
    # 3 Nov (simple_trainer.py:814).
    return result / "ply" / f"point_cloud_{steps - 1}.ply"


def check_command(ply: Path, sfm: Path) -> list[str]:
    """sfm adalah model asli, bukan model hasil prepare; ambang dimiliki alatnya."""
    return [
        sys.executable,
        str(SPIKE / "splat_check_frame.py"),
        "--ply",
        str(ply),
        "--sfm",
        str(sfm),
    ]


def convert_command(ply: Path, sog: Path) -> list[str]:
    # Urutan -g cpu <ply> -H 0 <sog> terbukti pada konversi 3 Nov dan README splat-transform 3.10.3.
    return ["node", SPLAT_TRANSFORM_CLI, "-g", "cpu", str(ply), "-H", "0", str(sog)]
