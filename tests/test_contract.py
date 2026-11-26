"""Kontrak /localize dan /navgraph berversi, dengan berkas contoh bersama (roadmap M1-8).

Berkas di tests/fixtures/ ditulis dari jawaban server sungguhan, bukan JSON buatan tangan, dan
eutopos-mobile menyalin berkas yang sama byte demi byte lalu mem-parse-nya di tesnya. Pelajaran
22 Oct 2026: tes aplikasi yang memakai JSON buatan sendiri meloloskan bug `frame` dan `units`.
Mengubah bentuk jawaban berarti mengubah berkas ini, dan itu terlihat di kedua repo.
"""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import pycolmap
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server import contract, navgraph
from server.db import Area, PublishedGraph
from server.localizer import Result

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_fixtures_carry_the_current_contract_version():
    for name in (
        "localize_ok.json",
        "localize_failed.json",
        "localize_multi_ok.json",
        "localize_multi_no_consensus.json",
        "navgraph_response.json",
    ):
        assert fixture(name)["contract_version"] == contract.CONTRACT_VERSION, name


class FakeLocalizer:
    def __init__(self, result):
        self.result = result

    def same_size_as_map(self, w, h):
        return False

    def localize(self, rgb, camera):
        return self.result

    def to_building(self, cam_from_world):
        return [1.5, 2.0, 1.3], [0.0, 0.0, 0.0, 1.0]


def localize(monkeypatch, result) -> dict:
    import io

    from PIL import Image

    from server.app import app

    monkeypatch.delenv("DATABASE_URL", raising=False)  # tanpa pencatatan permintaan
    st = app.state
    st.lock = threading.Lock()
    st.area_id, st.map_version = "floor10", 4
    st.localizer = FakeLocalizer(result)
    buf = io.BytesIO()
    Image.new("RGB", (64, 48)).save(buf, "PNG")
    form = {"fx": "100", "fy": "100", "cx": "32", "cy": "24"}
    r = TestClient(app).post(
        "/localize", files={"image": ("q.png", buf.getvalue(), "image/png")}, data=form
    )
    assert r.status_code == 200
    return r.json()


def test_localize_ok_matches_the_shared_fixture(monkeypatch):
    ok = Result(True, 120, 300, pycolmap.Rigid3d(), [0.5, 0.25, 0.1], {"prep": 0.01, "total": 0.9})
    assert localize(monkeypatch, ok) == fixture("localize_ok.json")


def test_localize_failed_matches_the_shared_fixture(monkeypatch):
    failed = Result(False, 7, 30, None, None, {"total": 0.2})
    assert localize(monkeypatch, failed) == fixture("localize_failed.json")


def _q_axis(axis, deg: float) -> list[float]:
    import math

    import numpy as np

    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    h = math.radians(deg) / 2.0
    s = math.sin(h)
    return [float(a[0] * s), float(a[1] * s), float(a[2] * s), float(math.cos(h))]


