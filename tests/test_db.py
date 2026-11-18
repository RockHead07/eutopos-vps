"""Uji model versi peta dan migrasinya, dengan SQLite di memori (tanpa PostgreSQL).

Indeks unik parsial "satu versi terbit per area" didukung SQLite juga, jadi aturannya ikut teruji.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from server.db import Area, MapVersion, active_version, publish, register


@pytest.fixture
def session():
    from tests.conftest import make_building

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        bld = make_building(s)
        s.add(Area(id="floor10", name="Lantai 10", building_id=bld.id))
        s.add(Area(id="floor9", name="Lantai 9", building_id=bld.id))
        s.commit()
        yield s


def test_register_numbers_versions_per_area(session):
    a1 = register(session, "floor10", "Lantai 10", "/maps/floor10/v1")
    a2 = register(session, "floor10", "Lantai 10", "/maps/floor10/v2")
    b1 = register(session, "floor9", "Lantai 9", "/maps/floor9/v1")
    assert (a1.version, a2.version, b1.version) == (1, 2, 1)
    assert a1.status == "candidate"
    assert active_version(session, "floor10") is None


def test_publish_retires_previous(session):
    v1 = register(session, "floor10", "Lantai 10", "/maps/v1")
    v2 = register(session, "floor10", "Lantai 10", "/maps/v2")
    publish(session, v1.id)
    publish(session, v2.id)
    assert active_version(session, "floor10").id == v2.id
    assert session.get(MapVersion, v1.id).status == "retired"


def test_database_rejects_two_published_versions(session):
    v1 = register(session, "floor10", "Lantai 10", "/maps/v1")
    v2 = register(session, "floor10", "Lantai 10", "/maps/v2")
    publish(session, v1.id)
    v2.status = "published"  # melewati publish(): database sendiri yang harus menolak
    session.add(v2)
    with pytest.raises(IntegrityError):
        session.commit()


def test_publish_unknown_version(session):
    with pytest.raises(LookupError):
        publish(session, 999)


def test_migration_matches_models(tmp_path, monkeypatch):
    """Migrasi Alembic membuat skema yang sama dengan model (tidak ada yang terlewat)."""
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext

    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("server/alembic.ini"), "head")
    with create_engine(url).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), SQLModel.metadata)
    assert diff == [], diff


def test_service_starts_without_active_map(tmp_path, monkeypatch):
    """Database baru tanpa versi terbit: layanan tetap menyala, /localize menjawab 503."""
    import io

    from fastapi.testclient import TestClient
    from PIL import Image

    url = f"sqlite:///{tmp_path / 's.db'}"
    SQLModel.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_AREA", "floor10")
    from server.app import app

    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "PNG")
    with TestClient(app) as client:
        health = client.get("/health").json()
        assert health["status"] == "no_map" and health["map_images"] == 0
        r = client.post("/localize", files={"image": ("q.png", buf.getvalue(), "image/png")})
        assert r.status_code == 503


def test_service_starts_when_active_map_fails_to_load(tmp_path, monkeypatch):
    """Peta aktif rusak (atau GPU penuh saat menyala): api tetap menyala supaya dashboard bisa
    dipakai menerbitkan versi lain, bukan restart berulang."""
    from fastapi.testclient import TestClient

    from tests.conftest import make_building

    url = f"sqlite:///{tmp_path / 's.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        bld = make_building(s)
        s.add(Area(id="floor10", name="L10", building_id=bld.id))
        s.commit()
        publish(s, register(s, "floor10", "L10", str(tmp_path / "tidak-ada")).id)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_AREA", "floor10")
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    from server.app import app

    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "no_map"
        assert "version 1" in client.get("/api/service").json()["reload_error"]


def test_migration_cli_runs_like_the_container(tmp_path):
    """Container menjalankan perintah alembic (bukan pytest), jadi paket server harus bisa diimpor
    tanpa bantuan pythonpath pytest. Uji ini sempat hilang dan container gagal menyala."""
    import os
    import shutil
    import subprocess
    from pathlib import Path

    alembic = shutil.which("alembic")
    assert alembic, "perintah alembic tidak ditemukan"
    ini = Path(__file__).resolve().parents[1] / "server" / "alembic.ini"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'cli.db'}"
    r = subprocess.run(
        [alembic, "-c", str(ini), "upgrade", "head"], cwd=tmp_path, env=env, capture_output=True
    )
    assert r.returncode == 0, r.stderr.decode(errors="replace")


def test_missing_map_files(tmp_path):
    from server.map_layout import missing_files, required_files

    assert len(missing_files(tmp_path, 1024, 1024, 512)) == 4  # folder kosong
    for p in required_files(tmp_path, 1024, 1024, 512):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    assert missing_files(tmp_path, 1024, 1024, 512) == []
    assert missing_files(tmp_path, 512, 640, 512)  # setelan lain butuh folder lain


def test_migration_0008_puts_existing_areas_in_hcm(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    url = f"sqlite:///{tmp_path / 'mig0008.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config("server/alembic.ini")
    command.upgrade(cfg, "0007")

    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO area (id, name) VALUES ('floor10', 'Floor 10'),"
                " ('hcm-lantai-10', 'HCM Floor 10')"
            )
        )
        conn.commit()

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        orgs = conn.execute(text("SELECT id, slug, name FROM organization")).fetchall()
        assert len(orgs) == 1
        org = orgs[0]
        assert org[1] == "default"

        buildings = conn.execute(text("SELECT id, org_id, slug, name FROM building")).fetchall()
        assert len(buildings) == 1
        bld = buildings[0]
        assert bld[1] == org[0]
        assert bld[2] == "hcm"

        areas = conn.execute(text("SELECT id, building_id FROM area ORDER BY id")).fetchall()
        assert len(areas) == 2
        assert areas[0] == ("floor10", bld[0])
        assert areas[1] == ("hcm-lantai-10", bld[0])


def test_migration_0008_up_down_up(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    url = f"sqlite:///{tmp_path / 'updown.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config("server/alembic.ini")

    command.upgrade(cfg, "head")
    engine = create_engine(url)
    insp = inspect(engine)
    assert "organization" in insp.get_table_names()
    assert "building" in insp.get_table_names()
    col_names = [c["name"] for c in insp.get_columns("area")]
    assert "building_id" in col_names

    command.downgrade(cfg, "0007")
    insp = inspect(create_engine(url))
    assert "organization" not in insp.get_table_names()
    assert "building" not in insp.get_table_names()
    col_names = [c["name"] for c in insp.get_columns("area")]
    assert "building_id" not in col_names

    command.upgrade(cfg, "head")
    insp = inspect(create_engine(url))
    assert "organization" in insp.get_table_names()
    assert "building" in insp.get_table_names()
    col_names = [c["name"] for c in insp.get_columns("area")]
    assert "building_id" in col_names


def test_area_without_building_is_rejected(session):
    from server.db import Area

    session.add(Area(id="x", name="X"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_building_slug_unique_per_org(session):
    from server.db import Building, Organization

    org1 = Organization(slug="org1", name="Org 1")
    org2 = Organization(slug="org2", name="Org 2")
    session.add(org1)
    session.add(org2)
    session.commit()

    b1 = Building(org_id=org1.id, slug="hcm", name="HCM 1")
    session.add(b1)
    session.commit()

    b2 = Building(org_id=org1.id, slug="hcm", name="HCM Duplicate")
    session.add(b2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    b3 = Building(org_id=org2.id, slug="hcm", name="HCM in Org 2")
    session.add(b3)
    session.commit()
    assert b3.id is not None


def test_ensure_area_returns_existing(session):
    from server.db import ensure_area
    from tests.conftest import make_building

    bld = make_building(session)
    a1 = ensure_area(session, "test-existing", "L10", bld.id)
    assert a1.id == "test-existing"
    assert a1.name == "L10"
    assert a1.building_id == bld.id

    a2 = ensure_area(session, "test-existing", "Renamed", None)
    assert a2.id == "test-existing"
    assert a2.name == "L10"

    a3 = ensure_area(session, "test-existing", "Renamed Again", bld.id)
    assert a3.id == "test-existing"
    assert a3.name == "L10"


def test_ensure_area_rejects_other_building(session):
    from server.db import Building, Organization, ensure_area
    from tests.conftest import make_building

    bld1 = make_building(session)
    org2 = Organization(slug="other-org", name="Other Org")
    session.add(org2)
    session.commit()
    bld2 = Building(org_id=org2.id, slug="other-bld", name="Other Building")
    session.add(bld2)
    session.commit()

    ensure_area(session, "floor10", "L10", bld1.id)
    with pytest.raises(ValueError, match="area floor10 belongs to another building"):
        ensure_area(session, "floor10", "L10", bld2.id)


def test_ensure_area_new_requires_building(session):
    from server.db import ensure_area

    with pytest.raises(ValueError, match="building_id is required for a new area"):
        ensure_area(session, "brand-new", "Brand New", None)


def test_ensure_area_unknown_building(session):
    from server.db import ensure_area

    with pytest.raises(ValueError, match="building 99999 not found"):
        ensure_area(session, "brand-new", "Brand New", 99999)
