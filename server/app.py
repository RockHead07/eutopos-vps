"""Layanan lokalisasi eutopos: POST /localize dan GET /health.

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

Menjalankan tanpa database:
    set EUTOPOS_MAP_DIR=outputs\\demo
    fastapi dev
Dengan database: deploy/README.md.
"""

import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import torch
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlmodel import Session

from server import uploads
from server.db import active_version, engine_from_env
from server.localizer import MIN_INLIERS, Localizer
from server.photo import decode_upright, exif_camera, pinhole

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if threads := _env_int("EUTOPOS_THREADS", 0):
        torch.set_num_threads(threads)
    app.state.area_id = app.state.map_version = app.state.localizer = None
    if os.environ.get("DATABASE_URL"):
        with Session(engine_from_env()) as s:
            v = active_version(s, os.environ.get("EUTOPOS_AREA", "demo"))
        map_dir = Path(v.path) if v else None
        if v:
            app.state.area_id, app.state.map_version = v.area_id, v.version
    else:
        map_dir = Path(os.environ["EUTOPOS_MAP_DIR"])
    if map_dir is not None:
        app.state.localizer = _load_localizer(map_dir)
    # ponytail: satu lokalisasi dalam satu waktu. Model torch dipakai bersama dan server kecil
    # (2 vCPU). Kalau antrean permintaan jadi masalah, jalankan beberapa proses pekerja.
    app.state.lock = threading.Lock()
    yield


def _load_localizer(map_dir: Path) -> Localizer:
    return Localizer(
        map_dir,
        max_kp=_env_int("EUTOPOS_MAX_KP", 1024),
        resize=_env_int("EUTOPOS_RESIZE", 1024),
        global_resize=_env_int("EUTOPOS_GLOBAL_RESIZE", 512),
        k=_env_int("EUTOPOS_K", 5),
        device=os.environ.get("EUTOPOS_DEVICE", "cpu"),
        min_inliers=_env_int("EUTOPOS_MIN_INLIERS", MIN_INLIERS),
    )


app = FastAPI(title="eutopos-vps", lifespan=lifespan)
app.include_router(uploads.router)


class Pose(BaseModel):
    position: list[float]
    rotation_xyzw: list[float]  # rotasi kamera terhadap dunia (world_from_cam)


class LocalizeResponse(BaseModel):
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
    data = image.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"foto lebih dari {MAX_UPLOAD_BYTES // 2**20} MB")
    given = [v is not None for v in (fx, fy, cx, cy)]
    if any(given) and not all(given):
        raise HTTPException(422, "fx, fy, cx, cy dikirim semua atau tidak sama sekali")
    try:
        rgb = decode_upright(data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    loc: Localizer | None = request.app.state.localizer
    if loc is None:
        raise HTTPException(503, "belum ada versi peta aktif untuk area ini")
    h, w = rgb.shape[:2]
    if all(given):
        camera, source = pinhole(fx, fy, cx, cy, w, h), "client"
    elif loc.same_size_as_map(w, h):
        camera, source = loc.map_camera, "map"
    else:
        camera, source = exif_camera(data, w, h), "exif"

    with request.app.state.lock:
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
        area_id=request.app.state.area_id,
        map_version=request.app.state.map_version,
        t_s={k: round(v, 3) for k, v in r.t.items()},
    )
