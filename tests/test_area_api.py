"""API halaman area: graf rute, ruangan, editan, uji rute, terbitkan (spek 2026-10-21)."""

import threading
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server import area_api, auth, navgraph, uploads
from server.db import Area, MapVersion

IDENTITY = {
    "meter_from_model": {"scale": 1.0, "rotation_xyzw": [0, 0, 0, 1], "translation": [0, 0, 0]}
}


def camera_path():
    """Jalur L sintetis pada ketinggian ponsel: x 0..6 lalu y 0..4, tiap 0,1 m."""
    pts = [(i / 10, 0.0) for i in range(61)] + [(6.0, i / 10) for i in range(1, 41)]
    return [np.array([x, y, 1.3]) for x, y in pts]


# Kamera menghadap +x di G: baris ketiga cam_from_world = arah depan (z kamera) di dunia.
FACING_X = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])


def fake_image(i, c):
    pose = SimpleNamespace(rotation=SimpleNamespace(matrix=lambda: FACING_X))
    return SimpleNamespace(
        name=f"mapping/job1-v0-x_{i:05d}.jpg",
        projection_center=lambda: c,
        cam_from_world=lambda: pose,
    )


def fake_localizer(centers, align=IDENTITY):
    images = {i: fake_image(i, c) for i, c in enumerate(centers)}
    points = {1: SimpleNamespace(xyz=np.array([3.0, 0.5, 1.0]), color=np.array([200, 10, 10]))}
    return SimpleNamespace(model=SimpleNamespace(images=images, points3D=points), align=align)


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Area(id="floor10", name="Lantai 10"))
        s.commit()
        map_dir = tmp_path / "maps" / "floor10" / "job-1"
        s.add(MapVersion(area_id="floor10", version=1, path=str(map_dir), status="published"))
        s.commit()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.setenv("EUTOPOS_MAPS_ROOT", str(tmp_path / "maps"))
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    app = FastAPI()
    app.include_router(uploads.router)
    app.include_router(area_api.router)
    app.include_router(navgraph.router)
    st = app.state
    st.localizer, st.area_id, st.map_version = fake_localizer(camera_path()), "floor10", 1
    st.lock = threading.Lock()
    area_api.clear_cache()
    with TestClient(app) as c:
        c.map_dir = map_dir
        yield c


def add_room(client, name="Lab", x=3.0, y=0.3):
    return client.post("/api/areas/floor10/rooms", json={"name": name, "x": x, "y": y})


def as_guest(client, monkeypatch):
    monkeypatch.setenv("EUTOPOS_ADMINS", "boss@x.id")
    client.app.dependency_overrides[auth.current_user] = lambda: "tamu@x.id"


def test_graph_is_built_from_the_camera_path(client):
    g = client.get("/api/areas/floor10/graph").json()
    assert len(g["base"]["nodes"]) >= 3
    assert g["rooms"] == [] and g["edits"] == [] and g["published_at"] is None
    assert navgraph.validate(g["draft"])


def test_room_crud_and_duplicate_name(client):
    r = add_room(client)
    assert r.status_code == 201
    rid = r.json()["id"]
    assert add_room(client).status_code == 409
    assert (
        client.patch(f"/api/areas/floor10/rooms/{rid}", json={"name": "Lab A"}).status_code == 200
    )
    assert client.get("/api/areas/floor10/graph").json()["rooms"][0]["name"] == "Lab A"
    assert client.delete(f"/api/areas/floor10/rooms/{rid}").status_code == 204
    assert client.get("/api/areas/floor10/graph").json()["rooms"] == []


def test_writes_need_admin(client, monkeypatch):
    as_guest(client, monkeypatch)
    assert add_room(client).status_code == 403
    edit = {"kind": "remove_edge", "a": [0, 0], "b": [6, 0]}
    assert client.post("/api/areas/floor10/edits", json=edit).status_code == 403
    assert client.post("/api/areas/floor10/publish-graph", json={}).status_code == 403
    g = client.get("/api/areas/floor10/graph").json()
    assert g["rooms"] == [] and g["edits"] == []


