"""API halaman area di dashboard: graf rute otomatis, ruangan, editan, uji rute, terbitkan.

Spesifikasi `docs/specs/2026-10-21-dashboard-rute-otomatis-design.md` bagian 5 dan 6. Semua
endpoint di bawah /api (Cloudflare Access + JWT); menulis dan menerbitkan hanya admin. Graf dasar
diturunkan dari jalur kamera versi peta yang dilayani; ruangan, editan, dan graf terbit di database.
"""

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlmodel import select

from server import auth, floorplan, navgraph, routegraph, uploads, walkable
from server.db import PublishedGraph, Room, RouteEdit, WalkableStroke, active_version
from server.floorplan import to_building

router = APIRouter()
_cache: dict = {}

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
XY = Annotated[list[float], Field(min_length=2, max_length=2)]


class RoomIn(BaseModel):
    name: Name
    x: float
    y: float


class RoomPatch(BaseModel):
    name: Name | None = None
    x: float | None = None
    y: float | None = None


class EditIn(BaseModel):
    kind: Literal["add_edge", "remove_edge", "move_node"]
    a: XY
    b: XY


class StrokeIn(BaseModel):
    # Radius dan koordinat diperiksa di add_stroke: FastAPI tidak bisa menyajikan galat validasi
    # yang memuat NaN (jadi 500), jadi NaN tidak boleh sampai ke validasi pydantic.
    mode: Literal["paint", "erase"]
    radius: float
    points: list[Annotated[list[float], Field(min_length=2, max_length=2)]] = Field(
        min_length=1, max_length=2000
    )


class RouteIn(BaseModel):
    start: XY = Field(alias="from")
    room_id: int


def clear_cache() -> None:
    _cache.clear()


def _area(request: Request, area_id: str):
    st = request.app.state
    if area_id != getattr(st, "area_id", None) or getattr(st, "localizer", None) is None:
        raise HTTPException(409, f"area not served: {area_id}")
    return st.localizer


def _aligned(request: Request, area_id: str):
    loc = _area(request, area_id)
    if loc.align is None:
        raise HTTPException(409, "map version not aligned")
    return loc


def _write(request: Request, user: str) -> None:
    # Sama dengan Terbitkan versi peta: application/json butuh preflight CORS (menutup CSRF lewat
    # cookie Access), dan menulis hanya admin.
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(415, "send with Content-Type: application/json")
    if not auth.is_admin(user):
        raise HTTPException(403, "only admins can change rooms and routes")


def _sequences(area_id: str, loc) -> list[list[tuple[float, float]]]:
    """Urutan pusat kamera (urut nama frame) di G, dipotong bila loncat; di-cache."""
    key = ("seq", area_id, json.dumps(loc.align, sort_keys=True), len(loc.model.images))
    if key not in _cache:
        imgs = sorted(loc.model.images.values(), key=lambda im: im.name)
        seqs = []
        if imgs:
            centers = np.array([im.projection_center() for im in imgs])
            g = to_building(centers, loc.align["meter_from_model"])
            seqs = routegraph.split_sequences([(float(x), float(y)) for x, y, _ in g])
        _cache[key] = seqs
    return _cache[key]


def base_graph(area_id: str, loc) -> routegraph.Graph:
    """Graf dasar dari urutan kamera, di-cache per area dan align.json."""
    key = ("graph", area_id, json.dumps(loc.align, sort_keys=True), len(loc.model.images))
    if key not in _cache:
        _cache[key] = routegraph.build_base_graph(_sequences(area_id, loc))
    return _cache[key]


def _rooms(s, area_id: str) -> list[dict]:
    rows = s.exec(select(Room).where(Room.area_id == area_id).order_by(Room.id)).all()
    return [{"id": r.id, "name": r.name, "x": r.x, "y": r.y} for r in rows]


def _edits(s, area_id: str) -> list[dict]:
    rows = s.exec(select(RouteEdit).where(RouteEdit.area_id == area_id).order_by(RouteEdit.id))
    return [{"id": e.id, "kind": e.kind, "a": [e.ax, e.ay], "b": [e.bx, e.by]} for e in rows]


