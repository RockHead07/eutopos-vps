"""Kunci sesi PostgreSQL untuk pemakaian GPU bersama."""

import sys
from contextlib import contextmanager

from sqlalchemy import text

# Kunci yang SAMA dipakai worker dan splat-worker.
GPU_LOCK_KEY: int = 0x6575746F706F73


@contextmanager
def gpu_lock(engine):
    if engine.dialect.name != "postgresql":
        yield
        return
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": GPU_LOCK_KEY})
        try:
            yield
        finally:
            try:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": GPU_LOCK_KEY})
            except Exception as exc:
                print(
                    "warning: GPU advisory unlock failed:",
                    " ".join(str(exc).splitlines()),
                    file=sys.stderr,
                )
    finally:
        try:
            conn.invalidate()
        finally:
            conn.close()
