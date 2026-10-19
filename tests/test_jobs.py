"""Uji antrean pekerjaan bangun peta, dengan SQLite di memori."""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from server import jobs
from server.db import Area, MapJob, publish, register

MAP = {"path": "/data/inbox/v1.mp4", "role": "peta"}
QUERY = {"path": "/data/inbox/v2.mp4", "role": "uji"}


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_create_job_makes_area_and_keeps_videos(session):
    job = jobs.create_job(session, "floor10", "Lantai 10", "a@x.id", [MAP, QUERY], "queued")
    assert session.get(Area, "floor10").name == "Lantai 10"
    assert (job.status, job.created_by, job.videos) == ("queued", "a@x.id", [MAP, QUERY])


@pytest.mark.parametrize(
    "videos",
    [
        [],
        [QUERY],
        [{"path": "/x.mp4", "role": "map"}],
        [MAP, {"path": "/lain/v1.mp4", "role": "uji"}],
    ],
    ids=["kosong", "tanpa-peta", "peran-salah-ketik", "nama-video-kembar"],
)
def test_create_job_rejects_unusable_videos(session, videos):
    with pytest.raises(ValueError):
        jobs.create_job(session, "floor10", "Lantai 10", "a@x.id", videos, "queued")


def test_claim_next_is_fifo_and_skips_non_queued(session):
    jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "uploading")
    first = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "queued")
    second = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "queued")
    got = jobs.claim_next(session)
    assert (got.id, got.status) == (first.id, "running")
    assert got.started_at is not None
    assert jobs.claim_next(session).id == second.id
    assert jobs.claim_next(session) is None


def test_finish_and_fail_record_outcome(session):
    job = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "queued")
    jobs.claim_next(session)
    jobs.set_stage(session, job, "build")
    jobs.fail(session, job, "x" * 10_000)
    assert (job.status, job.stage) == ("failed", "build")
    assert len(job.error) == 4000 and job.finished_at is not None

    ok = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "queued")
    jobs.claim_next(session)
    v = register(session, "floor10", "L10", "/maps/floor10/job-2")
    jobs.finish(session, ok, v.id, {"run": {"map_registered": 80}})
    assert (ok.status, ok.map_version_id, ok.summary["run"]["map_registered"]) == ("done", v.id, 80)


def test_recover_stale_fails_running_jobs(session):
    job = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "queued")
    jobs.claim_next(session)
    assert jobs.recover_stale(session) == 1
    assert session.get(MapJob, job.id).status == "failed"
    assert "worker stopped" in session.get(MapJob, job.id).error


def test_publish_records_who(session):
    v = register(session, "floor10", "L10", "/maps/v1")
    assert publish(session, v.id, by="a@x.id").published_by == "a@x.id"


def test_manage_job_queues_and_lists(tmp_path, monkeypatch, capsys):
    from server import manage

    url = f"sqlite:///{tmp_path / 'm.db'}"
    SQLModel.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    frames = tmp_path / "mapping"
    frames.mkdir()
    monkeypatch.setattr("sys.argv", ["manage", "job", "floor10", "Lantai 10", "--map", str(frames)])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["manage", "job", "floor10", "Lantai 10", "--map", "mapping"])
    manage.main()
    assert "pekerjaan 1 diantrekan" in capsys.readouterr().out
    job = Session(create_engine(url)).get(MapJob, 1)
    assert job.videos[0]["path"] == str(frames.resolve())  # jalur relatif disimpan absolut
    monkeypatch.setattr("sys.argv", ["manage", "jobs"])
    manage.main()
    listing = capsys.readouterr().out
    assert "floor10" in listing and "queued" in listing


def test_manage_job_rejects_missing_path(tmp_path, monkeypatch):
    from server import manage

    url = f"sqlite:///{tmp_path / 'm.db'}"
    SQLModel.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr("sys.argv", ["manage", "job", "floor10", "L10", "--map", "/tidak/ada"])
    with pytest.raises(SystemExit, match="tidak ditemukan"):
        manage.main()


def test_upload_job_may_have_no_path_yet(session):
    videos = [{"name": "a.mp4", "role": "peta", "size": 10, "upload_id": None, "path": None}]
    job = jobs.create_job(session, "floor10", "L10", "a@x.id", videos)
    assert job.status == "uploading"


def test_expire_uploading_fails_only_old_jobs(session):
    from datetime import UTC, datetime, timedelta

    old = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP])
    new = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP])
    old.created_at = datetime.now(UTC) - timedelta(hours=25)
    session.add(old)
    session.commit()
    expired = jobs.expire_uploading(session, timedelta(hours=24))
    assert [j.id for j in expired] == [old.id]
    assert session.get(MapJob, old.id).status == "failed"
    assert session.get(MapJob, new.id).status == "uploading"


