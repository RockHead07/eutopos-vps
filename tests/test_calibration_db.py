"""Tabel kalibrasi (roadmap M1-2): set, titik, pengamatan, riwayat, dan migrasi 0006."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from server.db import (
    Alignment,
    Area,
    CalibrationObservation,
    CalibrationPoint,
    CalibrationSet,
    MapVersion,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Area(id="floor10", name="Lantai 10"))
        s.add(MapVersion(area_id="floor10", version=1, path="/maps/floor10/v1"))
        s.commit()
        yield s


def make_set(session) -> CalibrationSet:
    cal = CalibrationSet(area_id="floor10", map_version_id=1, created_by="a@x.id", note="uji")
    session.add(cal)
    session.commit()
    return cal


def test_tables_exist_and_hold_a_set(session):
    cal = make_set(session)
    session.add(CalibrationPoint(set_id=cal.id, point_id="P01", x_m=0.0, y_m=0.0, role="reference"))
    session.add(CalibrationPoint(set_id=cal.id, point_id="P02", x_m=3.5, y_m=1.0, role="test"))
    session.add(
        CalibrationObservation(
            set_id=cal.id, point_id="P01", model_xyz=[1.0, 2.0, 3.0], inliers=120, source="import"
        )
    )
    session.add(
        Alignment(
            map_version_id=1,
            set_id=cal.id,
            params={"meter_from_model": {"scale": 0.25}},
            stats={"scale": 0.25, "residual_median_m": 0.1},
            status="applied",
            source="fit",
            created_by="a@x.id",
        )
    )
    session.commit()
    session.expire_all()

    assert session.get(CalibrationSet, cal.id).note == "uji"
    points = session.exec(select(CalibrationPoint).order_by(CalibrationPoint.point_id)).all()
    assert [(p.point_id, p.x_m, p.y_m, p.role) for p in points] == [
        ("P01", 0.0, 0.0, "reference"),
        ("P02", 3.5, 1.0, "test"),
    ]
    obs = session.exec(select(CalibrationObservation)).one()
    assert (obs.model_xyz, obs.inliers, obs.heading_deg, obs.query) == (
        [1.0, 2.0, 3.0],
        120,
        None,
        None,
    )
    al = session.exec(select(Alignment)).one()
    assert al.params == {"meter_from_model": {"scale": 0.25}}
    assert (al.status, al.source, al.applied_at, al.set_id) == ("applied", "fit", None, cal.id)


def test_point_id_is_unique_per_set(session):
    cal = make_set(session)
    session.add(CalibrationPoint(set_id=cal.id, point_id="P01", x_m=0, y_m=0, role="reference"))
    session.commit()
    session.add(CalibrationPoint(set_id=cal.id, point_id="P01", x_m=1, y_m=1, role="test"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_allows_one_applied_alignment_per_version(session):
    def al(status):
        return Alignment(
            map_version_id=1, params={}, stats={}, status=status, source="fit", created_by="a"
        )

    session.add_all([al("superseded"), al("superseded"), al("applied")])
    session.commit()
    session.add(al("applied"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_same_point_id_is_fine_in_another_set(session):
    a, b = make_set(session), make_set(session)
    session.add(CalibrationPoint(set_id=a.id, point_id="P01", x_m=0, y_m=0, role="reference"))
    session.add(CalibrationPoint(set_id=b.id, point_id="P01", x_m=0, y_m=0, role="reference"))
    session.commit()


def test_migration_0006_up_down_up(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect

    cfg = Config("server/alembic.ini")
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    tables = {"calibration_set", "calibration_point", "calibration_observation", "alignment"}

    def present():
        return tables & set(inspect(create_engine(url)).get_table_names())

    command.upgrade(cfg, "head")
    assert ScriptDirectory.from_config(cfg).get_current_head() == "0006"
    assert present() == tables
    command.downgrade(cfg, "0005")
    assert present() == set()
    command.upgrade(cfg, "head")
    assert present() == tables
