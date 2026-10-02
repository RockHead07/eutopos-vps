"""Uji pemuatan ulang peta aktif dengan pemuat palsu (tanpa model, tanpa GPU)."""

import threading
from types import SimpleNamespace

import pytest
from sqlmodel import Session, SQLModel, create_engine

from server import active_map
from server.db import MapVersion, active_version, publish, register


@pytest.fixture
def engine(tmp_path):
    e = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    SQLModel.metadata.create_all(e)
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


def broken(path):
    raise RuntimeError("berkas peta rusak")


def test_reload_swaps_localizer_then_publishes(engine, monkeypatch):
    _, v2 = versions(engine)
    monkeypatch.setattr(active_map, "load_localizer", lambda path: f"baru:{path.name}")
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
    assert "versi 2" in st.reload_error
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
    monkeypatch.setattr(active_map, "load_localizer", lambda path: "baru")

    def db_down(*args, **kwargs):
        raise ConnectionError("database mati")

    monkeypatch.setattr(active_map, "publish", db_down)
    st = state()
    active_map.reload_in_background(st, engine, v2, "bob").join(5)
    assert (st.localizer, st.reloading) == ("lama", False)
    assert "database mati" in st.reload_error
