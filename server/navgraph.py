"""Graf navigasi per area untuk klien eutopos-mobile (spesifikasi bagian 7 dan 8).

Berkas <maps>/<area_id>/navgraph.json, kerangka gedung G (meter, tangan kanan, z ke atas):
    {"frame": "building", "units": "m",
     "nodes": [{"id": "P01", "x": 0.0, "y": 0.4}, ...],
     "edges": [["P01", "P02"], ...],
     "targets": [{"node": "P02", "name": "Pintu Lab"}, ...]}
Per area, bukan per versi peta: koordinat gedung tidak berubah saat peta dibangun ulang.
"""

import json
import math
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

FILE_NAME = "navgraph.json"


def maps_root() -> Path:
    return Path(os.environ.get("EUTOPOS_MAPS_ROOT", "/maps"))


def graph_path(root: Path, area_id: str) -> Path:
    if not area_id or area_id in (".", "..") or Path(area_id).name != area_id:
        raise ValueError(f"area_id tidak sah: {area_id!r}")
    return root / area_id / FILE_NAME


def _number(v) -> bool:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:  # bilangan bulat JSON di luar jangkauan float
        return False


def validate(data) -> dict:
    """Periksa isi navgraph dan kembalikan apa adanya. ValueError menyebut kesalahan pertama."""
    if not isinstance(data, dict):
        raise ValueError("navgraph harus objek JSON")
    if data.get("frame") != "building":
        raise ValueError('frame harus "building"')
    if data.get("units") != "m":
        raise ValueError('units harus "m"')
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("nodes kosong")
    ids = set()
    for n in nodes:
        if not isinstance(n, dict) or not isinstance(n.get("id"), str) or not n["id"]:
            raise ValueError(f"simpul tanpa id: {n!r}")
        if n["id"] in ids:
            raise ValueError(f"id simpul ganda: {n['id']}")
        for k in ("x", "y"):
            if not _number(n.get(k)):
                raise ValueError(f"simpul {n['id']}: {k} bukan angka")
        ids.add(n["id"])
    edges = data.get("edges")
    if not isinstance(edges, list):
        raise ValueError("edges harus daftar")
    for e in edges:
        if not (isinstance(e, list) and len(e) == 2 and all(isinstance(i, str) for i in e)):
            raise ValueError(f"sisi harus pasangan id: {e!r}")
        if e[0] == e[1]:
            raise ValueError(f"sisi ke dirinya sendiri: {e[0]}")
        for i in e:
            if i not in ids:
                raise ValueError(f"sisi merujuk simpul yang tidak ada: {i}")
    targets = data.get("targets")
    if not isinstance(targets, list):
        raise ValueError("targets harus daftar")
    for t in targets:
        ok = isinstance(t, dict) and isinstance(t.get("node"), str) and t["node"] in ids
        if not ok or not isinstance(t.get("name"), str) or not t["name"]:
            raise ValueError(f"target tidak sah: {t!r}")
    return data


def disconnected_nodes(data: dict) -> list[str]:
    """Simpul yang tidak terhubung ke simpul pertama (peringatan, bukan galat)."""
    adj = {n["id"]: set() for n in data["nodes"]}
    for a, b in data["edges"]:
        adj[a].add(b)
        adj[b].add(a)
    start = data["nodes"][0]["id"]
    seen, todo = {start}, [start]
    while todo:
        for nxt in adj[todo.pop()] - seen:
            seen.add(nxt)
            todo.append(nxt)
    return [n["id"] for n in data["nodes"] if n["id"] not in seen]


router = APIRouter()


@router.get("/navgraph")
def get_navgraph(request: Request) -> dict:
    """Graf navigasi area aktif. Tanpa identitas pengguna, sama seperti /localize."""
    st = request.app.state
    area_id = getattr(st, "area_id", None)
    if area_id is None:
        raise HTTPException(503, "no active map")
    path = graph_path(maps_root(), area_id)
    if not path.exists():
        raise HTTPException(404, f"no navgraph for area {area_id}")
    try:
        graph = validate(json.loads(path.read_text(encoding="utf-8")))
    except ValueError as e:  # json.JSONDecodeError juga ValueError
        raise HTTPException(500, f"navgraph.json invalid: {e}") from e
    return {"area_id": area_id, "map_version": getattr(st, "map_version", None), "graph": graph}
