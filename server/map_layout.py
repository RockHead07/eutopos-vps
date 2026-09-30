"""Susunan folder satu versi peta (keluaran spike/run.py --out), dipakai layanan dan manage."""

from pathlib import Path


def required_files(map_dir: Path, max_kp: int, resize: int, global_resize: int) -> list[Path]:
    run_dir = map_dir / f"kp{max_kp}-r{resize}"
    return [
        run_dir / "sfm" / "images.bin",
        run_dir / "sfm" / "points3D.bin",
        run_dir / "features.h5",
        map_dir / f"global-r{global_resize}.h5",
    ]


def missing_files(map_dir: Path, max_kp: int, resize: int, global_resize: int) -> list[Path]:
    return [p for p in required_files(map_dir, max_kp, resize, global_resize) if not p.is_file()]