def localize_multi_response(monkeypatch, *, agreeing: bool) -> dict:
    import io

    import numpy as np
    from PIL import Image

    from server import align4dof
    from server import app as app_mod

    monkeypatch.delenv("DATABASE_URL", raising=False)
    true_yaw = 20.0
    true_t = np.array([1.0, 0.0, 3.0])
    # 3 frame sepakat dengan heading AR 0, 18, 35 deg (rentang 35 deg >= 20 -> view_diverse True)
    # + 1 frame pencilan (atau 4 frame menyebar jika agreeing=False)
    yaws_u = [0.0, 18.0, 35.0, 10.0]
    b_poses = []
    frames_meta = []
    for idx, yu in enumerate(yaws_u):
        yb = yu - true_yaw
        b_rot_g = (
            pycolmap.Rotation3d(np.array(_q_axis([0, 0, 1], -yb)))
            * pycolmap.Rotation3d(np.array(_q_axis([1, 0, 0], -90.0)))
        ).quat.tolist()
        true_b_pos = [float(idx), 0.0, 1.3]
        ar_pos = (align4dof.rot_y(true_yaw, align4dof.g_to_b(true_b_pos)) + true_t).tolist()
        ar_rot = _q_axis([0, 1, 0], yu)
        if agreeing:
            b_pos = [9.0, 0.0, 1.3] if idx == 3 else true_b_pos
        else:
            b_pos = [float(idx) * 10.0, 0.0, 1.3]
        inl = [110, 160, 130, 90][idx]
        b_poses.append((b_pos, b_rot_g, inl))
        frames_meta.append(
            {
                "fx": 100.0,
                "fy": 100.0,
                "cx": 32.0,
                "cy": 24.0,
                "ar_position": ar_pos,
                "ar_rotation": ar_rot,
            }
        )

    class FakeMultiLoc:
        def __init__(self):
            self.align = {"meter_from_model": {"scale": 1.0}}

        def same_size_as_map(self, w, h):
            return False

        def localize_batch(self, rgbs, cameras):
            clock["t"] += 0.42
            out = []
            for pos, rot, inl in b_poses:
                pose = pycolmap.Rigid3d(pycolmap.Rotation3d(np.array(rot)), np.array(pos)).inverse()
                out.append(
                    Result(
                        True,
                        inl,
                        inl + 40,
                        pose,
                        pos,
                        {"total": 0.1},
                        reprojection_error_px_median=1.25,
                        retrieval_top1=0.86,
                        ambiguous=False,
                    )
                )
            return out

        def to_building(self, cam_from_world):
            wfc = cam_from_world.inverse()
            return [round(v, 6) for v in wfc.translation.tolist()], [
                round(v, 6) for v in wfc.rotation.quat.tolist()
            ]

    st = app_mod.app.state
    st.lock = threading.Lock()
    st.area_id, st.map_version = "floor10", 4
    st.localizer = FakeMultiLoc()

    clock = {"t": 10.0}
    monkeypatch.setattr(app_mod.time, "perf_counter", lambda: clock["t"])

    buf = io.BytesIO()
    Image.new("RGB", (64, 48)).save(buf, "PNG")
    png = buf.getvalue()
    files = [(f"image_{i}", (f"f{i}.png", png, "image/png")) for i in range(4)]
    r = TestClient(app_mod.app).post(
        "/localize-multi", files=files, data={"frames": json.dumps(frames_meta)}
    )
    assert r.status_code == 200
    return r.json()


def test_localize_multi_ok_matches_the_shared_fixture(monkeypatch):
    body = localize_multi_response(monkeypatch, agreeing=True)
    assert body["status"] == "ok"
    assert body["frames_agreeing"] == 3 and body["frames_total"] == 4
    assert body["view_diverse"] is True
    assert body == fixture("localize_multi_ok.json")


def test_localize_multi_no_consensus_matches_the_shared_fixture(monkeypatch):
    body = localize_multi_response(monkeypatch, agreeing=False)
    assert body["status"] == "not_found" and body["reason"] == "no_consensus"
    assert body == fixture("localize_multi_no_consensus.json")


def navgraph_response(tmp_path, monkeypatch) -> dict:
    url = f"sqlite:///{tmp_path / 'c.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    graph = {
        "frame": "building",
        "units": "m",
        "nodes": [{"id": "P01", "x": 0.0, "y": 0.4}, {"id": "P02", "x": 1.5, "y": 1.6}],
        "edges": [["P01", "P02"]],
        "targets": [{"node": "P02", "name": "Pintu Lab"}],
    }
    walkable = json.loads((FIXTURES / "walkable_payload.json").read_text(encoding="utf-8"))
    with Session(engine) as s:
        from tests.conftest import make_building

        bld = make_building(s)
        s.add(Area(id="floor10", name="Lantai 10", building_id=bld.id))
        s.add(
            PublishedGraph(
                area_id="floor10",
                graph=graph,
                walkable=walkable,
                published_by="dev@local",
                published_at=datetime(2026, 10, 22, 6, 33, 0, tzinfo=UTC),
            )
        )
        s.commit()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_MAPS_ROOT", str(tmp_path))
    app = FastAPI()
    app.include_router(navgraph.router)
    app.state.area_id, app.state.map_version = "floor10", 4
    r = TestClient(app).get("/navgraph")
    assert r.status_code == 200
    return r.json()


def test_navgraph_matches_the_shared_fixture(tmp_path, monkeypatch):
    assert navgraph_response(tmp_path, monkeypatch) == fixture("navgraph_response.json")


def test_contract_version_is_a_positive_integer():
    assert isinstance(contract.CONTRACT_VERSION, int) and contract.CONTRACT_VERSION >= 1


@pytest.mark.parametrize("name", ["localize_ok.json", "localize_failed.json"])
def test_localize_fixtures_have_every_field_the_app_reads(name):
    # VpsResponses.ParseLocalize membaca bidang-bidang ini; menghapusnya memutus aplikasi lama.
    keys = {"status", "inliers", "area_id", "map_version", "t_s", "pose_building"}
    assert keys <= fixture(name).keys()
