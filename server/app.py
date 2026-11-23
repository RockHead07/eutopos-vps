"""Layanan lokalisasi eutopos: POST /localize, GET /health, dan GET /navgraph.

Peta yang dimuat:
    - Kalau DATABASE_URL ada: versi peta aktif area EUTOPOS_AREA (bawaan "demo") dari
      PostgreSQL. Belum ada versi aktif = layanan tetap menyala, /localize menjawab 503
      (lihat server/manage.py).
    - Kalau tidak: folder EUTOPOS_MAP_DIR (untuk pengembangan lokal tanpa database).

Konfigurasi lain lewat variabel lingkungan:
    EUTOPOS_MAX_KP           batas keypoint ALIKED, sama dengan peta (bawaan 1024)
    EUTOPOS_RESIZE           resolusi ALIKED, sama dengan peta (bawaan 1024)
    EUTOPOS_GLOBAL_RESIZE    resolusi MegaLoc (bawaan 512)
    EUTOPOS_K                jumlah kandidat foto peta (bawaan 5)
    EUTOPOS_DEVICE           cpu atau cuda (bawaan cpu: angka latensi untuk klaim diukur tanpa GPU)
    EUTOPOS_THREADS          batas thread torch, 0 = bawaan (bawaan 0)
    EUTOPOS_MIN_INLIERS      di bawah ini status "failed" (bawaan 50)
    CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD   autentikasi /api/* (server/auth.py)
    EUTOPOS_MAPS_ROOT        folder akar peta untuk navgraph.json per area (bawaan /maps)

Menjalankan tanpa database:
    set EUTOPOS_MAP_DIR=outputs\\demo
    fastapi dev
Dengan database: deploy/README.md.
"""

import logging
import os
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import torch
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session

from server import (
    active_map,
    app_tokens,
    area_api,
    buildings_api,
    calibration_api,
    candidate_map,
    localize_log,
    maps_api,
    navgraph,
    uploads,
)
from server.alignment import DbAlign
from server.contract import CONTRACT_VERSION
from server.db import DB, active_version, engine_from_env
from server.localizer import Localizer
from server.photo import decode_upright, exif_camera, pinhole

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _sweep_candidates(state, stop: threading.Event) -> None:
    while not stop.wait(candidate_map.SWEEP_S):
        state.candidates.sweep()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if threads := int(os.environ.get("EUTOPOS_THREADS", 0)):
        torch.set_num_threads(threads)
    st = app.state
    st.area_id = st.map_version = st.localizer = st.reload_error = None
    st.candidates = None
    st.reloading = False
    # ponytail: satu lokalisasi dalam satu waktu. Model torch dipakai bersama dan server kecil
    # (2 vCPU). Kalau antrean permintaan jadi masalah, jalankan beberapa proses pekerja.
    st.lock = threading.Lock()
    stop = None
    if os.environ.get("DATABASE_URL"):
        engine = engine_from_env()
        stop = threading.Event()
        st.candidates = candidate_map.CandidateCache(engine, loader=active_map.load_localizer)
        threading.Thread(target=_sweep_candidates, args=(st, stop), daemon=True).start()
        with Session(engine) as s:
            v = active_version(s, active_map.serving_area())
        if v:
            try:
                st.localizer = active_map.load_localizer(
                    Path(v.path), align_source=DbAlign(engine, v.id).get
                )
                st.area_id, st.map_version = v.area_id, v.version
            except Exception as e:
                # Tetap menyala, /localize 503: dashboard di proses ini dipakai untuk menerbitkan
                # versi lain. Tanpa ini api restart berulang dan dashboard ikut mati.
                logging.getLogger("eutopos").exception("gagal memuat peta aktif")
                st.reload_error = f"version {v.version} failed to load at startup ({e})"
        if active_map.auto_publish_enabled():
            publisher = threading.Thread(
                target=active_map.publish_loop, args=(st, engine, stop), daemon=True
            )
            publisher.start()
    else:
        st.localizer = active_map.load_localizer(Path(os.environ["EUTOPOS_MAP_DIR"]))
    try:
        yield
    finally:
        if stop is not None:
            stop.set()


