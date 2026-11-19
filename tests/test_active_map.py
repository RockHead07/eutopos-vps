"""Uji pemuatan ulang peta aktif dengan pemuat palsu (tanpa model, tanpa GPU)."""

import json
import threading
from types import SimpleNamespace

import pytest
from sqlmodel import Session, SQLModel, create_engine

from server import active_map
from server.db import Alignment, Area, MapVersion, active_version, publish, register
from server.pipeline import run_dir
from tests.test_alignment import GOOD_ALIGN


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EUTOPOS_AREA", "floor10")
    e = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    SQLModel.metadata.create_all(e)
    with Session(e) as s:
        from tests.conftest import make_building

        bld = make_building(s)
        s.add(Area(id="floor10", name="L10", building_id=bld.id))
        s.commit()
    return e


def state():
    return SimpleNamespace(
        localizer="lama",
        area_id="floor10",
        map_version=1,
        lock=threading.Lock(),
        reloading=False,
        reload_error=None,
    )


def versions(engine):
    with Session(engine) as s:
        v1 = register(s, "floor10", "L10", "/maps/floor10/job-1")
        v2 = register(s, "floor10", "L10", "/maps/floor10/job-2")
        publish(s, v1.id, by="alice")  # peta yang sedang dilayani
        return v1.id, v2.id


def broken(path, **kw):
    raise RuntimeError("berkas peta rusak")


def test_reload_swaps_localizer_then_publishes(engine, monkeypatch):
    _, v2 = versions(engine)
    monkeypatch.setattr(active_map, "load_localizer", lambda path, **kw: f"baru:{path.name}")
    st = state()
    st.reload_error = "galat lama"
    active_map.reload_in_background(st, engine, v2, "bob").join(5)
    assert (st.localizer, st.map_version, st.reloading, st.reload_error) == (
        "baru:job-2",
        2,
        False,
        None,
    )
    with Session(engine) as s:
        assert (active_version(s, "floor10").id, s.get(MapVersion, v2).published_by) == (v2, "bob")


def test_failed_load_keeps_old_map_and_database(engine, monkeypatch):
    # Spesifikasi bagian 7: peta lama tetap dipakai, versi kembali ke status sebelumnya.
    v1, v2 = versions(engine)
    monkeypatch.setattr(active_map, "load_localizer", broken)
    st = state()
    active_map.reload_in_background(st, engine, v2, "bob").join(5)
    assert (st.localizer, st.map_version, st.reloading) == ("lama", 1, False)
    assert "version 2" in st.reload_error
    with Session(engine) as s:
        assert (active_version(s, "floor10").id, active_version(s, "floor10").published_by) == (
            v1,
            "alice",
        )
        assert s.get(MapVersion, v2).status == "candidate"


def test_failed_republish_of_active_version_keeps_it_published(engine, monkeypatch):
    v1, _ = versions(engine)
    monkeypatch.setattr(active_map, "load_localizer", broken)
    active_map.reload_in_background(state(), engine, v1, "bob").join(5)
    with Session(engine) as s:
        assert active_version(s, "floor10").id == v1


def test_database_error_does_not_leave_reloading_stuck(engine, monkeypatch):
    _, v2 = versions(engine)
    monkeypatch.setattr(active_map, "load_localizer", lambda path, **kw: "baru")

    def db_down(*args, **kwargs):
        raise ConnectionError("database mati")

    monkeypatch.setattr(active_map, "publish", db_down)
    st = state()
    active_map.reload_in_background(st, engine, v2, "bob").join(5)
    assert (st.localizer, st.reloading) == ("lama", False)
    assert "database mati" in st.reload_error


def mark_ready(engine, version_id):
    with Session(engine) as s:
        v = s.get(MapVersion, version_id)
        v.status = "ready"
        s.add(v)
        s.commit()


def add_alignment(engine, version_id):
    with Session(engine) as s:
        s.add(
            Alignment(
                map_version_id=version_id,
                params=GOOD_ALIGN,
                stats={},
                status="applied",
                source="fit",
                created_by="alice",
            )
        )
        s.commit()


