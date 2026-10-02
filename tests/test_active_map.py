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
        publish(s, v1.id)
        publish(s, v2.id)  # yang diterbitkan pengguna
        return v1.id, v2.id


def test_reload_swaps_localizer(engine, monkeypatch):
    v1, v2 = versions(engine)
    monkeypatch.setattr(active_map, "load_localizer", lambda path: f"baru:{path.name}")
    st = state()
    active_map.reload_in_background(st, engine, v2, v1).join(5)
    assert (st.localizer, st.map_version, st.reloading, st.reload_error) == (
        "baru:job-2",
        2,
        False,
        None,
    )


def test_failed_load_keeps_old_map_and_restores_version(engine, monkeypatch):
    v1, v2 = versions(engine)

    def broken(path):
        raise RuntimeError("berkas peta rusak")

    monkeypatch.setattr(active_map, "load_localizer", broken)
    st = state()
    active_map.reload_in_background(st, engine, v2, v1).join(5)
    assert (st.localizer, st.map_version, st.reloading) == ("lama", 1, False)
    assert "versi 2" in st.reload_error
    with Session(engine) as s:
        assert active_version(s, "floor10").id == v1
        assert s.get(MapVersion, v2).status == "rejected"