def _restrict_app_bearer(request: Request) -> None:
    if request.scope.get("endpoint") in (uploads.create, uploads.get, candidate_localize):
        return
    if any(app_tokens.has_app_bearer(value) for value in request.headers.getlist("authorization")):
        raise HTTPException(401, "app token is not allowed on this route")


app = FastAPI(title="eutopos-vps", lifespan=lifespan, dependencies=[Depends(_restrict_app_bearer)])
app.include_router(app_tokens.router)
app.include_router(buildings_api.router)
app.include_router(uploads.router)
app.include_router(maps_api.router)
app.include_router(navgraph.router)
app.include_router(area_api.router)
app.include_router(calibration_api.router)
app.include_router(localize_log.router)


class Pose(BaseModel):
    position: list[float]
    rotation_xyzw: list[float]  # rotasi kamera terhadap dunia (world_from_cam)


class LocalizeResponse(BaseModel):
    contract_version: int = CONTRACT_VERSION
    status: Literal["ok", "failed"]
    inliers: int
    correspondences: int
    intrinsics_source: Literal["client", "map", "exif"]
    pose_model: Pose | None  # kerangka model SfM, tanpa skala meter
    pose_building: Pose | None  # kerangka gedung (meter), kalau peta sudah diselaraskan
    area_id: str | None  # None kalau layanan berjalan tanpa database
    map_version: int | None
    t_s: dict[str, float]


class HealthResponse(BaseModel):
    status: Literal["ok", "no_map"]
    area_id: str | None
    map_version: int | None
    map_images: int
    device: str | None
    aligned: bool


@app.get("/health")
def health(request: Request) -> HealthResponse:
    st = request.app.state
    loc: Localizer | None = st.localizer
    return HealthResponse(
        status="ok" if loc else "no_map",
        area_id=st.area_id,
        map_version=st.map_version,
        map_images=len(loc.db_names) if loc else 0,
        device=str(loc.dev) if loc else None,
        aligned=bool(loc and loc.align is not None),
    )


@app.post("/localize")
def localize(
    request: Request,
    image: Annotated[UploadFile, File(description="Foto JPEG atau PNG")],
    fx: Annotated[float | None, Form(gt=0)] = None,
    fy: Annotated[float | None, Form(gt=0)] = None,
    cx: Annotated[float | None, Form(gt=0)] = None,
    cy: Annotated[float | None, Form(gt=0)] = None,
) -> LocalizeResponse:
    """Intrinsik (fx, fy, cx, cy) opsional, untuk foto yang SUDAH tegak. Kalau tidak dikirim,
    dipakai intrinsik peta (resolusi sama) atau taksiran dari EXIF."""
    st = request.app.state
    entry = {"area_id": st.area_id, "map_version": st.map_version}
    return _logged_localize(entry, lambda: _localize(request, image, fx, fy, cx, cy, entry))


@app.post("/versions/{version_id}/localize")
def candidate_localize(
    version_id: int,
    request: Request,
    image: Annotated[UploadFile, File(description="Foto JPEG atau PNG")],
    user: app_tokens.CaptureUser,
    s: DB,
    fx: Annotated[float | None, Form(gt=0)] = None,
    fy: Annotated[float | None, Form(gt=0)] = None,
    cx: Annotated[float | None, Form(gt=0)] = None,
    cy: Annotated[float | None, Form(gt=0)] = None,
) -> LocalizeResponse:
    entry = {"candidate": True}
    if app_tokens.is_app_identity(user):
        logging.getLogger("eutopos").info("candidate localization requested by %s", user)
    return _logged_localize(
        entry, lambda: _candidate_pose(request, s, version_id, image, fx, fy, cx, cy, entry)
    )


def _logged_localize(
    entry: dict, localize_photo: Callable[[], LocalizeResponse]
) -> LocalizeResponse:
    t0 = time.perf_counter()
    try:
        resp = localize_photo()
    except HTTPException as e:
        entry.update(result="rejected", http_status=e.status_code, reason=str(e.detail))
        raise
    except Exception:
        entry.update(result="error", http_status=500)
        raise
    else:
        entry.update(
            result=resp.status,
            http_status=200,
            inliers=resp.inliers,
            correspondences=resp.correspondences,
            intrinsics_source=resp.intrinsics_source,
            t_s=resp.t_s,
        )
        return resp
    finally:
        entry["wall_s"] = round(time.perf_counter() - t0, 3)
        localize_log.record(entry)


