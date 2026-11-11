"""Pekerja bangun peta (spesifikasi web-upload bagian 6).

Mengambil satu pekerjaan queued, menjalankan alat spike tahap demi tahap sebagai subprocess, lalu
mendaftarkan hasilnya sebagai versi kandidat. Satu pekerja, satu pekerjaan dalam satu waktu.

    python -m server.worker
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import AbstractContextManager as ContextManager
from pathlib import Path

from sqlmodel import Session, select

from server import jobs, splat_jobs, splat_pipeline
from server.db import Area, MapJob, MapVersion, engine_from_env, register
from server.gpu_lock import gpu_lock
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
from server.previews import make_preview
from server.system import HostDisk, get_host_disk_path, read_host_disk
from server.thumbs import make_thumbs
from server.video_meta import recorded_at

DATA, MAPS = Path("/data"), Path("/maps")  # jalur di dalam container (deploy/compose.yaml)
UPLOAD_MAX_AGE = jobs.UPLOAD_MAX_AGE
UPLOAD_ID = re.compile(r"^[A-Za-z0-9-]+$")  # pola ID buatan server, tanpa / atau ..
MIN_FREE_BYTES = 20 * 1024**3
# Drive Windows di bawah disk virtual WSL (aturan proyek: sisakan 30 GB). Disk virtual melapor
# 1 TB walau drive sebenarnya tinggal puluhan GB, jadi batas di atas tidak melindungi drive itu.
MIN_HOST_FREE_BYTES = 30 * 1024**3
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


def stamp_recorded(session: Session, job: MapJob) -> None:
    """Catat waktu rekam tiap video sebelum videonya dihapus: waktu itu hanya ada di dalam berkas.

    None berarti tidak diketahui (folder frame, tanpa metadata, atau nilai tak masuk akal).
    """
    stamped = []
    for v in job.videos:
        p = Path(v["path"])
        when = recorded_at(p) if p.is_file() else None
        stamped.append({**v, "recorded_at": when.isoformat() if when else None})
    jobs.set_videos(session, job, stamped)


def backfill_previews(session: Session, data: Path, maps: Path) -> tuple[int, int]:
    """Buat pratinjau untuk job selesai yang belum punya, dari frame yang masih tersimpan.

    Hasil: (dibuat, dilewati). Waktu rekam tidak bisa diisi ulang: videonya sudah dihapus.
    """
    made = skipped = 0
    root = maps.resolve()
    for job in session.exec(select(MapJob).where(MapJob.status == "done")).all():
        map_dir = (maps / job.area_id / f"job-{job.id}").resolve()
        out = map_dir / "preview.jpg"
        if map_dir.parent.parent != root or not map_dir.is_dir() or out.exists():
            continue
        mapping = data / "jobs" / str(job.id) / "dataset" / "mapping"
        if make_preview(mapping, job.videos, out):
            made += 1
        else:
            skipped += 1
    return made, skipped


def backfill_thumbs(session: Session, data: Path, maps: Path) -> tuple[int, int]:
    """Foto kecil frame scan untuk job selesai yang belum punya (dari frame yang masih tersimpan).

    Hasil: (job dibuatkan, job dilewati karena frame-nya sudah tidak ada).
    """
    made = skipped = 0
    root = maps.resolve()
    for job in session.exec(select(MapJob).where(MapJob.status == "done")).all():
        map_dir = (maps / job.area_id / f"job-{job.id}").resolve()
        out = map_dir / "thumbs"
        if map_dir.parent.parent != root or not map_dir.is_dir() or out.is_dir():
            continue
        if make_thumbs(data / "jobs" / str(job.id) / "dataset" / "mapping", out):
            made += 1
        else:
            skipped += 1
    return made, skipped


def splat_auto_enabled() -> bool:
    """Pemicu 3D otomatis hanya hidup bila diminta, bersama profil compose `splat` (README 10).

    Tanpa pekerja splat, pekerjaan 3D menumpuk berstatus queued dan menahan penghapusan versi.
    """
    return os.environ.get("EUTOPOS_SPLAT_AUTO", "").strip().lower() in {"1", "true", "yes", "on"}


def queue_splat(session: Session, version_id: int) -> None:
    """3D adalah tambahan: gagal mengantre tidak boleh menggagalkan peta yang sudah jadi."""
    if not splat_auto_enabled():
        return
    try:
        splat_jobs.enqueue(session, version_id)
    except Exception as exc:
        session.rollback()
        detail = " ".join(str(exc).splitlines())
        print(
            f"warning: could not queue a 3D build for version {version_id}: {detail}",
            file=sys.stderr,
            flush=True,
        )


def process(
    session: Session,
    job: MapJob,
    data: Path,
    maps: Path,
    runner: Callable[[list[str], Path], None] = run,
    free_bytes: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free,
    host_disk: Callable[[Path], HostDisk | None] = lambda m: read_host_disk(get_host_disk_path(m)),
    lock: Callable[[], ContextManager[None]] | None = None,
) -> None:
    lock = (lambda: gpu_lock(session.get_bind())) if lock is None else lock
    job_dir = data / "jobs" / str(job.id)
    dataset, log = job_dir / "dataset", job_dir / "log.txt"
    map_dir = maps / job.area_id / f"job-{job.id}"
    try:
        jobs.set_stage(session, job, "gpu_wait")
        with lock():
            jobs.set_stage(session, job, "extract")
            # di dalam try: folder tak bisa ditulis = gagal
            job_dir.mkdir(parents=True, exist_ok=True)
            if min(free_bytes(data), free_bytes(maps)) < MIN_FREE_BYTES:
                raise StageError("less than 20 GB of free disk; job not started")
            # ponytail: umpan hilang atau basi (timer deploy mati) tidak memblokir pekerjaan:
            # tanpa angka segar tidak ada dasar menolak. Balik bila disk penuh lebih mahal.
            host = host_disk(maps)
            if host and not host.stale and host.free_bytes < MIN_HOST_FREE_BYTES:
                raise StageError(
                    f"less than 30 GB of free space on host drive {host.mount}; job not started"
                )
            if missing := missing_inputs(job.videos):
                raise StageError(f"input files not found: {', '.join(missing)}")
            stamp_recorded(session, job)
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
            make_preview(dataset / "mapping", job.videos, map_dir / "preview.jpg")
            make_thumbs(dataset / "mapping", map_dir / "thumbs")

            jobs.set_stage(session, job, "register")
            if missing := missing_files(map_dir, MAX_KP, RESIZE, GLOBAL_RESIZE):
                raise StageError(f"map is incomplete: {', '.join(map(str, missing))}")
            summary = {
                "run": json.loads((run_dir(map_dir) / "summary.json").read_text(encoding="utf-8")),
                "inspect": json.loads((map_dir / "inspect.json").read_text(encoding="utf-8")),
            }
            version = register(
                session, job.area_id, session.get(Area, job.area_id).name, str(map_dir)
            )
            jobs.finish(session, job, version.id, summary)
            queue_splat(session, version.id)
    except Exception as e:  # pekerjaan gagal, pekerja tetap hidup untuk pekerjaan berikutnya
        session.rollback()
        # Privasi: video unggahan tidak boleh tertinggal walau pekerjaan gagal sebelum ekstraksi.
        delete_uploaded_videos(job.videos, data / "uploads")
        msg = str(e)[: jobs.ERROR_MAX // 2]  # pesan utama selalu utuh di awal
        tail = log_tail(log)[-(jobs.ERROR_MAX - len(msg) - 1) :]
        jobs.fail(session, job, f"{msg}\n{tail}".strip())


def purge(
    session: Session,
    job: MapJob,
    maps: Path,
    uploads: Path = DATA / "uploads",
    data: Path = DATA,
) -> None:
    """Hapus peta hasil dan baris database sebuah pekerjaan yang diminta dihapus (DELETE /api/jobs).

    Folder frame di data/jobs/<id> sengaja dibiarkan: itu masukan yang bisa membangun ulang peta
    (video unggahan sudah dibuang setelah ekstraksi). Folder kerja splat (data/jobs/<id>/splat,
    PLY ratusan MB yang tertinggal bila pembangunan 3D gagal) ikut dihapus. Folder peta hanya
    dihapus kalau tepat <maps>/<area>/job-<id>; jalur lain berarti baris database rusak dan
    pekerjaan ditandai gagal.
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
        splat_work = splat_pipeline.work_dir(data, job.id)  # jalurnya turunan id bilangan bulat
        if splat_work.is_dir() and not splat_work.is_symlink():
            shutil.rmtree(splat_work)
        uids = [v["upload_id"] for v in job.videos if isinstance(v, dict) and v.get("upload_id")]
        delete_upload_files(uids, uploads)
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