def test_publish_ready_skips_serving_area_without_alignment(engine, monkeypatch):
    v1, v2 = versions(engine)
    with Session(engine) as s:
        newest_id = register(s, "floor10", "L10", "/maps/floor10/job-3").id
    mark_ready(engine, v2)
    add_alignment(engine, v2)
    mark_ready(engine, newest_id)
    monkeypatch.setattr(active_map, "load_localizer", lambda path, **kw: path.name)
    st = state()

    threads = active_map.publish_ready(st, engine)
    for thread in threads:
        thread.join(5)
    assert threads == []
    assert (st.localizer, st.map_version, st.reloading) == ("lama", 1, False)
    with Session(engine) as s:
        assert active_version(s, "floor10").id == v1
        assert s.get(MapVersion, newest_id).status == "ready"
        assert s.get(MapVersion, v2).status == "retired"


@pytest.mark.parametrize("source", ["database", "file"])
def test_publish_ready_publishes_serving_area_once_aligned(engine, monkeypatch, tmp_path, source):
    _, v2 = versions(engine)
    maps_root = tmp_path / "maps"
    map_path = maps_root / "floor10" / "job-2"
    monkeypatch.setenv("EUTOPOS_MAPS_ROOT", str(maps_root))
    with Session(engine) as s:
        version = s.get(MapVersion, v2)
        version.path = str(map_path)
        s.add(version)
        s.commit()
    mark_ready(engine, v2)
    monkeypatch.setattr(active_map, "load_localizer", lambda path, **kw: path.name)
    st = state()

    threads = active_map.publish_ready(st, engine)
    for thread in threads:
        thread.join(5)
    assert threads == []
    with Session(engine) as s:
        assert s.get(MapVersion, v2).status == "ready"
    if source == "database":
        add_alignment(engine, v2)
    else:
        directory = run_dir(map_path)
        directory.mkdir(parents=True)
        (directory / "align.json").write_text(json.dumps(GOOD_ALIGN), encoding="utf-8")

    (thread,) = active_map.publish_ready(st, engine)
    thread.join(5)
    assert not thread.is_alive()
    assert (st.localizer, st.map_version) == ("job-2", 2)
    with Session(engine) as s:
        assert active_version(s, "floor10").id == v2
        assert s.get(MapVersion, v2).published_by == "system"


def test_publish_ready_other_area_does_not_need_alignment(engine, monkeypatch):
    _, serving_id = versions(engine)
    with Session(engine) as s:
        other_id = register(s, "lain", "Lain", "/maps/other", s.get(Area, "floor10").building_id).id
    mark_ready(engine, serving_id)
    mark_ready(engine, other_id)
    monkeypatch.setattr(active_map, "load_localizer", lambda path, **kw: path.name)
    st = state()

    threads = active_map.publish_ready(st, engine)
    for thread in threads:
        thread.join(5)
    with Session(engine) as s:
        other = active_version(s, "lain")
        assert (other.id, other.published_by) == (other_id, "system")
        assert s.get(MapVersion, serving_id).status == "ready"
    assert threads == []
    assert (st.localizer, st.map_version) == ("lama", 1)


def test_publish_ready_swaps_serving_area(engine, monkeypatch):
    _, v2 = versions(engine)
    mark_ready(engine, v2)
    add_alignment(engine, v2)
    monkeypatch.setattr(active_map, "load_localizer", lambda path, **kw: f"baru:{path.name}")
    st = state()
    (thread,) = active_map.publish_ready(st, engine)
    thread.join(5)
    assert not thread.is_alive()
    assert (st.localizer, st.map_version) == ("baru:job-2", 2)
    with Session(engine) as s:
        assert active_version(s, "floor10").id == v2
        assert s.get(MapVersion, v2).published_by == "system"


def test_publish_ready_publishes_other_area_directly(engine, monkeypatch):
    monkeypatch.setenv("EUTOPOS_AREA", "floor10")
    with Session(engine) as s:
        other = register(s, "lain", "Lain", "/maps/other", s.get(Area, "floor10").building_id)
        version_id = other.id
    mark_ready(engine, version_id)
    st = state()
    assert active_map.publish_ready(st, engine) == []
    assert st.localizer == "lama"
    with Session(engine) as s:
        assert (active_version(s, "lain").id, s.get(MapVersion, version_id).published_by) == (
            version_id,
            "system",
        )


