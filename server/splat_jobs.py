"""Antrean splat per versi peta, dengan satu pekerja dan pemulihan saat mulai ulang."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from server.db import MapVersion, SplatJob
from server.jobs import ERROR_MAX

DEFAULT_PARAMS = {"steps": 30000, "min_opacity": 0.02}
STATUSES = {"queued", "running", "done", "failed"}


def _save(session: Session, job: SplatJob) -> None:
    # Tanpa refresh: transaksi baru akan tertahan selama subprocess pelatihan yang panjang.
    session.add(job)
    session.commit()


def _existing(session: Session, map_version_id: int) -> SplatJob | None:
    stmt = select(SplatJob).where(SplatJob.map_version_id == map_version_id).with_for_update()
    return session.exec(stmt).first()


def enqueue(session: Session, map_version_id: int, params: dict | None = None) -> SplatJob:
    """Buat atau antre ulang pekerjaan yang sudah berhenti; tolak parameter tidak sah."""
    params = {} if params is None else params
    for key in params:
        if key not in DEFAULT_PARAMS:
            raise ValueError(f"unknown parameter: {key}")
    params = {**DEFAULT_PARAMS, **params}
    steps, opacity = params["steps"], params["min_opacity"]
    if isinstance(steps, bool) or not isinstance(steps, int) or steps <= 0:
        raise ValueError("steps must be an integer greater than zero, not bool")
    if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not 0 <= opacity < 1:
        raise ValueError("min_opacity must be a number in [0, 1)")
    if session.get(MapVersion, map_version_id) is None:
        raise ValueError("map version not found")
    job = _existing(session, map_version_id)
    if job is None:
        job = SplatJob(map_version_id=map_version_id, params=params)
        try:
            _save(session, job)
        except IntegrityError as exc:
            session.rollback()
            raise ValueError("already queued or running") from exc
        return job
    if job.status not in {"done", "failed"}:
        raise ValueError("already queued or running")
    job.status, job.params = "queued", params
    job.error, job.summary, job.stage = None, None, None
    job.started_at, job.finished_at = None, None
    _save(session, job)
    return job


def claim_next(session: Session) -> SplatJob | None:
    """Ambil pekerjaan queued tertua dan tandai running."""
    stmt = (
        select(SplatJob)
        .where(SplatJob.status == "queued")
        .order_by(SplatJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = session.exec(stmt).first()
    if job is None:
        session.rollback()
        return None
    job.status, job.stage, job.started_at = "running", None, datetime.now(UTC)
    _save(session, job)
    return job


def set_stage(session: Session, job: SplatJob, stage: str) -> None:
    job.stage = stage
    _save(session, job)


def finish(session: Session, job: SplatJob, summary: dict) -> None:
    job.status, job.summary, job.finished_at = "done", summary, datetime.now(UTC)
    _save(session, job)


def fail(session: Session, job: SplatJob, error: str) -> None:
    job.status, job.error, job.finished_at = "failed", error[-ERROR_MAX:], datetime.now(UTC)
    _save(session, job)


def recover_stale(session: Session) -> int:
    """Saat pekerja mulai: semua running kehilangan pemilik (hanya satu instance)."""
    stale = session.exec(select(SplatJob).where(SplatJob.status == "running")).all()
    for job in stale:
        fail(session, job, "the splat worker stopped mid-job; rebuild it")
    return len(stale)
