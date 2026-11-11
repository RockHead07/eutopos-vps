"""Uji antrean splat dan migrasi 0007, tanpa GPU atau PostgreSQL."""

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from server import db, jobs


@pytest.fixture
def splat_jobs():
    return importlib.import_module("server.splat_jobs")


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


@pytest.fixture
def version_id(session):
    return db.register(session, "test-area", "Test area", "/maps/test-area/v1").id


def make_job(session, version_id, **values):
    job = db.SplatJob(map_version_id=version_id, **values)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def test_enqueue_creates_queued_row_with_default_params(session, version_id, splat_jobs):
    job = splat_jobs.enqueue(session, version_id)
    assert not session.in_transaction()
    assert splat_jobs.DEFAULT_PARAMS == {"steps": 30000, "min_opacity": 0.02}
    assert splat_jobs.STATUSES == {"queued", "running", "done", "failed"}
    assert (job.map_version_id, job.status) == (version_id, "queued")
    assert job.params == {"steps": 30000, "min_opacity": 0.02}
    assert job.created_at is not None
    assert (job.stage, job.error, job.summary, job.started_at, job.finished_at) == (None,) * 5
    assert session.get(db.SplatJob, job.id).params == job.params
    assert len(session.exec(select(db.SplatJob)).all()) == 1


def test_enqueue_resets_a_failed_row_and_clears_error(session, version_id, splat_jobs, monkeypatch):
    old = datetime.now(UTC) - timedelta(hours=1)
    job = make_job(
        session,
        version_id,
        status="failed",
        stage="train",
        error="old failure",
        summary={"old": True},
        params={"steps": 1, "min_opacity": 0.5},
        started_at=old,
        finished_at=old,
    )
    job_id, created_at = job.id, job.created_at
    statements = []
    original_exec = session.exec

    def capture(statement, *args, **kwargs):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return original_exec(statement, *args, **kwargs)

    monkeypatch.setattr(session, "exec", capture)
    again = splat_jobs.enqueue(session, version_id)
    assert not session.in_transaction()
    assert (again.id, again.created_at, again.status) == (job_id, created_at, "queued")
    assert (again.error, again.summary, again.stage, again.started_at, again.finished_at) == (
        None,
    ) * 5
    assert again.params == splat_jobs.DEFAULT_PARAMS
    assert any("FOR UPDATE" in sql and "splat_job.map_version_id =" in sql for sql in statements)
    session.expire_all()
    assert session.get(db.SplatJob, job_id).error is None
    assert len(session.exec(select(db.SplatJob)).all()) == 1


@pytest.mark.parametrize("status", ["queued", "running"])
def test_enqueue_rejects_queued_and_running(session, version_id, splat_jobs, status):
    job = make_job(session, version_id, status=status)
    before = job.model_dump()
    with pytest.raises(ValueError, match=r"^already queued or running$"):
        splat_jobs.enqueue(session, version_id)
    session.expire_all()
    assert session.get(db.SplatJob, job.id).model_dump() == before
    assert len(session.exec(select(db.SplatJob)).all()) == 1


def test_claim_next_takes_oldest_queued_and_marks_running(
    session, version_id, splat_jobs, monkeypatch
):
    job = make_job(session, version_id, stage="old stage")
    job_id = job.id
    session.rollback()
    statements = []
    original_exec = session.exec

    def capture(statement, *args, **kwargs):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return original_exec(statement, *args, **kwargs)

    monkeypatch.setattr(session, "exec", capture)
    got = splat_jobs.claim_next(session)
    assert not session.in_transaction()
    assert (got.id, got.status, got.stage) == (job_id, "running", None)
    assert got.started_at is not None
    assert "ORDER BY splat_job.id" in statements[0]
    assert "FOR UPDATE SKIP LOCKED" in statements[0]
    assert "LIMIT" in statements[0]
    session.expire_all()
    assert session.get(db.SplatJob, job_id).status == "running"


def test_claim_next_returns_none_when_empty(session, splat_jobs):
    assert splat_jobs.claim_next(session) is None
    assert not session.in_transaction()


def test_recover_stale_marks_running_failed_and_counts_them(session, version_id, splat_jobs):
    first = make_job(session, version_id, status="running", stage="train")
    other_id = db.register(session, "test-area", "Test area", "/maps/test-area/v2").id
    second = make_job(session, other_id, status="running", stage="check")
    assert splat_jobs.recover_stale(session) == 2
    session.expire_all()
    for job, stage in [(first, "train"), (second, "check")]:
        assert (job.status, job.stage) == ("failed", stage)
        assert job.error == "the splat worker stopped mid-job; rebuild it"
        assert job.finished_at is not None


