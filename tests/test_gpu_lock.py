"""Kunci GPU sesi PostgreSQL, diuji tanpa koneksi PostgreSQL sungguhan."""

import importlib
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine


@pytest.fixture
def lock_module():
    return importlib.import_module("server.gpu_lock")


class FakeConn:
    def __init__(self, events, fail_sql=None, error=None):
        self.events = events
        self.fail_sql = fail_sql
        self.error = error

    def execution_options(self, **kwargs):
        self.events.append(("execution_options", kwargs))
        return self

    def execute(self, stmt, params):
        sql = str(stmt)
        self.events.append((sql, params))
        if sql == self.fail_sql:
            raise self.error

    def invalidate(self):
        self.events.append("invalidate")

    def close(self):
        self.events.append("close")


class FakeEngine:
    def __init__(self, dialect_name="postgresql", fail_sql=None, error=None):
        self.dialect = SimpleNamespace(name=dialect_name)
        self.events = []
        self.connections = 0
        self.conn = FakeConn(self.events, fail_sql, error)

    def connect(self):
        self.connections += 1
        if self.dialect.name != "postgresql":
            raise AssertionError("non-PostgreSQL must not connect")
        return self.conn


def test_gpu_lock_is_a_noop_on_sqlite(lock_module):
    engine = create_engine("sqlite://")
    try:
        with lock_module.gpu_lock(engine):
            pass
    finally:
        engine.dispose()


def test_gpu_lock_does_not_connect_on_non_postgres(lock_module):
    engine = FakeEngine("sqlite")
    with lock_module.gpu_lock(engine):
        engine.events.append("body")
    assert engine.connections == 0
    assert engine.events == ["body"]


def test_gpu_lock_events_on_postgres_in_order(lock_module):
    engine = FakeEngine()
    with lock_module.gpu_lock(engine):
        engine.events.append("body")
    assert engine.connections == 1
    assert engine.events == [
        ("execution_options", {"isolation_level": "AUTOCOMMIT"}),
        ("SELECT pg_advisory_lock(:k)", {"k": lock_module.GPU_LOCK_KEY}),
        "body",
        ("SELECT pg_advisory_unlock(:k)", {"k": lock_module.GPU_LOCK_KEY}),
        "invalidate",
        "close",
    ]


def test_gpu_lock_uses_the_same_key_for_lock_and_unlock(lock_module):
    engine = FakeEngine()
    with lock_module.gpu_lock(engine):
        pass
    statements = [
        event
        for event in engine.events
        if isinstance(event, tuple) and event[0].startswith("SELECT")
    ]
    assert [sql for sql, _ in statements] == [
        "SELECT pg_advisory_lock(:k)",
        "SELECT pg_advisory_unlock(:k)",
    ]
    assert [params for _, params in statements] == [{"k": lock_module.GPU_LOCK_KEY}] * 2


def test_gpu_lock_key_fits_a_signed_bigint(lock_module):
    key = lock_module.GPU_LOCK_KEY
    assert isinstance(key, int) and not isinstance(key, bool)
    assert -(2**63) <= key < 2**63


def test_gpu_lock_unlocks_when_the_body_raises(lock_module):
    engine = FakeEngine()
    error = ValueError("body failure")
    with pytest.raises(ValueError, match="body failure") as caught:
        with lock_module.gpu_lock(engine):
            engine.events.append("body")
            raise error
    assert caught.value is error
    assert engine.events == [
        ("execution_options", {"isolation_level": "AUTOCOMMIT"}),
        ("SELECT pg_advisory_lock(:k)", {"k": lock_module.GPU_LOCK_KEY}),
        "body",
        ("SELECT pg_advisory_unlock(:k)", {"k": lock_module.GPU_LOCK_KEY}),
        "invalidate",
        "close",
    ]


def test_gpu_lock_failed_acquire_closes_without_unlock(lock_module):
    error = RuntimeError("acquire failed")
    engine = FakeEngine(fail_sql="SELECT pg_advisory_lock(:k)", error=error)
    with pytest.raises(RuntimeError, match="acquire failed") as caught:
        with lock_module.gpu_lock(engine):
            pytest.fail("body must not run when acquire fails")
    assert caught.value is error
    assert engine.events == [
        ("execution_options", {"isolation_level": "AUTOCOMMIT"}),
        ("SELECT pg_advisory_lock(:k)", {"k": lock_module.GPU_LOCK_KEY}),
        "invalidate",
        "close",
    ]


@pytest.mark.parametrize("body_raises", [False, True])
def test_gpu_lock_failed_unlock_does_not_mask_or_raise_and_still_invalidates(
    lock_module, capsys, body_raises
):
    engine = FakeEngine(
        fail_sql="SELECT pg_advisory_unlock(:k)",
        error=RuntimeError("unlock failed\nDB lost"),
    )
    error = ValueError("body failure")

    def body():
        with lock_module.gpu_lock(engine):
            engine.events.append("body")
            if body_raises:
                raise error

    if body_raises:
        with pytest.raises(ValueError, match="body failure") as caught:
            body()
        assert caught.value is error
    else:
        body()
    assert engine.events == [
        ("execution_options", {"isolation_level": "AUTOCOMMIT"}),
        ("SELECT pg_advisory_lock(:k)", {"k": lock_module.GPU_LOCK_KEY}),
        "body",
        ("SELECT pg_advisory_unlock(:k)", {"k": lock_module.GPU_LOCK_KEY}),
        "invalidate",
        "close",
    ]
    warning = capsys.readouterr().err
    assert len(warning.splitlines()) == 1
    assert "unlock failed" in warning
