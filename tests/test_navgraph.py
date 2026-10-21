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


def write_sheets(tmp_path, points, edges, targets):
    for name, header, rows in (
        ("points.csv", "point,x_m,y_m", points),
        ("edges.csv", "a,b", edges),
        ("targets.csv", "node,name", targets),
    ):
        (tmp_path / name).write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return tmp_path / "points.csv", tmp_path / "edges.csv", tmp_path / "targets.csv"


def test_build_takes_coordinates_from_the_reference_points(tmp_path):
    # P09 hanya titik acuan penyelarasan (tidak di sisi atau target): bukan simpul
    sheets = write_sheets(
        tmp_path,
        ["P01,0.00,0.40", "P02,1.50,1.60", "P09,7.0,2.0"],
        ["P01,P02"],
        ["P02,Pintu Lab"],
    )
    assert navgraph.build(*sheets) == GOOD


def test_build_rejects_an_edge_to_an_unmeasured_point(tmp_path):
    sheets = write_sheets(tmp_path, ["P01,0,0", "P02,1,0"], ["P01,P07"], ["P02,Lab"])
    with pytest.raises(ValueError, match="P07"):
        navgraph.build(*sheets)


def test_build_names_the_line_of_a_comma_decimal(tmp_path):
    # Excel berlokal Indonesia menulis 1,50: baris itu punya kolom lebih
    sheets = write_sheets(tmp_path, ["P01,0,0", 'P02,"1,50",0'], ["P01,P02"], ["P02,Lab"])
    with pytest.raises(ValueError, match="P02"):
        navgraph.build(*sheets)


def test_build_cli_writes_a_valid_file(tmp_path, monkeypatch, capsys):
    sheets = write_sheets(
        tmp_path, ["P01,0,0", "P02,1,0", "P03,9,9"], ["P01,P02"], ["P02,Lab", "P03,Gudang"]
    )
    out = tmp_path / "navgraph.json"
    monkeypatch.setattr(
        "sys.argv",
        ["navgraph", "build", *map(str, sheets), str(out)],
    )
    navgraph.main()
    written = navgraph.validate(json.loads(out.read_text(encoding="utf-8")))
    assert written["targets"][1]["node"] == "P03"
    assert "P03" in capsys.readouterr().out  # peringatan simpul tidak terhubung


def test_navgraph_prefers_the_published_graph(tmp_path, monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine

    from server.db import Area, PublishedGraph

    url = f"sqlite:///{tmp_path / 'n.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    published = broken(["targets"], [{"node": "P01", "name": "Dari dashboard"}])
    with Session(engine) as s:
        s.add(Area(id="floor10", name="L10"))
        s.add(PublishedGraph(area_id="floor10", graph=published, published_by="dev@local"))
        s.commit()
    write_graph(tmp_path, "floor10", GOOD)
    monkeypatch.setenv("DATABASE_URL", url)
    r = client_for(tmp_path, monkeypatch).get("/navgraph")
    assert r.status_code == 200 and r.json()["graph"] == published


def test_navgraph_falls_back_to_the_file_without_database(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    write_graph(tmp_path, "floor10", GOOD)
    assert client_for(tmp_path, monkeypatch).get("/navgraph").json()["graph"] == GOOD