def _draft(s, area_id: str, loc):
    base = base_graph(area_id, loc)
    edited, unmatched = routegraph.apply_edits(base, _edits(s, area_id))
    nav, warnings = routegraph.compose_navgraph(edited, _rooms(s, area_id))
    if unmatched:
        warnings.append(f"{len(unmatched)} route edit(s) no longer match the route graph")
    return base, nav, warnings, unmatched


@router.get("/api/areas/{area_id}/graph")
def get_graph(area_id: str, request: Request, user: uploads.User, s: uploads.DB) -> dict:
    loc = _aligned(request, area_id)
    base, nav, warnings, unmatched = _draft(s, area_id, loc)
    pub = s.get(PublishedGraph, area_id)
    return {
        "base": routegraph.compose_navgraph(base, [])[0],
        "edits": _edits(s, area_id),
        "rooms": _rooms(s, area_id),
        "draft": nav,
        "warnings": warnings,
        "unmatched_edits": unmatched,
        "published_at": pub.published_at.isoformat() if pub else None,
    }


def _unique_name(s, area_id: str, name: str, room_id: int | None = None) -> None:
    other = s.exec(select(Room).where(Room.area_id == area_id, Room.name == name)).first()
    if other is not None and other.id != room_id:
        raise HTTPException(409, f"a room named {name} already exists")


@router.post("/api/areas/{area_id}/rooms", status_code=201)
def add_room(area_id: str, body: RoomIn, request: Request, user: uploads.User, s: uploads.DB):
    _write(request, user)
    _area(request, area_id)
    _unique_name(s, area_id, body.name)
    room = Room(area_id=area_id, name=body.name, x=body.x, y=body.y, created_by=user)
    s.add(room)
    s.commit()
    return {"id": room.id, "name": room.name, "x": room.x, "y": room.y}


def _room(s, area_id: str, room_id: int) -> Room:
    room = s.get(Room, room_id)
    if room is None or room.area_id != area_id:
        raise HTTPException(404, "room not found")
    return room


@router.patch("/api/areas/{area_id}/rooms/{room_id}")
def edit_room(
    area_id: str, room_id: int, body: RoomPatch, request: Request, user: uploads.User, s: uploads.DB
):
    _write(request, user)
    room = _room(s, area_id, room_id)
    if body.name is not None:
        _unique_name(s, area_id, body.name, room_id)
        room.name = body.name
    room.x = room.x if body.x is None else body.x
    room.y = room.y if body.y is None else body.y
    s.add(room)
    s.commit()
    return {"id": room.id, "name": room.name, "x": room.x, "y": room.y}


@router.delete("/api/areas/{area_id}/rooms/{room_id}", status_code=204)
def delete_room(area_id: str, room_id: int, user: uploads.User, s: uploads.DB) -> Response:
    if not auth.is_admin(user):
        raise HTTPException(403, "only admins can change rooms and routes")
    s.delete(_room(s, area_id, room_id))
    s.commit()
    return Response(status_code=204)


@router.post("/api/areas/{area_id}/edits", status_code=201)
def add_edit(area_id: str, body: EditIn, request: Request, user: uploads.User, s: uploads.DB):
    _write(request, user)
    _area(request, area_id)
    (ax, ay), (bx, by) = body.a, body.b
    e = RouteEdit(area_id=area_id, kind=body.kind, ax=ax, ay=ay, bx=bx, by=by, created_by=user)
    s.add(e)
    s.commit()
    return {"id": e.id, "kind": e.kind, "a": [e.ax, e.ay], "b": [e.bx, e.by]}


@router.delete("/api/areas/{area_id}/edits/{edit_id}", status_code=204)
def delete_edit(area_id: str, edit_id: int, user: uploads.User, s: uploads.DB) -> Response:
    if not auth.is_admin(user):
        raise HTTPException(403, "only admins can change rooms and routes")
    e = s.get(RouteEdit, edit_id)
    if e is None or e.area_id != area_id:
        raise HTTPException(404, "edit not found")
    s.delete(e)
    s.commit()
    return Response(status_code=204)


def _strokes(s, area_id: str) -> list[WalkableStroke]:
    q = select(WalkableStroke).where(WalkableStroke.area_id == area_id)
    return list(s.exec(q.order_by(WalkableStroke.id)).all())