def test_fail_truncates_error_to_jobs_error_max(session, version_id, splat_jobs):
    job = make_job(session, version_id)
    error = "discard this prefix:" + "x" * jobs.ERROR_MAX + ":keep this tail"
    splat_jobs.fail(session, job, error)
    assert job.error == error[-jobs.ERROR_MAX :]
    assert len(job.error) == jobs.ERROR_MAX


def test_one_row_per_version(session, version_id):
    make_job(session, version_id)
    session.add(db.SplatJob(map_version_id=version_id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert len(session.exec(select(db.SplatJob)).all()) == 1


def test_enqueue_resets_a_done_row_too(session, version_id, splat_jobs):
    old = datetime.now(UTC) - timedelta(hours=1)
    job = make_job(
        session,
        version_id,
        status="done",
        stage="place",
        summary={"kept": 123},
        started_at=old,
        finished_at=old,
    )
    job_id, created_at = job.id, job.created_at
    params = {"steps": 7000, "min_opacity": 0.1}
    again = splat_jobs.enqueue(session, version_id, params)
    assert (again.id, again.created_at, again.status) == (job_id, created_at, "queued")
    assert (again.summary, again.finished_at, again.started_at, again.stage, again.error) == (
        None,
    ) * 5
    assert again.params == params
    session.expire_all()
    assert session.get(db.SplatJob, job_id).params == params


def test_enqueue_merges_params_over_defaults(session, version_id, splat_jobs):
    params = {"steps": 7000}
    job = splat_jobs.enqueue(session, version_id, params)
    assert job.params == {"steps": 7000, "min_opacity": 0.02}
    assert params == {"steps": 7000}
    assert splat_jobs.DEFAULT_PARAMS == {"steps": 30000, "min_opacity": 0.02}


@pytest.mark.parametrize(
    ("params", "key"),
    [
        ({"unknown": 1}, "unknown"),
        ({"steps": 0}, "steps"),
        ({"steps": -1}, "steps"),
        ({"steps": True}, "steps"),
        ({"steps": "30000"}, "steps"),
        ({"min_opacity": -0.1}, "min_opacity"),
        ({"min_opacity": 1.0}, "min_opacity"),
        ({"min_opacity": "x"}, "min_opacity"),
        ({"min_opacity": False}, "min_opacity"),
        ({"min_opacity": True}, "min_opacity"),
        ({"min_opacity": float("nan")}, "min_opacity"),
    ],
    ids=[
        "unknown-key",
        "zero-steps",
        "negative-steps",
        "bool-steps",
        "string-steps",
        "negative-opacity",
        "one-opacity",
        "string-opacity",
        "false-opacity",
        "true-opacity",
        "nan-opacity",
    ],
)
def test_enqueue_rejects_bad_params(session, version_id, splat_jobs, params, key):
    with pytest.raises(ValueError, match=key):
        splat_jobs.enqueue(session, version_id, params)
    assert session.exec(select(db.SplatJob)).all() == []


def test_enqueue_rejects_unknown_version(session, splat_jobs):
    with pytest.raises(ValueError, match=r"^map version not found$"):
        splat_jobs.enqueue(session, 999)
    assert session.exec(select(db.SplatJob)).all() == []


def test_enqueue_insert_race_maps_to_value_error(session, version_id, splat_jobs, monkeypatch):
    job = splat_jobs.enqueue(session, version_id)
    job_id = job.id
    monkeypatch.setattr(splat_jobs, "_existing", lambda session, map_version_id: None)
    with pytest.raises(ValueError, match=r"^already queued or running$"):
        splat_jobs.enqueue(session, version_id)
    assert not session.in_transaction()
    session.expire_all()
    assert session.get(db.SplatJob, job_id).status == "queued"
    assert session.get(db.MapVersion, version_id) is not None
    assert len(session.exec(select(db.SplatJob)).all()) == 1


def test_claim_next_skips_non_queued(session, splat_jobs):
    for status in ["running", "done", "failed"]:
        version = db.register(session, "test-area", "Test area", f"/maps/{status}")
        make_job(session, version.id, status=status)
    assert splat_jobs.claim_next(session) is None
    assert not session.in_transaction()


def test_claim_next_is_fifo_by_id(session, splat_jobs):
    ids = []
    for i in range(3):
        version = db.register(session, "test-area", "Test area", f"/maps/v{i}")
        # created_at sengaja terbalik: FIFO ditentukan id, bukan waktu.
        job = make_job(session, version.id, created_at=datetime.now(UTC) - timedelta(days=i))
        ids.append(job.id)
    assert ids == sorted(ids)
    assert [splat_jobs.claim_next(session).id for _ in ids] == ids
    assert splat_jobs.claim_next(session) is None


def test_fail_keeps_the_stage_and_sets_finished_at(session, version_id, splat_jobs):
    job = make_job(session, version_id, status="running")
    splat_jobs.set_stage(session, job, "check")
    splat_jobs.fail(session, job, "frame mismatch")
    assert not session.in_transaction()
    session.expire_all()
    assert (job.status, job.stage, job.error) == ("failed", "check", "frame mismatch")
    assert job.finished_at is not None


def test_finish_sets_done_summary_and_finished_at(session, version_id, splat_jobs):
    job = make_job(session, version_id, status="running")
    summary = {"kept": 123, "stages": {"train": 1.5}}
    splat_jobs.finish(session, job, summary)
    assert not session.in_transaction()
    session.expire_all()
    assert (job.status, job.summary) == ("done", summary)
    assert job.finished_at is not None


def test_recover_stale_leaves_queued_done_failed_alone(session, splat_jobs):
    before = {}
    for status in ["queued", "done", "failed"]:
        version = db.register(session, "test-area", "Test area", f"/maps/{status}")
        job = make_job(session, version.id, status=status, error="unchanged", summary={"kept": 1})
        before[job.id] = job.model_dump()
    version = db.register(session, "test-area", "Test area", "/maps/running")
    make_job(session, version.id, status="running")
    assert splat_jobs.recover_stale(session) == 1
    session.expire_all()
    for job_id, values in before.items():
        assert session.get(db.SplatJob, job_id).model_dump() == values


def test_recover_stale_returns_zero_when_nothing_running(session, splat_jobs):
    assert splat_jobs.recover_stale(session) == 0


def test_set_stage_commits_without_refresh(session, version_id, splat_jobs, monkeypatch):
    job = make_job(session, version_id, status="running")
    job_id = job.id
    refresh = []
    monkeypatch.setattr(session, "refresh", lambda *args, **kwargs: refresh.append(args))
    splat_jobs.set_stage(session, job, "train")
    assert refresh == []
    assert not session.in_transaction()
    session.expire_all()
    assert session.get(db.SplatJob, job_id).stage == "train"


def test_migration_0007_up_and_down(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect

    cfg = Config("server/alembic.ini")
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    def present():
        engine = create_engine(url)
        try:
            with engine.connect() as connection:
                return "splat_job" in inspect(connection).get_table_names()
        finally:
            engine.dispose()

    command.upgrade(cfg, "head")
    assert present()
    assert ScriptDirectory.from_config(cfg).get_revision("0007").down_revision == "0006"
    command.downgrade(cfg, "0006")
    assert not present()
    command.upgrade(cfg, "head")
    assert present()


def _fk_engine(url):
    """SQLite tidak menegakkan FK kecuali dinyalakan; PostgreSQL selalu menegakkannya."""
    from sqlalchemy import event

    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _count_splat_rows_after_deleting_the_version(engine):
    from sqlalchemy import text

    with engine.begin() as c:
        c.execute(text("INSERT INTO area (id, name) VALUES ('a', 'A')"))
        c.execute(
            text(
                "INSERT INTO map_version (id, area_id, version, path, status, created_at) "
                "VALUES (1, 'a', 1, '/maps/a/v1', 'candidate', '2026-11-10 00:00:00')"
            )
        )
        c.execute(
            text(
                "INSERT INTO splat_job (map_version_id, status, params, created_at) "
                "VALUES (1, 'failed', '{}', '2026-11-10 00:00:00')"
            )
        )
        c.execute(text("DELETE FROM map_version WHERE id = 1"))
        return c.execute(text("SELECT count(*) FROM splat_job")).scalar_one()


def test_deleting_a_version_deletes_its_splat_job_row_model_schema(tmp_path):
    """Dua jalur menghapus versi (maps_api untuk versi CLI, worker.purge); tanpa ON DELETE CASCADE
    keduanya gagal di PostgreSQL begitu ada baris splat_job."""
    engine = _fk_engine(f"sqlite:///{tmp_path / 'm.db'}")
    try:
        SQLModel.metadata.create_all(engine)
        assert _count_splat_rows_after_deleting_the_version(engine) == 0
    finally:
        engine.dispose()


def test_deleting_a_version_deletes_its_splat_job_row_migration_schema(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("server/alembic.ini"), "head")
    engine = _fk_engine(url)
    try:
        assert _count_splat_rows_after_deleting_the_version(engine) == 0
    finally:
        engine.dispose()
