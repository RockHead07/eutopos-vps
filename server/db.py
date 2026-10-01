"""Model data peta: area, versi petanya (spesifikasi bagian 4), dan antrean pekerjaan bangun peta.

Setiap area punya versi peta berurutan. Paling banyak satu versi berstatus "published" per area,
dijaga indeks unik parsial di database, sehingga "versi aktif" tidak bisa ganda walau ada dua
proses yang menerbitkan bersamaan.
"""

import os
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import JSON, DateTime, Index, UniqueConstraint, func, text
from sqlmodel import Field, Session, SQLModel, create_engine, select

Status = Literal["candidate", "published", "rejected", "retired"]


class Area(SQLModel, table=True):
    id: str = Field(primary_key=True)  # slug, misalnya "floor10"
    name: str


class MapVersion(SQLModel, table=True):
    __tablename__ = "map_version"
    __table_args__ = (
        UniqueConstraint("area_id", "version"),
        Index(
            "one_published_per_area",
            "area_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
            sqlite_where=text("status = 'published'"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    area_id: str = Field(foreign_key="area.id", index=True)
    version: int  # nomor urut per area, mulai 1
    path: str  # folder --out spike/run.py, dilihat dari dalam container
    status: str = "candidate"
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True)
    )
    published_by: str | None = None  # email dari JWT Access, null untuk versi lewat CLI


class MapJob(SQLModel, table=True):
    """Satu pekerjaan bangun peta (spesifikasi web-upload bagian 5)."""

    __tablename__ = "map_job"

    id: int | None = Field(default=None, primary_key=True)
    area_id: str = Field(foreign_key="area.id", index=True)
    created_by: str
    status: str = "uploading"  # uploading, queued, running, done, failed
    stage: str | None = None  # tahap aktif, atau tahap tempat gagal
    videos: list[dict] = Field(default_factory=list, sa_type=JSON)
    summary: dict | None = Field(default=None, sa_type=JSON)
    error: str | None = None
    map_version_id: int | None = Field(default=None, foreign_key="map_version.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True)
    )
    started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    finished_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


def engine_from_env():
    return create_engine(os.environ["DATABASE_URL"])


def active_version(session: Session, area_id: str) -> MapVersion | None:
    stmt = select(MapVersion).where(MapVersion.area_id == area_id, MapVersion.status == "published")
    return session.exec(stmt).first()


def register(session: Session, area_id: str, name: str, path: str) -> MapVersion:
    """Tambah versi kandidat baru untuk area (area dibuat kalau belum ada)."""
    if session.get(Area, area_id) is None:
        session.add(Area(id=area_id, name=name))
    last = session.exec(
        select(func.max(MapVersion.version)).where(MapVersion.area_id == area_id)
    ).one()
    v = MapVersion(area_id=area_id, version=(last or 0) + 1, path=path)
    session.add(v)
    session.commit()
    session.refresh(v)
    return v


def publish(session: Session, version_id: int, by: str | None = None) -> MapVersion:
    """Jadikan versi ini aktif. Versi aktif sebelumnya menjadi "retired", dalam satu transaksi."""
    v = session.get(MapVersion, version_id)
    if v is None:
        raise LookupError(f"versi {version_id} tidak ada")
    current = active_version(session, v.area_id)
    if current is not None and current.id != v.id:
        current.status = "retired"
        session.add(current)
        session.flush()  # lepas status lama dulu supaya indeks unik tidak bentrok
    v.status = "published"
    v.published_by = by
    session.add(v)
    session.commit()
    session.refresh(v)
    return v
