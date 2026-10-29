"""Pemindahan konten area saat penyelarasan berganti (roadmap M1-4, opsi A di spesifikasi)."""

import math

import numpy as np
import pycolmap
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from server import content_migration, sim3
from server.db import Area, PublishedGraph, Room, RouteEdit, WalkableStroke


def align(scale, q, t, h=1.3):
    q = np.array(q, float)
    return {
        "meter_from_model": {
            "scale": scale,
            "rotation_xyzw": (q / np.linalg.norm(q)).tolist(),
            "translation": list(t),
        },
        "phone_height_m": h,
    }


OLD = align(0.25, [0.1, 0.7, 0.2, 0.68], [3.0, -1.0, 2.0])
NEW = align(0.30, [0.5, -0.2, 0.4, 0.7], [-2.0, 4.0, 0.5])


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Area(id="floor10", name="Lantai 10"))
        s.add(Area(id="floor9", name="Lantai 9"))
        s.commit()
        yield s


def g_of(a, m):
    return (sim3.from_align(a["meter_from_model"]) * np.array([m], float))[0]


def test_from_align_matches_the_alignment_dict():
    sim = sim3.from_align(OLD["meter_from_model"])
    assert isinstance(sim, pycolmap.Sim3d) and sim.scale == pytest.approx(0.25)
    np.testing.assert_allclose(sim.translation, [3.0, -1.0, 2.0])


def test_content_stays_on_the_same_physical_place(session):
    m = np.array([1.0, 2.0, 3.0])
    x, y, _ = g_of(OLD, m)
    session.add(Room(area_id="floor10", name="Lab", x=float(x), y=float(y), created_by="a"))
    session.commit()
    # ruangan ditaruh di G lama pada ketinggian ponsel: titik model yang sama adalah m dengan z
    # yang menghasilkan 1,3 m di G lama
    z_model = (sim3.from_align(OLD["meter_from_model"]).inverse() * np.array([[x, y, 1.3]]))[0]
    content_migration.migrate(session, "floor10", OLD, NEW)
    session.commit()
    room = session.exec(select(Room)).one()
    expect = g_of(NEW, z_model)
    assert (room.x, room.y) == pytest.approx((expect[0], expect[1]), abs=1e-6)


def levelled(old, scale, deg):
    """Penyelarasan baru yang meratakan lantai seperti yang lama: hanya putar di sekitar z."""
    th = np.radians(deg)
    yaw = pycolmap.Rotation3d(np.array([0, 0, np.sin(th / 2), np.cos(th / 2)]))
    q = (yaw * pycolmap.Rotation3d(np.array(old["meter_from_model"]["rotation_xyzw"]))).quat
    return align(scale, q.tolist(), [-2.0, 4.0, 0.5])


def test_distance_between_rooms_scales_by_the_ratio(session):
    new = levelled(OLD, 0.30, 40.0)
    session.add(Room(area_id="floor10", name="A", x=1.0, y=2.0, created_by="a"))
    session.add(Room(area_id="floor10", name="B", x=7.0, y=-3.0, created_by="a"))
    session.commit()
    before = math.dist((1.0, 2.0), (7.0, -3.0))
    content_migration.migrate(session, "floor10", OLD, new)
    a, b = session.exec(select(Room).order_by(Room.name)).all()
    assert math.dist((a.x, a.y), (b.x, b.y)) == pytest.approx(before * 0.30 / 0.25, rel=1e-9)


def test_stroke_radius_scales_and_points_move(session):
    session.add(
        WalkableStroke(
            area_id="floor10",
            mode="paint",
            radius=0.5,
            points=[[1.0, 2.0], [3.0, 4.0]],
            created_by="a",
        )
    )
    session.commit()
    move = content_migration.plane_transform(OLD["meter_from_model"], NEW["meter_from_model"], 1.3)
    n = content_migration.migrate(session, "floor10", OLD, NEW)
    session.commit()
    st = session.exec(select(WalkableStroke)).one()
    assert n["strokes"] == 1 and st.radius == pytest.approx(0.5 * 0.30 / 0.25)
    assert st.points[1] == pytest.approx(list(move(3.0, 4.0)), abs=1e-9)
    assert move.scale == pytest.approx(1.2)


def test_route_edits_move(session):
    session.add(
        RouteEdit(area_id="floor10", kind="add_edge", ax=1, ay=2, bx=5, by=6, created_by="a")
    )
    session.commit()
    move = content_migration.plane_transform(OLD["meter_from_model"], NEW["meter_from_model"], 1.3)
    n = content_migration.migrate(session, "floor10", OLD, NEW)
    session.commit()
    e = session.exec(select(RouteEdit)).one()
    assert n["edits"] == 1
    assert (e.ax, e.ay) == pytest.approx(move(1, 2), abs=1e-9)
    assert (e.bx, e.by) == pytest.approx(move(5, 6), abs=1e-9)


def test_other_areas_are_untouched(session):
    session.add(Room(area_id="floor9", name="Lab", x=1.0, y=2.0, created_by="a"))
    session.commit()
    content_migration.migrate(session, "floor10", OLD, NEW)
    session.commit()
    r = session.exec(select(Room)).one()
    assert (r.x, r.y) == (1.0, 2.0)


def test_republish_is_required_only_when_a_graph_was_published(session):
    assert content_migration.migrate(session, "floor10", OLD, NEW)["republish_required"] is False
    session.add(PublishedGraph(area_id="floor10", graph={}, published_by="a"))
    session.commit()
    assert content_migration.migrate(session, "floor10", OLD, NEW)["republish_required"] is True
    assert content_migration.migrate(session, "floor9", OLD, NEW)["republish_required"] is False


def test_first_alignment_moves_nothing(session):
    session.add(Room(area_id="floor10", name="Lab", x=1.0, y=2.0, created_by="a"))
    session.commit()
    n = content_migration.migrate(session, "floor10", None, NEW)
    session.commit()
    assert (n["rooms"], n["strokes"], n["edits"]) == (0, 0, 0)
    assert (session.exec(select(Room)).one().x) == 1.0
