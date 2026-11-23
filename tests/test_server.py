"""Uji layanan lokalisasi.

Uji rotasi EXIF selalu jalan. Uji layanan penuh butuh peta dan bobot model, jadi hanya jalan kalau
EUTOPOS_MAP_DIR (folder --out run.py dengan global-r512.h5) dan EUTOPOS_TEST_QUERY (foto uji yang
ada di peta itu) diset:
    set EUTOPOS_MAP_DIR=outputs\\bench-verify
    set EUTOPOS_TEST_QUERY=data\\demo\\query\\93341989_396310999.jpg
    pytest
"""

import io
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageOps

from server.photo import decode_upright


def _png_with_orientation(pixels: np.ndarray, orientation: int) -> bytes:
    im = Image.fromarray(pixels)
    exif = im.getexif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    im.save(buf, format="PNG", exif=exif.tobytes())  # PNG: tanpa kompresi lossy
    return buf.getvalue()


@pytest.mark.parametrize("orientation", range(1, 9))
def test_decode_upright_matches_pil(orientation):
    pixels = np.random.default_rng(orientation).integers(0, 255, (5, 7, 3), dtype=np.uint8)
    data = _png_with_orientation(pixels, orientation)
    expected = np.asarray(ImageOps.exif_transpose(Image.open(io.BytesIO(data))))
    np.testing.assert_array_equal(decode_upright(data), expected.astype(np.float32))


def test_decode_rejects_non_image():
    with pytest.raises(ValueError):
        decode_upright(b"bukan gambar")


MAP_DIR, QUERY = os.environ.get("EUTOPOS_MAP_DIR"), os.environ.get("EUTOPOS_TEST_QUERY")
needs_map = pytest.mark.skipif(not (MAP_DIR and QUERY), reason="EUTOPOS_MAP_DIR/TEST_QUERY kosong")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from server.app import app

    with TestClient(app) as c:
        yield c


def _post(client, data: bytes, **form):
    return client.post("/localize", files={"image": ("q.jpg", data, "image/jpeg")}, data=form)


@needs_map
def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["map_images"] > 0


@needs_map
def test_localize_known_query(client):
    body = _post(client, Path(QUERY).read_bytes()).json()
    assert body["status"] == "ok", body
    assert body["inliers"] >= 50
    # peta demo berisi foto berbagai ukuran (satu kamera per foto), jadi taksiran EXIF juga sah
    assert body["intrinsics_source"] in ("map", "exif")
    assert len(body["pose_model"]["position"]) == 3


@needs_map
def test_localize_portrait_query_is_uprighted(client):
    """Foto potret ponsel: piksel miring + EXIF 6. Tanpa ditegakkan, spike memberi pose salah."""
    with Image.open(QUERY) as im:
        raw = np.rot90(np.asarray(im), 1)  # EXIF 6 = tampilkan dengan putar 90 derajat searah jarum
        exif = im.getexif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(raw)).save(buf, "JPEG", exif=exif.tobytes(), quality=95)
    body = _post(client, buf.getvalue()).json()
    assert body["status"] == "ok", body
    assert body["inliers"] >= 50


@needs_map
def test_localize_noise_fails(client):
    noise = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noise).save(buf, "JPEG")
    body = _post(client, buf.getvalue()).json()
    assert body["status"] == "failed" and body["pose_model"] is None


@needs_map
def test_partial_intrinsics_rejected(client):
    assert _post(client, Path(QUERY).read_bytes(), fx="1000").status_code == 422


@needs_map
def test_non_image_rejected(client):
    assert _post(client, b"bukan gambar").status_code == 400


