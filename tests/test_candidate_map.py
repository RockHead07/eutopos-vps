import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlmodel import Session, SQLModel, create_engine

from server.candidate_map import CandidateCache, CandidateUnavailable
from server.db import Area, MapJob, MapVersion


@pytest.fixture
def candidate_db(tmp_path):
    from tests.conftest import make_building

    engine = create_engine(f"sqlite:///{tmp_path / 'candidate.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        building = make_building(session)
        session.add(Area(id="floor10", name="L10", building_id=building.id))
        session.commit()
        for version, status in [(1, "candidate"), (2, "ready"), (3, "rejected"), (4, "retired")]:
            path = tmp_path / f"v{version}"
            if version != 4:
                path.mkdir()
            session.add(
                MapVersion(
                    id=version, area_id="floor10", version=version, path=str(path), status=status
                )
            )
        session.commit()
    yield engine
    engine.dispose()


def test_loads_once_and_reuses(candidate_db):
    calls = []

    def loader(path, *, align_source):
        calls.append(path)
        assert align_source() is None
        return object()

    cache = CandidateCache(candidate_db, loader=loader)
    first, area, version = cache.get(1)
    assert cache.get(1) == (first, area, version)
    assert (area, version) == ("floor10", 1)
    assert len(calls) == 1


def test_other_version_replaces_previous(candidate_db):
    calls = []

    def loader(path, *, align_source):
        calls.append(path.name)
        return object()

    cache = CandidateCache(candidate_db, loader=loader)
    assert cache.get(1)[2] == 1
    assert cache.get(2)[2] == 2
    assert cache.get(1)[2] == 1
    assert calls == ["v1", "v2", "v1"]


def test_sweep_drops_idle_candidate(candidate_db):
    now = 0
    cache = CandidateCache(
        candidate_db, loader=lambda *a, **k: object(), idle_s=10, clock=lambda: now
    )
    first, _, _ = cache.get(1)
    now = 10
    assert cache.sweep() is False
    now = 11
    assert cache.sweep() is True
    assert cache.get(1)[0] is not first


@pytest.mark.parametrize(("version_id", "status"), [(999, 404), (3, 409), (4, 409)])
def test_unavailable_versions(candidate_db, version_id, status):
    cache = CandidateCache(candidate_db, loader=lambda *a, **k: pytest.fail("unexpected load"))
    with pytest.raises(CandidateUnavailable) as error:
        cache.get(version_id)
    assert error.value.status == status


def test_candidate_during_incomplete_job_unavailable(candidate_db, tmp_path):
    path = tmp_path / "job-21"
    path.mkdir()
    with Session(candidate_db) as session:
        session.add(MapJob(id=21, area_id="floor10", created_by="dev@local", status="running"))
        session.add(
            MapVersion(id=5, area_id="floor10", version=5, path=str(path), status="candidate")
        )
        session.commit()
    cache = CandidateCache(candidate_db, loader=lambda *a, **k: pytest.fail("unexpected load"))
    with pytest.raises(CandidateUnavailable) as error:
        cache.get(5)
    assert error.value.status == 409


def test_concurrent_gets_do_not_load_two_versions(candidate_db):
    lock = threading.Lock()
    barrier = threading.Barrier(2, timeout=5)
    active = max_concurrent = 0

    def loader(path, *, align_source):
        nonlocal active, max_concurrent
        with lock:
            active += 1
            max_concurrent = max(max_concurrent, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return path.name

    cache = CandidateCache(candidate_db, loader=loader)

    def request(version_id):
        barrier.wait()
        return cache.get(version_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(request, [1, 2])) == [("v1", "floor10", 1), ("v2", "floor10", 2)]
    assert max_concurrent == 1
