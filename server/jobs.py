"""Antrean pekerjaan bangun peta di tabel map_job (spesifikasi web-upload bagian 4 sampai 6).

Satu pekerja, jadi FOR UPDATE SKIP LOCKED di sini lebih sebagai pengaman daripada kebutuhan. Pola
antrean ini disebut di dokumentasi PostgreSQL untuk SELECT ... FOR UPDATE.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from server.db import Area, MapJob

ROLES = {"peta", "uji"}
ERROR_MAX = 4000  # cukup untuk 50 baris log terakhir


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
        raise ValueError(f"peran video tidak dikenal: {sorted(unknown)}, pakai peta atau uji")
    if not any(v["role"] == "peta" for v in videos):
        raise ValueError("butuh minimal satu video berperan peta")
    # Frame dinamai <nama video>_<nomor>.jpg: dua video bernama sama saling menimpa frame.
    # Video unggahan belum punya path saat dibuat; namanya dibuat unik oleh server (ID unggahan).
    paths = [Path(v["path"]) for v in videos if v.get("path")]
    stems = [p.stem for p in paths if p.suffix]
    if dup := sorted({s for s in stems if stems.count(s) > 1}):
        raise ValueError(f"nama video kembar {dup}, ganti nama salah satunya")
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
        fail(session, job, "pekerja berhenti di tengah pekerjaan, unggah atau antrekan ulang")
    return len(stale)


def expire_uploading(session: Session, max_age: timedelta) -> list[MapJob]:
    """Unggahan yang ditinggal (spesifikasi bagian 10): uploading terlalu lama menjadi failed."""
    limit = datetime.now(UTC) - max_age
    stmt = select(MapJob).where(MapJob.status == "uploading", MapJob.created_at < limit)
    # Kunci baris: pre-finish yang mengantrekan tepat di batas 24 jam tidak tertimpa failed.
    stmt = stmt.with_for_update(skip_locked=True)
    stale = session.exec(stmt).all()
    for job in stale:
        fail(session, job, "unggahan tidak selesai dalam 24 jam, buat sesi baru")
    return stale
