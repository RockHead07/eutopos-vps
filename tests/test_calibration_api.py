"""API kalibrasi: set, impor, hitung, terapkan, riwayat, batalkan (roadmap M1-3b)."""

import json
import threading

import numpy as np
import pycolmap
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from server import alignment, auth, calibration_api, content_migration, uploads
from server.db import Alignment, Area, CalibrationSet, MapVersion, PublishedGraph, Room

JSON = {"content-type": "application/json"}


def truth():
    """Model = truth * dunia (skala 4,0), jadi meter_from_model punya skala 0,25."""
    q = np.array([0.1, 0.7, 0.2, 0.68])
    return pycolmap.Sim3d(4.0, pycolmap.Rotation3d(q / np.linalg.norm(q)), np.array([3.0, -1, 2]))


def pts(n=8, test=()):
    out = [
        {"point_id": f"P{i:02d}", "x_m": i * 1.5, "y_m": 0.3 if i % 2 else 1.7, "role": "reference"}
        for i in range(n)
    ]
    out += [{"point_id": t, "x_m": 4.0, "y_m": 1.0, "role": "test"} for t in test]
    return out


def csv_for(points, inliers=100, skip=(), shift=None, sim=None):
    shift = shift or {}
    sim = sim or truth()
    lines = ["query,ok,inliers,center_xyz_model"]
    for p in points:
        if p["point_id"] in skip:
            continue
        dx = shift.get(p["point_id"], 0.0)
        c = (sim * np.array([[p["x_m"] + dx, p["y_m"], 1.3]]))[0].tolist()
        lines.append(f'query/{p["point_id"]}_a.jpg,True,{inliers},"{json.dumps(c)}"')
    return "\n".join(lines) + "\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'c.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Area(id="floor10", name="Lantai 10"))
        for n, status in ((1, "published"), (2, "candidate")):
            s.add(MapVersion(area_id="floor10", version=n, path=f"/maps/job-{n}", status=status))
        s.commit()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    app = FastAPI()
    app.include_router(uploads.router)
    app.include_router(calibration_api.router)
    st = app.state
    st.localizer, st.area_id, st.map_version, st.lock = None, "floor10", 1, threading.Lock()
    with TestClient(app) as c:
        c.engine = engine
        yield c


def served(client, version=1):
    """Yang dibaca Localizer untuk versi itu (alignment.DbAlign), bukan berkas di /maps."""
    return alignment.DbAlign(client.engine, version).get()


