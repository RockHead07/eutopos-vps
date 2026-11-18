"""Uji perintah CLI manage untuk manajemen gedung dan opsi --building."""

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from server import manage
from server.db import Area, Building, Organization
from tests.conftest import make_building


@pytest.fixture
def cli_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    eng = create_engine(url)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        bld = make_building(s)
        s.add(Area(id="floor10", name="Lantai 10", building_id=bld.id))
        s.commit()
    monkeypatch.setattr(manage, "engine_from_env", lambda: eng)
    return eng


def test_building_add_and_list(cli_db, monkeypatch, capsys):
    # Tambah gedung baru lewat CLI
    monkeypatch.setattr("sys.argv", ["manage", "building", "add", "pens", "Politeknik Elektronika"])
    manage.main()

    with Session(cli_db) as s:
        b = s.exec(select(Building).where(Building.slug == "pens")).first()
        assert b is not None
        assert b.name == "Politeknik Elektronika"

    # List gedung
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["manage", "building", "list"])
    manage.main()
    out = capsys.readouterr().out
    assert "hcm" in out
    assert "pens" in out
    # Format: slug  name  jumlah-area
    lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
    hcm_line = next(line for line in lines if line.startswith("hcm"))
    assert "1" in hcm_line  # floor10 ada di hcm
    pens_line = next(line for line in lines if line.startswith("pens"))
    assert "0" in pens_line  # belum ada area di pens


def test_manage_building_unknown_rejects(cli_db, monkeypatch):
    # register dengan gedung tidak dikenal
    monkeypatch.setattr(
        "sys.argv",
        ["manage", "register", "area-x", "Area X", "/maps/dummy", "--building", "unknown-slug"],
    )
    with pytest.raises(SystemExit) as exc:
        manage.main()
    assert "building unknown-slug not found" in str(exc.value)

    # job dengan gedung tidak dikenal
    monkeypatch.setattr(
        "sys.argv",
        [
            "manage",
            "job",
            "area-y",
            "Area Y",
            "--map",
            "some-map.mp4",
            "--building",
            "unknown-slug",
        ],
    )
    with pytest.raises(SystemExit) as exc2:
        manage.main()
    assert "building unknown-slug not found" in str(exc2.value)


def test_manage_register_with_building(cli_db, tmp_path, monkeypatch):
    # Buat gedung pens dulu
    with Session(cli_db) as s:
        org = s.exec(select(Organization)).first()
        bld = Building(org_id=org.id, slug="pens", name="PENS")
        s.add(bld)
        s.commit()
        s.refresh(bld)
        pens_id = bld.id

    # Siapkan folder peta dummy yang lolos missing_files
    from server.map_layout import required_files

    map_dir = tmp_path / "map_dummy"
    for p in required_files(map_dir, 1024, 1024, 512):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()

    monkeypatch.setattr(
        "sys.argv",
        ["manage", "register", "pens-hall", "PENS Hall", str(map_dir), "--building", "pens"],
    )
    manage.main()

    with Session(cli_db) as s:
        area = s.get(Area, "pens-hall")
        assert area is not None
        assert area.building_id == pens_id


def test_manage_job_with_building(cli_db, tmp_path, monkeypatch):
    # Buat gedung pens
    with Session(cli_db) as s:
        org = s.exec(select(Organization)).first()
        bld = Building(org_id=org.id, slug="pens", name="PENS")
        s.add(bld)
        s.commit()
        s.refresh(bld)
        pens_id = bld.id

    dummy_video = tmp_path / "test.mp4"
    dummy_video.write_bytes(b"dummy video")

    monkeypatch.setattr(
        "sys.argv",
        [
            "manage",
            "job",
            "pens-lab",
            "PENS Lab",
            "--map",
            str(dummy_video),
            "--building",
            "pens",
        ],
    )
    manage.main()

    with Session(cli_db) as s:
        area = s.get(Area, "pens-lab")
        assert area is not None
        assert area.building_id == pens_id
