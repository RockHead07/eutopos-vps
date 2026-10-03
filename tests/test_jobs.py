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
