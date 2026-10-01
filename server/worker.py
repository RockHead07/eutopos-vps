"""Pekerja bangun peta (spesifikasi web-upload bagian 6).

Mengambil satu pekerjaan queued, menjalankan alat spike tahap demi tahap sebagai subprocess, lalu
mendaftarkan hasilnya sebagai versi kandidat. Satu pekerja, satu pekerjaan dalam satu waktu.

    python -m server.worker
"""

import json
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from sqlmodel import Session

from server import jobs
from server.db import Area, MapJob, engine_from_env, register
from server.map_layout import missing_files
from server.pipeline import (
    GLOBAL_RESIZE,
    MAX_KP,
    RESIZE,
    build_command,
    copy_frame_dirs,
    extract_commands,
    inspect_command,
    missing_inputs,
    run_dir,
)

DATA, MAPS = Path("/data"), Path("/maps")  # jalur di dalam container (deploy/compose.yaml)
MIN_FREE_BYTES = 20 * 1024**3
POLL_S = 5
LOG_LINES = 50


class StageError(RuntimeError):
    pass


def run(argv: list[str], log: Path) -> None:
    """Jalankan satu perintah, keluarannya ditambahkan ke log pekerjaan."""
    with open(log, "a", encoding="utf-8") as f:
        f.write("$ " + " ".join(argv) + "\n")
        f.flush()
        code = subprocess.run(argv, stdout=f, stderr=subprocess.STDOUT).returncode
    if code:
        raise StageError(f"perintah gagal (kode {code}): {Path(argv[1]).name}")


def log_tail(log: Path) -> str:
    if not log.exists():
        return ""
    return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_LINES:])


def delete_uploaded_videos(videos: list[dict], uploads: Path) -> None:
    """Video mentah dari unggahan website dihapus setelah frame diekstrak (privasi). Berkas yang
    diberikan lewat CLI berada di luar folder uploads dan tidak pernah disentuh."""
    root = uploads.resolve()
    for v in videos:
        p = Path(v["path"]).resolve()
        if p.is_file() and p.is_relative_to(root):
            p.unlink()


def process(
    session: Session,
    job: MapJob,
    data: Path,
    maps: Path,
    runner: Callable[[list[str], Path], None] = run,
    free_bytes: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free,
) -> None:
    job_dir = data / "jobs" / str(job.id)
    dataset, log = job_dir / "dataset", job_dir / "log.txt"
    map_dir = maps / job.area_id / f"job-{job.id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        jobs.set_stage(session, job, "extract")
        if free_bytes(data) < MIN_FREE_BYTES:
            raise StageError("ruang disk kurang dari 20 GB, pekerjaan tidak dimulai")
        if missing := missing_inputs(job.videos):
            raise StageError(f"berkas masukan tidak ditemukan: {', '.join(missing)}")
        for sub in ("mapping", "query"):
            (dataset / sub).mkdir(parents=True, exist_ok=True)
        copy_frame_dirs(job.videos, dataset)
        for argv in extract_commands(job.videos, dataset):
            runner(argv, log)
        delete_uploaded_videos(job.videos, data / "uploads")

        jobs.set_stage(session, job, "build")
        runner(build_command(dataset, map_dir), log)

        jobs.set_stage(session, job, "inspect")
        runner(inspect_command(map_dir), log)

        jobs.set_stage(session, job, "register")
        if missing := missing_files(map_dir, MAX_KP, RESIZE, GLOBAL_RESIZE):
            raise StageError(f"peta tidak lengkap: {', '.join(map(str, missing))}")
        summary = {
            "run": json.loads((run_dir(map_dir) / "summary.json").read_text(encoding="utf-8")),
            "inspect": json.loads((map_dir / "inspect.json").read_text(encoding="utf-8")),
        }
        version = register(session, job.area_id, session.get(Area, job.area_id).name, str(map_dir))
        jobs.finish(session, job, version.id, summary)
    except Exception as e:  # pekerjaan gagal, pekerja tetap hidup untuk pekerjaan berikutnya
        session.rollback()
        jobs.fail(session, job, f"{e}\n{log_tail(log)}".strip())


def main() -> None:
    engine = engine_from_env()
    with Session(engine) as s:
        if n := jobs.recover_stale(s):
            print(f"{n} pekerjaan tertinggal ditandai gagal", flush=True)
    print("pekerja siap", flush=True)
    while True:
        with Session(engine) as s:
            job = jobs.claim_next(s)
            if job is None:
                time.sleep(POLL_S)
                continue
            print(f"pekerjaan {job.id} ({job.area_id}) mulai", flush=True)
            process(s, job, DATA, MAPS)
            print(f"pekerjaan {job.id}: {job.status}", flush=True)


if __name__ == "__main__":
    main()
