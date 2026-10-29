"""Pindahkan konten area ketika penyelarasan berganti (opsi A di spesifikasi editor penyelarasan).

Ruangan, editan rute, dan goresan walkable disimpan dalam koordinat G. Saat align.json berganti,
titik G lama dipetakan ke tempat fisik yang sama: kebalikan Sim3 lama ke model, lalu Sim3 baru ke G
baru, pada ketinggian ponsel (G hanya 2D). Graf yang sudah diterbitkan berupa grid bit yang tidak
aman diputar, jadi hanya ditandai harus diterbitkan ulang.
"""

from collections.abc import Callable

import numpy as np
from sqlmodel import Session, select

from server import sim3
from server.db import PublishedGraph, Room, RouteEdit, WalkableStroke

DEFAULT_HEIGHT_M = 1.3


def plane_transform(
    old: dict, new: dict, z: float
) -> Callable[[float, float], tuple[float, float]]:
    """(x, y) di G lama ke (x, y) di G baru; old dan new berupa isi `meter_from_model`."""
    back = sim3.from_align(old).inverse()
    forward = sim3.from_align(new)

    def move(x: float, y: float) -> tuple[float, float]:
        g = (forward * (back * np.array([[x, y, z]], float)))[0]
        return float(g[0]), float(g[1])

    move.scale = float(new["scale"]) / float(old["scale"])  # type: ignore[attr-defined]
    return move


def migrate(s: Session, area_id: str, old_align: dict | None, new_align: dict) -> dict:
    """Pindahkan konten area; tanpa commit. old_align None = belum ada konten di G."""
    out = {"rooms": 0, "strokes": 0, "edits": 0}
    if old_align is not None:
        z = new_align.get("phone_height_m", DEFAULT_HEIGHT_M)
        move = plane_transform(old_align["meter_from_model"], new_align["meter_from_model"], z)
        for r in s.exec(select(Room).where(Room.area_id == area_id)):
            r.x, r.y = move(r.x, r.y)
            s.add(r)
            out["rooms"] += 1
        for e in s.exec(select(RouteEdit).where(RouteEdit.area_id == area_id)):
            e.ax, e.ay = move(e.ax, e.ay)
            e.bx, e.by = move(e.bx, e.by)
            s.add(e)
            out["edits"] += 1
        for st in s.exec(select(WalkableStroke).where(WalkableStroke.area_id == area_id)):
            st.points = [list(move(px, py)) for px, py in st.points]  # objek baru: JSON dilacak
            st.radius = st.radius * move.scale  # type: ignore[attr-defined]
            s.add(st)
            out["strokes"] += 1
    graph = s.get(PublishedGraph, area_id)
    return {**out, "republish_required": graph is not None}
