"""Graf navigasi per area (spesifikasi eutopos-mobile bagian 7 dan 8)."""

import copy
import json
import math
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import navgraph

GOOD = {
    "frame": "building",
    "units": "m",
    "nodes": [{"id": "P01", "x": 0.0, "y": 0.4}, {"id": "P02", "x": 1.5, "y": 1.6}],
    "edges": [["P01", "P02"]],
    "targets": [{"node": "P02", "name": "Pintu Lab"}],
}


def broken(path, value):
    g = copy.deepcopy(GOOD)
    obj = g
    for key in path[:-1]:
        obj = obj[key]
    obj[path[-1]] = value
    return g


def test_valid_graph_is_returned_unchanged():
    assert navgraph.validate(copy.deepcopy(GOOD)) == GOOD


@pytest.mark.parametrize(
    ("graph", "words"),
    [
        (broken(["frame"], "model"), "frame"),
        (broken(["units"], "cm"), "units"),
        (broken(["nodes"], []), "nodes"),
        (broken(["nodes", 1, "id"], "P01"), "ganda"),
        (broken(["nodes", 0, "x"], "1.0"), "bukan angka"),
        (broken(["nodes", 0, "x"], True), "bukan angka"),
        (broken(["nodes", 0, "y"], math.nan), "bukan angka"),
        (broken(["edges"], [["P01", "P99"]]), "P99"),
        (broken(["edges"], [["P01", "P01"]]), "dirinya"),
        (broken(["edges"], [["P01"]]), "pasangan"),
        (broken(["targets"], [{"node": "P99", "name": "x"}]), "target"),
        (broken(["targets"], [{"node": "P02", "name": ""}]), "target"),
        (broken(["targets"], [{"node": ["P02"], "name": "x"}]), "target"),
        (broken(["nodes", 0, "x"], 10**400), "bukan angka"),
        ("bukan objek", "objek"),
    ],
)
def test_invalid_graph_is_rejected_with_the_reason(graph, words):
    with pytest.raises(ValueError, match=words):
        navgraph.validate(graph)


def test_disconnected_nodes_are_listed():
    g = copy.deepcopy(GOOD)
    g["nodes"].append({"id": "P03", "x": 9.0, "y": 9.0})
    assert navgraph.disconnected_nodes(g) == ["P03"]
    assert navgraph.disconnected_nodes(GOOD) == []


@pytest.mark.parametrize("area", ["../etc", "a/b", "..", "", "."])
def test_graph_path_refuses_area_ids_that_leave_the_maps_folder(area):
    with pytest.raises(ValueError):
        navgraph.graph_path(Path("/maps"), area)


def test_graph_path_is_per_area(tmp_path):
    assert navgraph.graph_path(tmp_path, "floor10") == tmp_path / "floor10" / "navgraph.json"


def test_maps_root_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("EUTOPOS_MAPS_ROOT", str(tmp_path))
    assert navgraph.maps_root() == tmp_path
    monkeypatch.delenv("EUTOPOS_MAPS_ROOT")
    assert navgraph.maps_root() == Path("/maps")


def client_for(tmp_path, monkeypatch, area="floor10", version=3):
    monkeypatch.setenv("EUTOPOS_MAPS_ROOT", str(tmp_path))
    app = FastAPI()
    app.include_router(navgraph.router)
    app.state.area_id, app.state.map_version = area, version
    return TestClient(app)


def write_graph(tmp_path, area, data):
    (tmp_path / area).mkdir(parents=True, exist_ok=True)
    (tmp_path / area / "navgraph.json").write_text(json.dumps(data), encoding="utf-8")


def test_navgraph_serves_the_active_area(tmp_path, monkeypatch):
    write_graph(tmp_path, "floor10", GOOD)
    r = client_for(tmp_path, monkeypatch).get("/navgraph")
    assert r.status_code == 200
    assert r.json() == {"area_id": "floor10", "map_version": 3, "graph": GOOD}


def test_navgraph_missing_file_is_404(tmp_path, monkeypatch):
    r = client_for(tmp_path, monkeypatch).get("/navgraph")
    assert r.status_code == 404 and "floor10" in r.json()["detail"]


def test_navgraph_without_active_map_is_503(tmp_path, monkeypatch):
    r = client_for(tmp_path, monkeypatch, area=None, version=None).get("/navgraph")
    assert r.status_code == 503


def test_navgraph_broken_file_is_500_with_reason(tmp_path, monkeypatch):
    write_graph(tmp_path, "floor10", broken(["edges"], [["P01", "P99"]]))
    r = client_for(tmp_path, monkeypatch).get("/navgraph")
    assert r.status_code == 500 and "P99" in r.json()["detail"]


def test_navgraph_not_json_is_500(tmp_path, monkeypatch):
    (tmp_path / "floor10").mkdir()
    (tmp_path / "floor10" / "navgraph.json").write_text("{bukan json", encoding="utf-8")
    assert client_for(tmp_path, monkeypatch).get("/navgraph").status_code == 500
