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
    for name in ("localize_ok.json", "localize_failed.json", "navgraph_response.json"):
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
        s.add(Area(id="floor10", name="Lantai 10"))
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
