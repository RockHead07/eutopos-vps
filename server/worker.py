"""Pekerja bangun peta (spesifikasi web-upload bagian 6).

Mengambil satu pekerjaan queued, menjalankan alat spike tahap demi tahap sebagai subprocess, lalu
mendaftarkan hasilnya sebagai versi kandidat. Satu pekerja, satu pekerjaan dalam satu waktu.

    python -m server.worker
"""

import json
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from sqlmodel import Session

from server import jobs
from server.db import Area, MapJob, MapVersion, engine_from_env, register
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
UPLOAD_MAX_AGE = timedelta(hours=24)
UPLOAD_ID = re.compile(r"^[A-Za-z0-9-]+$")  # pola ID buatan server, tanpa / atau ..
MIN_FREE_BYTES = 20 * 1024**3
POLL_S = 5
LOG_LINES = 50
# ponytail: satu batas untuk semua tahap. Peta lantai 10 (181 frame) selesai ±3,5 menit di GPU;
# batas ini hanya mencegah proses macet menahan satu-satunya antrean selamanya.
STAGE_TIMEOUT_S = 6 * 3600


class StageError(RuntimeError):
    pass


def worker_session(engine) -> Session:
    """Sesi pekerja: atribut tidak kedaluwarsa setelah commit, jadi membaca job tidak membuka
    transaksi baru yang tertahan selama subprocess berjalan."""
    return Session(engine, expire_on_commit=False)


def run(argv: list[str], log: Path) -> None:
    """Jalankan satu perintah, keluarannya ditambahkan ke log pekerjaan."""
    with open(log, "a", encoding="utf-8") as f:
        f.write("$ " + " ".join(argv) + "\n")
        f.flush()
        try:
            proc = subprocess.run(argv, stdout=f, stderr=subprocess.STDOUT, timeout=STAGE_TIMEOUT_S)
        except subprocess.TimeoutExpired as e:
            raise StageError(f"command exceeded {STAGE_TIMEOUT_S} s: {Path(argv[1]).name}") from e
    if proc.returncode:
        raise StageError(f"command failed (exit {proc.returncode}): {Path(argv[1]).name}")


def log_tail(log: Path) -> str:
    if not log.exists():
        return ""
    return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_LINES:])


def delete_upload_files(upload_ids: list[str], uploads: Path) -> None:
    """Hapus berkas tusd (data dan .info) untuk ID yang polanya sah. Berkas lain tidak disentuh."""
    for uid in upload_ids:
        if UPLOAD_ID.match(uid):
            for p in (uploads / uid, uploads / f"{uid}.info"):
                p.unlink(missing_ok=True)


def delete_uploaded_videos(videos: list[dict], uploads: Path) -> None:
    """Video mentah dari unggahan website dihapus setelah frame diekstrak (privasi). Berkas yang
    diberikan lewat CLI berada di luar folder uploads dan tidak pernah disentuh."""
    root = uploads.resolve()
    for v in videos:
        p = Path(v["path"]).resolve()
        if p.is_file() and p.is_relative_to(root):
            delete_upload_files([p.name], uploads)


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
    try:
        jobs.set_stage(session, job, "extract")
        job_dir.mkdir(parents=True, exist_ok=True)  # di dalam try: folder tak bisa ditulis = gagal
        if min(free_bytes(data), free_bytes(maps)) < MIN_FREE_BYTES:
            raise StageError("less than 20 GB of free disk; job not started")
        if missing := missing_inputs(job.videos):
            raise StageError(f"input files not found: {', '.join(missing)}")
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
            raise StageError(f"map is incomplete: {', '.join(map(str, missing))}")
        summary = {
            "run": json.loads((run_dir(map_dir) / "summary.json").read_text(encoding="utf-8")),
            "inspect": json.loads((map_dir / "inspect.json").read_text(encoding="utf-8")),
        }
        version = register(session, job.area_id, session.get(Area, job.area_id).name, str(map_dir))
        jobs.finish(session, job, version.id, summary)
    except Exception as e:  # pekerjaan gagal, pekerja tetap hidup untuk pekerjaan berikutnya
        session.rollback()
        # Privasi: video unggahan tidak boleh tertinggal walau pekerjaan gagal sebelum ekstraksi.
        delete_uploaded_videos(job.videos, data / "uploads")
        msg = str(e)[: jobs.ERROR_MAX // 2]  # pesan utama selalu utuh di awal
        tail = log_tail(log)[-(jobs.ERROR_MAX - len(msg) - 1) :]
        jobs.fail(session, job, f"{msg}\n{tail}".strip())


def purge(session: Session, job: MapJob, maps: Path) -> None:
    """Hapus peta hasil dan baris database sebuah pekerjaan yang diminta dihapus (DELETE /api/jobs).

    Folder frame di data/jobs/<id> sengaja dibiarkan: itu masukan yang bisa membangun ulang peta
    (video unggahan sudah dibuang setelah ekstraksi). Folder hanya dihapus kalau tepat
    <maps>/<area>/job-<id>; jalur lain berarti baris database rusak dan pekerjaan ditandai gagal.
    """
    root = maps.resolve()
    map_dir = (maps / job.area_id / f"job-{job.id}").resolve()
    try:
        version = session.get(MapVersion, job.map_version_id) if job.map_version_id else None
        if version is not None and version.status == "published":
            raise StageError("its map version is published; not deleted")
        if map_dir.parent.parent != root:
            raise StageError(f"refusing to delete outside the maps folder: {map_dir}")
        if map_dir.exists():
            shutil.rmtree(map_dir)
        session.delete(job)
        session.flush()  # job merujuk versi: baris job harus hilang lebih dulu
        if version is not None:
            session.delete(version)
        session.commit()
    except Exception as e:  # tetap hidup: pekerjaan ditandai gagal dan bisa dicoba hapus lagi
        session.rollback()
        jobs.fail(session, job, f"delete failed: {e}")


def main() -> None:
    from server.localizer import trust_megaloc_hub_repo  # impor berat (torch, hloc), hanya di sini

    # run.py memuat MegaLoc lewat torch.hub. Tanpa tanda tepercaya, torch bertanya y/N dan
    # subprocess tanpa masukan gagal. Jangan bergantung pada api yang kebetulan sudah menandainya.
    trust_megaloc_hub_repo()
    engine = engine_from_env()
    with worker_session(engine) as s:
        if n := jobs.recover_stale(s):
            print(f"{n} pekerjaan tertinggal ditandai gagal", flush=True)
    print("pekerja siap", flush=True)
    while True:
        with worker_session(engine) as s:
            job = jobs.claim_next(s)
            if job is None:
                for stale in jobs.expire_uploading(s, UPLOAD_MAX_AGE):
                    ids = [v["upload_id"] for v in stale.videos if v.get("upload_id")]
                    delete_upload_files(ids, DATA / "uploads")
                for gone in jobs.deleting(s):
                    print(f"pekerjaan {gone.id}: dihapus", flush=True)
                    purge(s, gone, MAPS)
                time.sleep(POLL_S)
                continue
            print(f"pekerjaan {job.id} ({job.area_id}) mulai", flush=True)
            process(s, job, DATA, MAPS)
            print(f"pekerjaan {job.id}: {job.status}", flush=True)


if __name__ == "__main__":
    main()
