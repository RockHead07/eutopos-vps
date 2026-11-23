"""Muat satu versi kandidat untuk uji lapangan tanpa menukar peta aktif."""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session, select

from server import active_map
from server.alignment import DbAlign
from server.db import MapJob, MapVersion
from server.localizer import Localizer

CANDIDATE_IDLE_S = 600
SWEEP_S = 60
TESTABLE = {"candidate", "ready", "published", "retired"}


class CandidateUnavailable(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def testable_version(session: Session, version_id: int) -> MapVersion:
    version = session.get(MapVersion, version_id)
    if version is None:
        raise CandidateUnavailable(404, "map version not found")
    if version.status not in TESTABLE:
        raise CandidateUnavailable(409, "map version is not testable")
    path = Path(version.path)
    if not path.is_dir():
        raise CandidateUnavailable(409, "map folder is missing")
    job = session.exec(select(MapJob).where(MapJob.map_version_id == version_id)).first()
    # Pekerja mendaftarkan versi di folder job-<id> sebelum jobs.finish mengaitkan id versi.
    stem = path.name.removeprefix("job-")
    if job is None and stem != path.name and stem.isascii() and stem.isdecimal() and len(stem) < 19:
        job = session.get(MapJob, int(stem))
    if job is not None and job.area_id == version.area_id and job.status != "done":
        raise CandidateUnavailable(409, "map job has not finished")
    return version


class CandidateCache:
    def __init__(
        self,
        engine,
        loader=active_map.load_localizer,
        idle_s=CANDIDATE_IDLE_S,
        clock=time.monotonic,
    ):
        self.engine = engine
        self.loader = loader
        self.idle_s = idle_s
        self.clock = clock
        self._lock = threading.Lock()
        self._entry: tuple[int, Localizer] | None = None
        self._last_used = 0.0

    def get(self, version_id: int) -> tuple[Localizer, str, int]:
        with self.use(version_id) as candidate:
            return candidate

    @contextmanager
    def use(self, version_id: int) -> Iterator[tuple[Localizer, str, int]]:
        """Tahan kandidat di cache sampai pemanggil selesai menggunakannya."""
        with self._lock:
            with Session(self.engine) as session:
                version = testable_version(session, version_id)
                path, area_id, number = Path(version.path), version.area_id, version.version
            if self._entry is None or self._entry[0] != version_id:
                self._entry = None
                try:
                    loc = self.loader(path, align_source=DbAlign(self.engine, version_id).get)
                except FileNotFoundError as e:
                    raise CandidateUnavailable(409, "map files are missing") from e
                self._entry = (version_id, loc)
            try:
                yield self._entry[1], area_id, number
            finally:
                self._last_used = self.clock()

    def sweep(self) -> bool:
        with self._lock:
            if self._entry is None or self.clock() - self._last_used <= self.idle_s:
                return False
            self._entry = None
            return True