@pytest.mark.parametrize("with_job", [False, True])
def test_failed_load_rejects_version_and_stops_retrying(engine, monkeypatch, with_job):
    from server import jobs
    from server.db import MapJob

    v1, v2 = versions(engine)
    mark_ready(engine, v2)
    add_alignment(engine, v2)
    if with_job:
        with Session(engine) as s:
            job = jobs.create_job(
                s, "floor10", "L10", "cli", [{"path": "/x.mp4", "role": "peta"}], "queued"
            )
            jobs.claim_next(s)
            jobs.finish(s, job, v2, {"gate": {"decision": "publish"}})
            job_id = job.id
    monkeypatch.setattr(active_map, "load_localizer", broken)
    st = state()
    (thread,) = active_map.publish_ready(st, engine)
    thread.join(5)
    assert not thread.is_alive()
    assert (st.localizer, st.map_version) == ("lama", 1)
    with Session(engine) as s:
        assert active_version(s, "floor10").id == v1
        assert s.get(MapVersion, v2).status == "rejected"
        if with_job:
            job = s.get(MapJob, job_id)
            assert (job.status, job.stage, job.map_version_id) == ("failed", "publish", v2)
            assert "Map could not be loaded: berkas peta rusak" == job.error
            assert job.summary == {"gate": {"decision": "publish"}}
    assert active_map.publish_ready(st, engine) == []


def test_newest_ready_wins_and_older_is_retired(engine, monkeypatch):
    _, v2 = versions(engine)
    with Session(engine) as s:
        v3 = register(s, "floor10", "L10", "/maps/floor10/job-3").id
    mark_ready(engine, v2)
    mark_ready(engine, v3)
    add_alignment(engine, v3)
    monkeypatch.setattr(active_map, "load_localizer", lambda path, **kw: path.name)
    st = state()
    (thread,) = active_map.publish_ready(st, engine)
    thread.join(5)
    assert not thread.is_alive()
    assert st.localizer == "job-3"
    with Session(engine) as s:
        assert active_version(s, "floor10").id == v3
        assert s.get(MapVersion, v2).status == "retired"


def test_publish_ready_waits_while_reloading(engine):
    _, v2 = versions(engine)
    mark_ready(engine, v2)
    add_alignment(engine, v2)
    st = state()
    st.reloading = True
    assert active_map.publish_ready(st, engine) == []
    with Session(engine) as s:
        assert s.get(MapVersion, v2).status == "ready"


def test_publish_loop_keeps_going_after_error(engine, monkeypatch):
    st = state()
    stop = threading.Event()
    calls = []

    def tick(state, engine):
        calls.append(state)
        if len(calls) == 1:
            raise RuntimeError("first tick failed")
        stop.set()

    monkeypatch.setattr(active_map, "publish_ready", tick, raising=False)
    active_map.publish_loop(st, engine, stop, interval=0.01)
    assert calls == [st, st]


@pytest.mark.parametrize(
    "value, enabled",
    [
        (None, False),
        ("", False),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("bogus", False),
        ("1", True),
        ("true", True),
        ("yes", True),
        (" ON ", True),
    ],
)
def test_auto_publish_enabled_parses_flag(monkeypatch, value, enabled):
    if value is None:
        monkeypatch.delenv("EUTOPOS_AUTO_PUBLISH", raising=False)
    else:
        monkeypatch.setenv("EUTOPOS_AUTO_PUBLISH", value)
    assert active_map.auto_publish_enabled() is enabled


@pytest.mark.parametrize("enabled", [False, True])
def test_publish_loop_not_started_without_flag(engine, monkeypatch, enabled):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from server import app as app_module

    _, v2 = versions(engine)
    mark_ready(engine, v2)
    monkeypatch.setenv("DATABASE_URL", str(engine.url))
    monkeypatch.setenv("EUTOPOS_AREA", "floor10")
    monkeypatch.delenv("EUTOPOS_AUTO_PUBLISH", raising=False)
    if enabled:
        monkeypatch.setenv("EUTOPOS_AUTO_PUBLISH", "yes")
    monkeypatch.setattr(app_module, "engine_from_env", lambda: engine)
    monkeypatch.setattr(active_map, "load_localizer", lambda path, **kw: path.name)
    started, stopped = threading.Event(), threading.Event()

    def loop(state, engine, stop):
        started.set()
        if stop.wait(5):
            stopped.set()

    monkeypatch.setattr(active_map, "publish_loop", loop)
    with TestClient(FastAPI(lifespan=app_module.lifespan)):
        if enabled:
            assert started.wait(2)
        else:
            assert not started.wait(0.1)
            with Session(engine) as s:
                assert s.get(MapVersion, v2).status == "ready"
    if enabled:
        assert stopped.wait(2)