def _localize(
    request: Request,
    image: UploadFile,
    fx: float | None,
    fy: float | None,
    cx: float | None,
    cy: float | None,
    entry: dict,
) -> LocalizeResponse:
    rgb, data, given = _read_photo(image, fx, fy, cx, cy, entry)
    st = request.app.state
    with st.lock:
        loc, area_id, map_version = st.localizer, st.area_id, st.map_version
    if loc is None:
        raise HTTPException(503, "no published map version for this area")
    entry.update(area_id=area_id, map_version=map_version)
    return _pose_response(loc, rgb, data, fx, fy, cx, cy, given, area_id, map_version, st.lock)


def _candidate_pose(request, session, version_id, image, fx, fy, cx, cy, entry) -> LocalizeResponse:
    st = request.app.state
    cache = getattr(st, "candidates", None)
    if cache is None:
        raise HTTPException(503, "candidate localization requires a database")
    rgb, data, given = _read_photo(image, fx, fy, cx, cy, entry)
    try:
        version = candidate_map.testable_version(session, version_id)
        area_id, map_version = version.area_id, version.version
        entry.update(area_id=area_id, map_version=map_version)
        with st.lock:
            served = (
                st.localizer if (area_id, map_version) == (st.area_id, st.map_version) else None
            )
        if served is not None:
            return _pose_response(
                served, rgb, data, fx, fy, cx, cy, given, area_id, map_version, st.lock
            )

        # Pemuatan hanya memakai kunci cache. Inferensi mengambil st.lock dari dalam kunci cache.
        with cache.use(version_id) as (loc, area_id, map_version):
            entry.update(area_id=area_id, map_version=map_version)
            try:
                return _pose_response(
                    loc, rgb, data, fx, fy, cx, cy, given, area_id, map_version, st.lock
                )
            finally:
                del loc
    except candidate_map.CandidateUnavailable as e:
        raise HTTPException(e.status, str(e)) from e


def _read_photo(
    image: UploadFile,
    fx: float | None,
    fy: float | None,
    cx: float | None,
    cy: float | None,
    entry: dict,
) -> tuple[np.ndarray, bytes, list[bool]]:
    data = image.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"photo larger than {MAX_UPLOAD_BYTES // 2**20} MB")
    given = [v is not None for v in (fx, fy, cx, cy)]
    if any(given) and not all(given):
        raise HTTPException(422, "send all of fx, fy, cx, cy or none of them")
    try:
        rgb = decode_upright(data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    entry["image_h"], entry["image_w"] = rgb.shape[:2]
    return rgb, data, given


def _pose_response(
    loc, rgb, data, fx, fy, cx, cy, given, area_id, map_version, lock
) -> LocalizeResponse:
    h, w = rgb.shape[:2]
    if all(given):
        camera, source = pinhole(fx, fy, cx, cy, w, h), "client"
    elif loc.same_size_as_map(w, h):
        camera, source = loc.map_camera, "map"
    else:
        camera, source = exif_camera(data, w, h), "exif"

    with lock:
        r = loc.localize(rgb, camera)

    pose_model = pose_building = None
    if r.ok:
        world_from_cam = r.cam_from_world.inverse()
        pose_model = Pose(
            position=r.center_model, rotation_xyzw=world_from_cam.rotation.quat.tolist()
        )
        if building := loc.to_building(r.cam_from_world):
            pose_building = Pose(position=building[0], rotation_xyzw=building[1])
    return LocalizeResponse(
        status="ok" if r.ok else "failed",
        inliers=r.inliers,
        correspondences=r.correspondences,
        intrinsics_source=source,
        pose_model=pose_model,
        pose_building=pose_building,
        area_id=area_id,
        map_version=map_version,
        t_s={k: round(v, 3) for k, v in r.t.items()},
    )


WEB_DIR = Path(__file__).resolve().parents[1] / "web" / "out"


def mount_web(app: FastAPI, directory: Path) -> bool:
    """Dashboard hasil next build (static export). Dipasang terakhir supaya rute API menang."""
    if not directory.is_dir():
        return False
    app.mount("/", StaticFiles(directory=directory, html=True), name="web")
    return True


mount_web(app, WEB_DIR)