def make_set(client, version_id=1, points=None):
    r = client.post(
        f"/api/versions/{version_id}/calibration",
        json={"note": "uji", "points": points or pts(test=["T1"])},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def import_csv(client, set_id, text):
    return client.post(f"/api/calibration/{set_id}/observations/import", json={"csv": text})


def ready_set(client, version_id=1, **csv_kw):
    points = pts(test=["T1"])
    sid = make_set(client, version_id, points)
    assert import_csv(client, sid, csv_for(points, **csv_kw)).status_code == 200
    return sid


def apply(client, sid, base=None):
    return client.post(f"/api/calibration/{sid}/apply", json={"base_alignment_id": base})


def history(client, version_id=1):
    return client.get(f"/api/versions/{version_id}/alignments").json()


def test_create_set_validates_input(client, monkeypatch):
    url = "/api/versions/1/calibration"
    good = pts()
    dup = [*good, dict(good[0])]
    assert client.post(url, json={"points": dup}).status_code == 422
    assert client.post(url, json={"points": [{**good[0], "role": "x"}]}).status_code == 422
    assert client.post(url, json={"points": []}).status_code == 422
    nan = '{"points": [{"point_id": "A", "x_m": NaN, "y_m": 0, "role": "reference"}]}'
    r = client.post(url, content=nan, headers=JSON)
    assert r.status_code == 422, r.text
    inf = nan.replace("NaN", "Infinity")
    assert client.post(url, content=inf, headers=JSON).status_code == 422
    long_id = [{**good[0], "point_id": "x" * 41}]
    assert client.post(url, json={"points": long_id}).status_code == 422
    assert client.post("/api/versions/99/calibration", json={"points": good}).status_code == 404
    # sebuah model body menolak non-JSON lebih dulu (422) sebelum pemeriksaan 415; keduanya menolak
    body = json.dumps({"points": good})
    plain = client.post(url, content=body, headers={"content-type": "text/plain"})
    assert plain.status_code in (415, 422)
    with Session(client.engine) as s:
        assert s.exec(select(CalibrationSet)).all() == []
    monkeypatch.setenv("EUTOPOS_ADMINS", "boss@x.id")
    client.app.dependency_overrides[auth.current_user] = lambda: "tamu@x.id"
    assert client.post(url, json={"points": good}).status_code == 403


def test_import_counts_accepted_and_rejected(client):
    sid = make_set(client)
    text = (
        "query,ok,inliers,center_xyz_model\n"
        'query/P00_a.jpg,True,120,"[1, 2, 3]"\n'
        'query/P01_a.jpg,True,90,"[1, 2, 3]"\n'
        'query/P02_a.jpg,True,40,"[1, 2, 3]"\n'
        'query/ZZ_a.jpg,True,150,"[1, 2, 3]"\n'
        "query/P03_a.jpg,False,0,\n"
    )
    r = import_csv(client, sid, text)
    assert r.json() == {"accepted": 2, "rejected_low_inliers": ["P02"], "unknown_points": ["ZZ"]}
    bad = import_csv(client, sid, "query,ok\nq/P00_a.jpg,True\n")
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "bad_input"
    assert import_csv(client, 999, text).status_code == 404


def test_fit_has_no_side_effects(client):
    sid = ready_set(client)
    r = client.post(f"/api/calibration/{sid}/fit", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert abs(body["stats"]["scale"] - 0.25) < 1e-6
    assert body["align"]["holdout_points"] == ["T1"] and len(body["rows"]) == 9
    assert history(client) == []
    assert served(client) is None


def test_apply_records_a_valid_alignment_and_history(client):
    sid = ready_set(client)
    r = apply(client, sid)
    assert r.status_code == 200, r.text
    first = r.json()["alignment_id"]
    alignment.validate_align(served(client))
    h = history(client)
    assert [(a["id"], a["status"], a["source"]) for a in h] == [(first, "applied", "fit")]
    assert abs(h[0]["scale"] - 0.25) < 1e-6 and h[0]["stats"]["reference_points"] == 8
    second = apply(client, sid, base=first).json()["alignment_id"]
    assert [(a["id"], a["status"]) for a in history(client)] == [
        (second, "applied"),
        (first, "superseded"),
    ]


def test_apply_with_a_stale_base_is_a_conflict(client):
    sid = ready_set(client)
    first = apply(client, sid).json()["alignment_id"]
    before = served(client)
    assert apply(client, sid, base=None).status_code == 409
    assert apply(client, sid, base=first + 100).status_code == 409
    assert served(client) == before
    assert [a["status"] for a in history(client)] == ["applied"]


def test_a_failed_content_move_leaves_alignment_and_content_untouched(client, monkeypatch):
    first = apply(client, ready_set(client)).json()["alignment_id"]
    add_room(client)
    before = served(client)
    other = ready_set(client, sim=other_truth())

    def boom(*a, **k):
        raise RuntimeError("pemindahan gagal")

    monkeypatch.setattr(content_migration, "migrate", boom)
    with pytest.raises(RuntimeError):
        apply(client, other, base=first)
    assert served(client) == before
    assert [(a["id"], a["status"]) for a in history(client)] == [(first, "applied")]
    assert room_xy(client) == (3.0, 1.0)


def test_a_failed_commit_leaves_the_alignment_untouched(client, monkeypatch):
    first = apply(client, ready_set(client)).json()["alignment_id"]
    before = served(client)
    other = ready_set(client, sim=other_truth())

    def boom(self):
        raise RuntimeError("commit gagal")

    monkeypatch.setattr(Session, "commit", boom)
    with pytest.raises(RuntimeError):
        apply(client, other, base=first)
    monkeypatch.undo()
    assert served(client) == before


def test_revert_restores_the_previous_params(client):
    sid = ready_set(client)
    first = apply(client, sid).json()["alignment_id"]
    first_params = served(client)
    shifted = ready_set(client, shift={"P03": 40.0})
    second = apply(client, shifted, base=first).json()["alignment_id"]
    assert served(client) != first_params
    r = client.post(f"/api/alignments/{first}/revert", json={"base_alignment_id": second})
    assert r.status_code == 200, r.text
    assert served(client) == first_params
    h = history(client)
    assert (h[0]["source"], h[0]["status"]) == ("revert", "applied")
    assert [a["status"] for a in h[1:]] == ["superseded", "superseded"]
    stale = client.post(f"/api/alignments/{first}/revert", json={"base_alignment_id": second})
    assert stale.status_code == 409
    current = h[0]["id"]
    same = client.post(f"/api/alignments/{current}/revert", json={"base_alignment_id": current})
    assert same.status_code == 409  # sudah berlaku
    assert (
        client.post("/api/alignments/999/revert", json={"base_alignment_id": 1}).status_code == 404
    )


def test_apply_for_a_non_serving_version_is_kept_for_when_it_is_published(client):
    sid = ready_set(client, version_id=2)  # versi 2: kandidat, bukan yang dilayani
    r = apply(client, sid)  # app.state.localizer = None: menyentuhnya akan gagal
    assert r.status_code == 200, r.text
    alignment.validate_align(served(client, 2))
    assert served(client, 1) is None


def test_fit_error_codes_are_422_with_a_code(client):
    points = pts(3)
    sid = make_set(client, points=points)
    import_csv(client, sid, csv_for(points))
    r = client.post(f"/api/calibration/{sid}/fit", json={})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_few_reference"
    assert apply(client, sid).status_code == 422
    assert history(client) == []


def test_unknown_set_and_version_are_404(client):
    assert client.post("/api/calibration/999/fit", json={}).status_code == 404
    assert apply(client, 999).status_code == 404
    assert client.get("/api/versions/999/alignments").status_code == 404


def test_writes_need_json_and_admin(client, monkeypatch):
    sid = ready_set(client)
    plain = {"content-type": "text/plain"}
    assert (
        client.post(f"/api/calibration/{sid}/fit", content="{}", headers=plain).status_code == 415
    )
    monkeypatch.setenv("EUTOPOS_ADMINS", "boss@x.id")
    client.app.dependency_overrides[auth.current_user] = lambda: "tamu@x.id"
    assert apply(client, sid).status_code == 403
    assert client.post(f"/api/calibration/{sid}/fit", json={}).status_code == 403
    assert client.get("/api/versions/1/alignments").status_code == 200


def level_shift(scale=1.2, deg=30.0, t=(2.0, -1.0)):
    """Perubahan di G yang menjaga bidang z 1,3: skala, putar di sekitar z, geser."""
    th = np.radians(deg)
    rz = pycolmap.Rotation3d(np.array([0, 0, np.sin(th / 2), np.cos(th / 2)]))
    c = np.array([0.0, 0.0, 1.3])
    return pycolmap.Sim3d(scale, rz, c + np.array([*t, 0.0]) - scale * (rz.matrix() @ c))


def other_truth():
    """Dunia ke model yang membuat penyelarasan kedua = level_shift() setelah yang pertama."""
    return truth() * level_shift().inverse()


def room_xy(client, name="Lab"):
    with Session(client.engine) as s:
        r = s.exec(select(Room).where(Room.name == name)).one()
        return r.x, r.y


def add_room(client, area="floor10", name="Lab", x=3.0, y=1.0):
    with Session(client.engine) as s:
        s.add(Room(area_id=area, name=name, x=x, y=y, created_by="a"))
        s.commit()


def test_apply_moves_rooms_of_the_active_version_only(client):
    # versi 1 (terbit): ruangan ikut bergeser ke tempat fisik yang sama
    first = apply(client, ready_set(client)).json()["alignment_id"]
    add_room(client)
    other = ready_set(client, sim=other_truth())
    r = apply(client, other, base=first)
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == {"rooms": 1, "strokes": 0, "edits": 0}
    assert r.json()["republish_required"] is False
    old = json.loads(history_params(client, first))["meter_from_model"]
    new = served(client)["meter_from_model"]
    move = content_migration.plane_transform(old, new, 1.3)
    assert room_xy(client) == pytest.approx(move(3.0, 1.0), abs=1e-6)
    # tempat fisik yang sama, dihitung tanpa kode migrasi: titik G lama lewat level_shift
    expect = (level_shift() * np.array([[3.0, 1.0, 1.3]]))[0]
    assert room_xy(client) == pytest.approx(tuple(expect[:2]), abs=1e-6)


def history_params(client, alignment_id):
    with Session(client.engine) as s:
        return json.dumps(s.get(Alignment, alignment_id).params)


def test_apply_for_a_candidate_version_does_not_touch_rooms(client):
    first = apply(client, ready_set(client, version_id=2)).json()["alignment_id"]
    add_room(client)
    r = apply(client, ready_set(client, version_id=2, sim=other_truth()), base=first)
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == {"rooms": 0, "strokes": 0, "edits": 0}
    assert room_xy(client) == (3.0, 1.0)


def test_republish_is_flagged_when_a_graph_exists(client):
    first = apply(client, ready_set(client)).json()["alignment_id"]
    with Session(client.engine) as s:
        s.add(PublishedGraph(area_id="floor10", graph={}, published_by="a"))
        s.commit()
    r = apply(client, ready_set(client, sim=other_truth()), base=first)
    assert r.json()["republish_required"] is True


def test_revert_moves_content_back(client):
    first = apply(client, ready_set(client)).json()["alignment_id"]
    add_room(client)
    second = apply(client, ready_set(client, sim=other_truth()), base=first).json()["alignment_id"]
    assert room_xy(client) != pytest.approx((3.0, 1.0), abs=0.1)
    client.post(f"/api/alignments/{first}/revert", json={"base_alignment_id": second})
    assert room_xy(client) == pytest.approx((3.0, 1.0), abs=1e-6)