def test_is_stalled_rule(session):
    from datetime import UTC, datetime, timedelta

    v = {"name": "a.mp4", "role": "peta", "size": 100, "upload_id": "u1", "uploaded": False}
    job = jobs.create_job(session, "floor10", "L10", "a@x.id", [v])
    now = datetime.now(UTC)

    # 1. Fresh job with no activity_at is not stalled
    assert jobs.is_stalled(job, now=now) is False

    # 2. Activity within 10 minutes is not stalled
    job.videos = [{**v, "activity_at": (now - timedelta(minutes=5)).isoformat()}]
    assert jobs.is_stalled(job, now=now) is False

    # 3. Activity older than 10 minutes is stalled
    job.videos = [{**v, "activity_at": (now - timedelta(minutes=11)).isoformat()}]
    assert jobs.is_stalled(job, now=now) is True

    # 4. Multi-video: newest activity within 10m keeps it not stalled
    v2 = {"name": "b.mp4", "role": "uji", "size": 50, "upload_id": "u2", "uploaded": False}
    job.videos = [
        {**v, "activity_at": (now - timedelta(minutes=15)).isoformat()},
        {**v2, "activity_at": (now - timedelta(minutes=2)).isoformat()},
    ]
    assert jobs.is_stalled(job, now=now) is False

    # 5. Fallback to created_at when no video has activity_at
    job.videos = [v]
    job.created_at = now - timedelta(minutes=12)
    assert jobs.is_stalled(job, now=now) is True
    job.created_at = now - timedelta(minutes=8)
    assert jobs.is_stalled(job, now=now) is False

    # 6. Non-uploading jobs are never stalled
    job.status = "queued"
    job.videos = [{**v, "activity_at": (now - timedelta(hours=2)).isoformat()}]
    assert jobs.is_stalled(job, now=now) is False

    job.status = "uploading"
    # 7. When all videos are uploaded, stalled is False
    job.videos = [{**v, "uploaded": True, "activity_at": (now - timedelta(hours=2)).isoformat()}]
    assert jobs.is_stalled(job, now=now) is False


def test_expire_uploading_idle_and_max_age(session):
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    v = {"name": "a.mp4", "role": "peta", "size": 100, "upload_id": "u1", "uploaded": False}

    # Job 1: Active upload (activity 1 hour ago, created 2 hours ago) -> stays uploading
    j_active = jobs.create_job(
        session,
        "floor10",
        "L10",
        "a@x.id",
        [{**v, "activity_at": (now - timedelta(hours=1)).isoformat()}],
    )
    j_active.created_at = now - timedelta(hours=2)

    # Job 2: Idle upload (activity 7 hours ago, created 8 hours ago) -> fails due to 6h idle
    j_idle = jobs.create_job(
        session,
        "floor10",
        "L10",
        "a@x.id",
        [{**v, "activity_at": (now - timedelta(hours=7)).isoformat()}],
    )
    j_idle.created_at = now - timedelta(hours=8)

    # Job 3: Idle upload without activity_at (created 7 hours ago) -> fails due to 6h idle
    j_no_act = jobs.create_job(session, "floor10", "L10", "a@x.id", [v])
    j_no_act.created_at = now - timedelta(hours=7)

    # Job 4: Active upload sending data, but created 25 hours ago -> fails due to 24h max age
    j_ancient = jobs.create_job(
        session,
        "floor10",
        "L10",
        "a@x.id",
        [{**v, "activity_at": (now - timedelta(minutes=5)).isoformat()}],
    )
    j_ancient.created_at = now - timedelta(hours=25)

    session.add_all([j_active, j_idle, j_no_act, j_ancient])
    session.commit()

    expired = jobs.expire_uploading(session)
    expired_ids = {j.id for j in expired}

    assert j_active.id not in expired_ids
    assert j_idle.id in expired_ids
    assert j_no_act.id in expired_ids
    assert j_ancient.id in expired_ids

    assert session.get(MapJob, j_active.id).status == "uploading"
    assert session.get(MapJob, j_idle.id).status == "failed"
    assert session.get(MapJob, j_idle.id).error == "upload stalled for 6 hours; start a new session"
    assert session.get(MapJob, j_no_act.id).status == "failed"
    assert (
        session.get(MapJob, j_no_act.id).error == "upload stalled for 6 hours; start a new session"
    )
    assert session.get(MapJob, j_ancient.id).status == "failed"
    assert (
        session.get(MapJob, j_ancient.id).error
        == "upload did not finish within 24 hours; start a new session"
    )


def test_delete_block_reason_uploading(session):
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    v = {"name": "a.mp4", "role": "peta", "size": 100, "upload_id": "u1", "uploaded": False}

    # Active upload: delete blocked with exact message
    active_job = jobs.create_job(
        session,
        "floor10",
        "L10",
        "a@x.id",
        [{**v, "activity_at": (now - timedelta(minutes=2)).isoformat()}],
    )
    assert jobs.delete_block_reason(session, active_job) == "upload is still receiving data"

    # Stalled upload: delete allowed (reason is None)
    stalled_job = jobs.create_job(
        session,
        "floor10",
        "L10",
        "a@x.id",
        [{**v, "activity_at": (now - timedelta(minutes=15)).isoformat()}],
    )
    assert jobs.delete_block_reason(session, stalled_job) is None
