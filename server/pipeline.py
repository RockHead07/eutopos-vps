"""Perintah alat spike untuk satu pekerjaan bangun peta. Fungsi murni, bisa diuji tanpa GPU."""

import shutil
import sys
from pathlib import Path

SPIKE = Path(__file__).resolve().parents[1] / "spike"
# Sama dengan bawaan layanan (server/app.py), supaya peta hasil langsung bisa dimuat /localize.
MAX_KP, RESIZE, GLOBAL_RESIZE = 1024, 1024, 512
SEQ = 10  # pasangan berurutan untuk video (docs/spike-plan.md, uji video lantai 10)
ROLES = {"peta": ("mapping", 2.0), "uji": ("query", 0.5)}  # subfolder, fps ekstraksi


def run_dir(map_dir: Path) -> Path:
    return map_dir / f"kp{MAX_KP}-r{RESIZE}"


def missing_inputs(videos: list[dict]) -> list[str]:
    return [v["path"] for v in videos if not Path(v["path"]).exists()]


def copy_frame_dirs(videos: list[dict], dataset: Path) -> None:
    """Masukan berupa folder frame (misalnya hasil ekstraksi lama) disalin apa adanya."""
    for v in videos:
        src = Path(v["path"])
        if src.is_dir():
            shutil.copytree(src, dataset / ROLES[v["role"]][0], dirs_exist_ok=True)


def extract_commands(videos: list[dict], dataset: Path) -> list[list[str]]:
    cmds = []
    for role, (sub, fps) in ROLES.items():
        files = [v["path"] for v in videos if v["role"] == role and Path(v["path"]).is_file()]
        if files:
            script = str(SPIKE / "extract_frames.py")
            out = ["--out", str(dataset / sub), "--fps", str(fps)]
            cmds.append([sys.executable, script, *files, *out])
    return cmds


def build_command(dataset: Path, map_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(SPIKE / "run.py"),
        str(dataset),
        "--out",
        str(map_dir),
        "--max-kp",
        str(MAX_KP),
        "--resize",
        str(RESIZE),
        "--global-resize",
        str(GLOBAL_RESIZE),
        "--seq",
        str(SEQ),
    ]


def inspect_command(map_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(SPIKE / "inspect_map.py"),
        str(run_dir(map_dir)),
        "--html",
        str(map_dir / "report.html"),
        "--json",
        str(map_dir / "inspect.json"),
    ]