def _grid(s, area_id: str, loc) -> walkable.Grid:
    """Grid rencana (seed jalur scan + goresan kuas, dierosi); di-cache per area, align, goresan."""
    m = _scene(area_id, loc)["meta"]
    rows = [{"mode": r.mode, "radius": r.radius, "points": r.points} for r in _strokes(s, area_id)]
    # Isi goresan ikut kunci: id bisa dipakai ulang setelah hapus (sqlite), id saja tidak cukup.
    digest = hashlib.sha1(json.dumps(rows).encode()).hexdigest()
    key = ("grid", area_id, json.dumps(loc.align, sort_keys=True), len(loc.model.images), digest)
    if key not in _cache:
        res = m["res_m"]
        bounds = (
            m["origin_x"],
            m["origin_y"],
            m["origin_x"] + m["width"] * res,
            m["origin_y"] + m["height"] * res,
        )
        try:
            _cache[key] = walkable.planning_grid(bounds, _sequences(area_id, loc), rows)
        except ValueError as e:
            raise HTTPException(409, "area too large for a walkable grid") from e
    return _cache[key]


@router.get("/api/areas/{area_id}/walkable")
def get_walkable(area_id: str, request: Request, user: uploads.User, s: uploads.DB) -> dict:
    grid = _grid(s, area_id, _aligned(request, area_id))
    return {
        **walkable.encode(grid),
        "walkable_cells": int(grid.cells.sum()),
        "strokes": [
            {"id": r.id, "mode": r.mode, "radius": r.radius, "points_count": len(r.points)}
            for r in _strokes(s, area_id)
        ],
        "warnings": walkable.room_warnings(grid, _rooms(s, area_id)),
    }


@router.post("/api/areas/{area_id}/strokes", status_code=201)
def add_stroke(area_id: str, body: StrokeIn, request: Request, user: uploads.User, s: uploads.DB):
    _write(request, user)
    _area(request, area_id)
    if not 0.1 <= body.radius <= 3:  # NaN juga gagal di sini
        raise HTTPException(422, "radius must be between 0.1 and 3")
    if not all(math.isfinite(c) for p in body.points for c in p):
        raise HTTPException(422, "coordinates must be finite numbers")
    row = WalkableStroke(
        area_id=area_id, mode=body.mode, radius=body.radius, points=body.points, created_by=user
    )
    s.add(row)
    s.commit()
    return {"id": row.id, "mode": row.mode, "radius": row.radius, "points_count": len(row.points)}


@router.delete("/api/areas/{area_id}/strokes/{stroke_id}", status_code=204)
def delete_stroke(area_id: str, stroke_id: int, user: uploads.User, s: uploads.DB) -> Response:
    if not auth.is_admin(user):
        raise HTTPException(403, "only admins can change the walkable area")
    row = s.get(WalkableStroke, stroke_id)
    if row is None or row.area_id != area_id:
        raise HTTPException(404, "stroke not found")
    s.delete(row)
    s.commit()
    return Response(status_code=204)


@router.delete("/api/areas/{area_id}/strokes", status_code=204)
def reset_strokes(area_id: str, user: uploads.User, s: uploads.DB) -> Response:
    if not auth.is_admin(user):
        raise HTTPException(403, "only admins can change the walkable area")
    for row in _strokes(s, area_id):
        s.delete(row)
    s.commit()
    return Response(status_code=204)


@router.post("/api/areas/{area_id}/route")
def test_route(area_id: str, body: RouteIn, request: Request, user: uploads.User, s: uploads.DB):
    loc = _aligned(request, area_id)
    room = _room(s, area_id, body.room_id)
    route = walkable.plan_route(_grid(s, area_id, loc), tuple(body.start), (room.x, room.y))
    return {"status": "unreachable"} if route is None else {"status": "ok", **route}


