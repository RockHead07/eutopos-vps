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


class Room(SQLModel, table=True):
    """Ruangan yang ditaruh staf di dashboard, posisi di kerangka gedung G (spek 2026-10-21 5b)."""

    __table_args__ = (UniqueConstraint("area_id", "name"),)

    id: int | None = Field(default=None, primary_key=True)
    area_id: str = Field(foreign_key="area.id", index=True)
    name: str
    x: float
    y: float
    created_by: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True)
    )


class RouteEdit(SQLModel, table=True):
    """Koreksi graf rute dengan koordinat G, supaya bertahan saat graf dasar dibuat ulang."""

    __tablename__ = "route_edit"

    id: int | None = Field(default=None, primary_key=True)
    area_id: str = Field(foreign_key="area.id", index=True)
    kind: str  # add_edge, remove_edge, move_node
    ax: float
    ay: float
    bx: float
    by: float
    created_by: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True)
    )


class WalkableStroke(SQLModel, table=True):
    """Goresan kuas area walkable (paint atau erase), dalam koordinat G; urut `id`."""

    __tablename__ = "walkable_stroke"

    id: int | None = Field(default=None, primary_key=True)
    area_id: str = Field(foreign_key="area.id", index=True)
    mode: str  # paint atau erase
    radius: float
    points: list = Field(sa_type=JSON)
    created_by: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True)
    )


class LocalizeRequest(SQLModel, table=True):
    """Satu permintaan /localize (roadmap M1-6). Tanpa gambar, tanpa pose, tanpa identitas."""

    __tablename__ = "localize_request"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True), index=True
    )
    result: str  # ok, failed (200), rejected (4xx/503), error (500)
    http_status: int
    reason: str | None = None  # alasan penolakan
    area_id: str | None = None
    map_version: int | None = None
    inliers: int | None = None
    correspondences: int | None = None
    intrinsics_source: str | None = None
    t_s: dict | None = Field(default=None, sa_type=JSON)  # waktu per tahap di Localizer
    wall_s: float | None = None  # seluruh permintaan: decode, antre kunci, lokalisasi
    image_w: int | None = None
    image_h: int | None = None


class PublishedGraph(SQLModel, table=True):
    """navgraph.json terbit per area; /navgraph membacanya lebih dulu daripada berkas di /maps."""

    __tablename__ = "published_graph"

    area_id: str = Field(foreign_key="area.id", primary_key=True)
    graph: dict = Field(sa_type=JSON)
    walkable: dict | None = Field(default=None, sa_type=JSON)  # grid siap pakai + targets
    published_by: str
    published_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True)
    )


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
