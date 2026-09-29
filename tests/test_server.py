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