def test_cross_site_form_writes_nothing(client):
    # Formulir lintas situs (cookie Access ikut terkirim) tidak boleh menulis apa pun: body bukan
    # JSON ditolak validasi (422), publish tanpa body JSON ditolak penjaga tipe isi (415).
    form = client.post("/api/areas/floor10/rooms", data={"name": "Lab", "x": "1", "y": "0"})
    plain = client.post(
        "/api/areas/floor10/rooms",
        content='{"name": "Lab", "x": 1, "y": 0}',
        headers={"Content-Type": "text/plain"},
    )
    publish = client.post("/api/areas/floor10/publish-graph", data={"x": "1"})
    assert form.status_code in (415, 422) and plain.status_code in (415, 422)
    assert publish.status_code == 415
    assert client.get("/api/areas/floor10/graph").json()["rooms"] == []


def test_edits_are_stored_and_bad_kinds_rejected(client):
    ok = client.post(
        "/api/areas/floor10/edits", json={"kind": "add_edge", "a": [0, 0], "b": [0, 3]}
    )
    assert ok.status_code == 201
    bad = client.post(
        "/api/areas/floor10/edits", json={"kind": "teleport", "a": [0, 0], "b": [1, 1]}
    )
    assert bad.status_code == 422
    eid = ok.json()["id"]
    assert client.get("/api/areas/floor10/graph").json()["edits"][0]["id"] == eid
    assert client.delete(f"/api/areas/floor10/edits/{eid}").status_code == 204


def test_route_uses_the_draft_graph(client):
    rid = add_room(client).json()["id"]
    r = client.post("/api/areas/floor10/route", json={"from": [0.5, 0.5], "room_id": rid}).json()
    assert r["points"][0] == [0.5, 0.5]
    assert r["nodes"][-1] == f"R{rid}"
    assert r["length_m"] > 0


def test_publish_then_navgraph_serves_it(client):
    add_room(client)
    r = client.post("/api/areas/floor10/publish-graph", json={})
    assert r.status_code == 200
    served = client.get("/navgraph").json()["graph"]
    assert {"node": served["targets"][0]["node"], "name": "Lab"} in served["targets"]
    assert client.get("/api/areas/floor10/graph").json()["published_at"] is not None


def test_publish_without_alignment_is_refused(client):
    client.app.state.localizer = fake_localizer(camera_path(), align=None)
    area_api.clear_cache()
    assert client.post("/api/areas/floor10/publish-graph", json={}).status_code == 409
    assert client.get("/api/areas/floor10/graph").status_code == 409


def test_publish_with_no_route_is_refused(client):
    client.app.state.localizer = fake_localizer([])
    area_api.clear_cache()
    r = client.post("/api/areas/floor10/publish-graph", json={})
    assert r.status_code == 409
    assert client.get("/navgraph").status_code == 404


def test_other_area_is_409(client):
    r = client.get("/api/areas/lain/graph")
    assert r.status_code == 409 and "not served" in r.json()["detail"]


def test_plan_returns_meta_and_trajectory(client):
    meta = client.get("/api/areas/floor10/plan").json()
    assert {"origin_x", "origin_y", "res_m", "width", "height"} <= meta.keys()
    assert len(meta["trajectory"]) == len(camera_path())
    png = client.get("/api/areas/floor10/plan.png")
    assert png.headers["content-type"] == "image/png" and png.content[1:4] == b"PNG"


def test_photo_returns_the_nearest_frame(client):
    thumbs = client.map_dir / "thumbs"
    thumbs.mkdir(parents=True)
    (thumbs / "job1-v0-x_00000.jpg").write_bytes(b"first")
    (thumbs / "job1-v0-x_00100.jpg").write_bytes(b"last")
    r = client.get("/api/areas/floor10/photo", params={"x": 6.0, "y": 4.0})
    assert r.status_code == 200 and r.content == b"last"
    assert abs(float(r.headers["x-heading-deg"])) < 1e-6


def test_photo_without_thumbs_is_404(client):
    r = client.get("/api/areas/floor10/photo", params={"x": 0, "y": 0})
    assert r.status_code == 404 and "photo" in r.json()["detail"]


def test_cloud_glb_is_served(client):
    r = client.get("/api/areas/floor10/cloud.glb")
    assert r.status_code == 200 and r.content[:4] == b"glTF"
