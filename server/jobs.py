"""Antrean pekerjaan bangun peta di tabel map_job (spesifikasi web-upload bagian 4 sampai 6).

Satu pekerja, jadi FOR UPDATE SKIP LOCKED di sini lebih sebagai pengaman daripada kebutuhan. Pola
antrean ini disebut di dokumentasi PostgreSQL untuk SELECT ... FOR UPDATE.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from server.db import Area, MapJob, MapVersion

ROLES = {"peta", "uji"}
ERROR_MAX = 4000  # cukup untuk 50 baris log terakhir
DELETABLE = {"done", "failed"}  # pekerjaan yang sudah berhenti
STALL_AFTER = timedelta(minutes=10)
UPLOAD_IDLE_MAX = timedelta(hours=6)
UPLOAD_MAX_AGE = timedelta(hours=24)


def newest_activity(job: MapJob) -> datetime:
    """Waktu aktivitas paling baru dari video-video job, atau created_at jika belum ada."""
    acts: list[datetime] = []
    for v in job.videos:
        if isinstance(v, dict) and (act := v.get("activity_at")):
            try:
                dt = datetime.fromisoformat(act)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                acts.append(dt)
            except ValueError:
                pass
    if acts:
        return max(acts)
    created = job.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return created


def is_stalled(job: MapJob, now: datetime | None = None) -> bool:
    """Periksa apakah pekerjaan uploading mandek (tidak ada data masuk > STALL_AFTER).

    Aturan tunggal di server: status uploading, setidaknya satu video belum lengkap
    (uploaded bukan True), dan aktivitas paling baru (fallback created_at) lebih
    tua dari STALL_AFTER (10 menit).
    """
    if job.status != "uploading":
        return False
    if not any(v.get("uploaded") is not True for v in job.videos if isinstance(v, dict)):
        return False
    if now is None:
        now = datetime.now(UTC)
    return (now - newest_activity(job)) > STALL_AFTER


def _save(session: Session, job: MapJob) -> None:
    # Tanpa refresh: refresh membuka transaksi baru yang tertahan selama subprocess berjam-jam
    # di pekerja ("idle in transaction" di PostgreSQL). Sesi biasa memuat ulang atribut sendiri.
    session.add(job)
    session.commit()


def create_job(
    session: Session,
    area_id: str,
    area_name: str,
    created_by: str,
    videos: list[dict],
    status: str = "uploading",
) -> MapJob:
    """Buat pekerjaan. Ditolak di sini, bukan di GPU, kalau videonya tidak bisa jadi peta."""
    if unknown := {v["role"] for v in videos} - ROLES:
        raise ValueError(f"unknown video role: {sorted(unknown)}; use peta or uji")
    if not any(v["role"] == "peta" for v in videos):
        raise ValueError("at least one video with role peta is required")
    # Frame dinamai <nama video>_<nomor>.jpg: dua video bernama sama saling menimpa frame.
    # Video unggahan belum punya path saat dibuat; namanya dibuat unik oleh server (ID unggahan).
    paths = [Path(v["path"]) for v in videos if v.get("path")]
    stems = [p.stem for p in paths if p.suffix]
    if dup := sorted({s for s in stems if stems.count(s) > 1}):
        raise ValueError(f"duplicate video names {dup}; rename one of them")
    if session.get(Area, area_id) is None:
        session.add(Area(id=area_id, name=area_name))
    job = MapJob(area_id=area_id, created_by=created_by, status=status, videos=videos)
    _save(session, job)
    return job


def claim_next(session: Session) -> MapJob | None:
    """Ambil pekerjaan queued tertua dan tandai running."""
    stmt = (
        select(MapJob)
        .where(MapJob.status == "queued")
        .order_by(MapJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = session.exec(stmt).first()
    if job is None:
        session.rollback()  # lepas transaksi yang dibuka SELECT
        return None
    job.status, job.stage, job.started_at = "running", None, datetime.now(UTC)
    _save(session, job)
    return job


def set_videos(session: Session, job: MapJob, videos: list[dict]) -> None:
    """Ganti daftar video (list baru, supaya perubahan kolom JSON terdeteksi)."""
    job.videos = videos
    _save(session, job)


def set_stage(session: Session, job: MapJob, stage: str) -> None:
    job.stage = stage
    _save(session, job)


def finish(session: Session, job: MapJob, map_version_id: int, summary: dict) -> None:
    job.status, job.map_version_id, job.summary = "done", map_version_id, summary
    job.finished_at = datetime.now(UTC)
    _save(session, job)


def fail(session: Session, job: MapJob, error: str) -> None:
    job.status, job.error, job.finished_at = "failed", error[-ERROR_MAX:], datetime.now(UTC)
    _save(session, job)


def recover_stale(session: Session) -> int:
    """Saat pekerja mulai: pekerjaan running tidak punya pemilik lagi (hanya ada satu pekerja)."""
    stale = session.exec(select(MapJob).where(MapJob.status == "running")).all()
    for job in stale:
        fail(session, job, "the worker stopped mid-job; upload or queue it again")
    return len(stale)


def expire_uploading(
    session: Session,
    max_age: timedelta = UPLOAD_MAX_AGE,
    idle_max: timedelta = UPLOAD_IDLE_MAX,
) -> list[MapJob]:
    """Unggahan yang ditinggal (spesifikasi bagian 10): uploading terlalu lama menjadi failed."""
    now = datetime.now(UTC)
    stmt = select(MapJob).where(MapJob.status == "uploading").with_for_update(skip_locked=True)
    stale: list[MapJob] = []
    for job in session.exec(stmt).all():
        created = job.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created < (now - max_age):
            fail(session, job, "upload did not finish within 24 hours; start a new session")
            stale.append(job)
        elif newest_activity(job) < (now - idle_max):
            fail(session, job, "upload stalled for 6 hours; start a new session")
            stale.append(job)
    return stale


def delete_block_reason(session: Session, job: MapJob) -> str | None:
    """Alasan pekerjaan belum boleh dihapus, atau None. 'deleting' lolos: permintaan ulang aman."""
    if job.status == "deleting":
        return None
    if job.status == "uploading":
        if not is_stalled(job):
            return "upload is still receiving data"
    elif job.status not in DELETABLE:
        return f"job is {job.status}; only finished or failed jobs can be deleted"
    version = session.get(MapVersion, job.map_version_id) if job.map_version_id else None
    if version is not None and version.status == "published":
        return "its map version is published; publish another version first"
    return None


def request_delete(session: Session, job: MapJob) -> None:
    """Tandai untuk dihapus. Folder peta baru hilang di pekerja: api memasang /maps hanya-baca."""
    job.status = "deleting"
    _save(session, job)


def deleting(session: Session) -> list[MapJob]:
    return list(session.exec(select(MapJob).where(MapJob.status == "deleting").order_by(MapJob.id)))