@pytest.fixture
def candidate_client(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace

    import pycolmap
    from fastapi.testclient import TestClient
    from sqlmodel import Session, SQLModel, create_engine

    from server import app_tokens, db, localize_log
    from server.app import app
    from server.candidate_map import CandidateCache
    from server.localizer import Result
    from tests.conftest import make_building

    class FakeLocalizer:
        def __init__(self, position):
            self.position = position
            self.db_names = ["mapping/test.jpg"]
            self.dev = "cpu"
            self.align = None

        def same_size_as_map(self, w, h):
            return False

        def localize(self, rgb, camera):
            position = [self.position, 0, 0]
            pose = pycolmap.Rigid3d(pycolmap.Rotation3d(), np.array([-self.position, 0, 0]))
            return Result(True, 80, 85, pose, position, {"total": 0.02})

        def to_building(self, cam_from_world):
            return None

    url = f"sqlite:///{tmp_path / 'candidate-api.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        building = make_building(session)
        for area in ["served", "candidate-area"]:
            session.add(db.Area(id=area, name=area, building_id=building.id))
        session.commit()
        for version_id, area, number, status in [
            (1, "served", 7, "published"),
            (2, "candidate-area", 4, "candidate"),
            (3, "candidate-area", 5, "candidate"),
        ]:
            path = tmp_path / str(version_id)
            path.mkdir()
            session.add(
                db.MapVersion(
                    id=version_id, area_id=area, version=number, status=status, path=str(path)
                )
            )
        session.commit()
        raw = app_tokens.create_token(session, "rekam-1", "admin@example.test")

    calls = []

    def loader(path, *, align_source):
        calls.append(path.name)
        return FakeLocalizer(int(path.name))

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    served = FakeLocalizer(1)
    for key, value in {
        "localizer": served,
        "area_id": "served",
        "map_version": 7,
        "lock": threading.Lock(),
        "candidates": CandidateCache(engine, loader=loader),
    }.items():
        monkeypatch.setattr(app.state, key, value, raising=False)
    png = _png_with_orientation(np.zeros((16, 16, 3), dtype=np.uint8), 1)
    try:
        yield SimpleNamespace(
            client=TestClient(app),
            api=app,
            headers={"Authorization": f"Bearer {raw}"},
            files={"image": ("test.png", png, "image/png")},
            served=served,
            calls=calls,
            engine=engine,
        )
    finally:
        db._engine(url).dispose()
        localize_log._engine(url).dispose()
        engine.dispose()


def test_candidate_localize_does_not_touch_served_map(candidate_client):
    test = candidate_client
    before = test.client.get("/health").json()
    response = test.client.post("/versions/2/localize", files=test.files, headers=test.headers)
    assert response.status_code == 200
    body = response.json()
    assert (body["area_id"], body["map_version"]) == ("candidate-area", 4)
    assert body["pose_model"]["position"] == [2, 0, 0]
    assert body["pose_building"] is None
    assert test.api.state.localizer is test.served
    assert test.client.get("/health").json() == before
    assert test.calls == ["2"]


def test_candidate_localize_uses_served_localizer_for_served_version(candidate_client):
    test = candidate_client
    response = test.client.post("/versions/1/localize", files=test.files, headers=test.headers)
    assert response.status_code == 200
    assert response.json()["pose_model"]["position"] == [1, 0, 0]
    assert test.calls == []


def test_candidate_localize_logs_candidate_flag(candidate_client):
    from sqlmodel import Session, select

    from server.db import LocalizeRequest

    test = candidate_client
    assert (
        test.client.post("/versions/2/localize", files=test.files, headers=test.headers).status_code
        == 200
    )
    assert test.client.post("/localize", files=test.files).status_code == 200
    with Session(test.engine) as session:
        candidate, normal = session.exec(select(LocalizeRequest).order_by(LocalizeRequest.id)).all()
    assert candidate.candidate is True
    assert (candidate.area_id, candidate.map_version) == ("candidate-area", 4)
    assert normal.candidate is False
    assert (normal.area_id, normal.map_version) == ("served", 7)


def test_candidate_localize_requires_identity(candidate_client, monkeypatch):
    test = candidate_client
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "https://team.invalid")
    monkeypatch.setenv("CF_ACCESS_AUD", "synthetic")
    assert test.client.post("/versions/2/localize", files=test.files).status_code == 401
    assert test.calls == []


def test_concurrent_candidate_requests_return_their_own_poses(candidate_client):
    from concurrent.futures import ThreadPoolExecutor

    test = candidate_client

    def request(version_id):
        response = test.client.post(
            f"/versions/{version_id}/localize", files=test.files, headers=test.headers
        )
        assert response.status_code == 200
        return response.json()["pose_model"]["position"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(request, [2, 3])) == [[2, 0, 0], [3, 0, 0]]
    assert test.api.state.localizer is test.served


def test_candidate_load_does_not_block_served_localize(candidate_client, monkeypatch):
    import threading

    test = candidate_client
    cache = test.api.state.candidates
    load = cache.loader
    entered = threading.Event()
    release = threading.Event()
    responses = {}

    def blocked_loader(path, *, align_source):
        entered.set()
        assert release.wait(timeout=10), "test did not release candidate loader"
        return load(path, align_source=align_source)

    def post(path, **kwargs):
        responses[path] = test.client.post(path, files=test.files, **kwargs)

    monkeypatch.setattr(cache, "loader", blocked_loader)
    candidate_path = "/versions/2/localize"
    served_path = "/localize"
    candidate = threading.Thread(
        target=post, args=(candidate_path,), kwargs={"headers": test.headers}, daemon=True
    )
    served = threading.Thread(target=post, args=(served_path,), daemon=True)
    candidate.start()
    try:
        assert entered.wait(timeout=5), "candidate loader did not start"
        served.start()
        served.join(timeout=2)
        assert not served.is_alive(), "/localize waited for the candidate loader"
        assert responses[served_path].status_code == 200
    finally:
        release.set()
        candidate.join(timeout=5)
        if served.ident is not None:
            served.join(timeout=5)

    assert not candidate.is_alive(), "candidate request did not finish after release"
    assert responses[candidate_path].status_code == 200