@router.post("/api/areas/{area_id}/publish-graph")
def publish_graph(area_id: str, request: Request, user: uploads.User, s: uploads.DB) -> dict:
    _write(request, user)
    loc = _aligned(request, area_id)
    base, nav, _, _ = _draft(s, area_id, loc)  # graf lama tetap diterbitkan untuk APK lama
    if not base["edges"]:
        raise HTTPException(409, "no route graph to publish: the scan path is empty")
    try:
        navgraph.validate(nav)
    except ValueError as e:
        raise HTTPException(409, f"route graph is invalid: {e}") from e
    rooms = _rooms(s, area_id)
    if not rooms:
        raise HTTPException(409, "add a room first")
    grid = _grid(s, area_id, loc)
    if not grid.cells.any():
        raise HTTPException(409, "no walkable area to publish")
    targets = [{"id": f"R{r['id']}", "name": r["name"], "x": r["x"], "y": r["y"]} for r in rooms]
    row = s.get(PublishedGraph, area_id) or PublishedGraph(
        area_id=area_id, graph={}, published_by=""
    )
    row.graph, row.walkable = nav, {**walkable.encode(grid), "targets": targets}
    row.published_by, row.published_at = user, datetime.now(row.published_at.tzinfo)
    s.add(row)
    s.commit()
    return {
        "published_at": row.published_at.isoformat(),
        "warnings": walkable.room_warnings(grid, rooms),
    }


def _scene(area_id: str, loc):
    """Pusat kamera (urut nama), titik, dan peta 2D di G; di-cache per area dan align.json."""
    key = ("scene", area_id, json.dumps(loc.align, sort_keys=True), len(loc.model.images))
    if key not in _cache:
        m = loc.align["meter_from_model"]
        imgs = sorted(loc.model.images.values(), key=lambda im: im.name)
        cams = to_building(np.array([im.projection_center() for im in imgs]).reshape(-1, 3), m)
        pts = list(loc.model.points3D.values())
        xyz = to_building(np.array([p.xyz for p in pts]).reshape(-1, 3), m)
        rgb = np.array([p.color for p in pts]).reshape(-1, 3)
        png, meta = floorplan.render_floorplan(xyz, cams)
        _cache[key] = {"imgs": imgs, "cams": cams, "xyz": xyz, "rgb": rgb, "png": png, "meta": meta}
    return _cache[key]


@router.get("/api/areas/{area_id}/plan")
def get_plan(area_id: str, request: Request, user: uploads.User) -> dict:
    sc = _scene(area_id, _aligned(request, area_id))
    trajectory = [[round(float(x), 3), round(float(y), 3)] for x, y, _ in sc["cams"]]
    return {**sc["meta"], "trajectory": trajectory}


@router.get("/api/areas/{area_id}/plan.png")
def get_plan_png(area_id: str, request: Request, user: uploads.User) -> Response:
    sc = _scene(area_id, _aligned(request, area_id))
    return Response(sc["png"], media_type="image/png")


@router.get("/api/areas/{area_id}/cloud.glb")
def get_cloud(area_id: str, request: Request, user: uploads.User) -> Response:
    sc = _scene(area_id, _aligned(request, area_id))
    return Response(floorplan.points_glb(sc["xyz"], sc["rgb"]), media_type="model/gltf-binary")


@router.get("/api/areas/{area_id}/photo")
def get_photo(
    area_id: str, x: float, y: float, request: Request, user: uploads.User, s: uploads.DB
) -> Response:
    loc = _aligned(request, area_id)
    sc = _scene(area_id, loc)
    v = active_version(s, area_id)
    if v is None or not len(sc["cams"]):
        raise HTTPException(404, "photo not available")
    i = int(np.argmin(np.hypot(sc["cams"][:, 0] - x, sc["cams"][:, 1] - y)))
    path = Path(v.path) / "thumbs" / Path(sc["imgs"][i].name).name
    if not path.is_file():
        raise HTTPException(404, "photo not available: scan photos were not prepared for this map")
    # Arah depan kamera COLMAP (z) di dunia = baris ketiga cam_from_world, lalu diputar ke G.
    fwd = floorplan.to_building(
        sc["imgs"][i].cam_from_world().rotation.matrix()[2][None, :],
        {**loc.align["meter_from_model"], "scale": 1.0, "translation": [0, 0, 0]},
    )[0]
    heading = math.degrees(math.atan2(fwd[1], fwd[0]))
    return Response(
        path.read_bytes(), media_type="image/jpeg", headers={"X-Heading-Deg": f"{heading:.1f}"}
    )
