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

import json
import logging
import math
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
    align4dof,
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
MULTI_MIN_FRAMES = 2
MULTI_MAX_FRAMES = 6


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
    if request.scope.get("endpoint") in (
        uploads.create,
        uploads.get,
        candidate_localize,
        buildings_api.list_buildings,
    ):
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


def _model_pose(center_model, world_from_cam) -> Pose:
    """Pose di kerangka model, dibulatkan 6 desimal seperti pose_building.

    Digit terakhir kuaternion pycolmap berbeda antarplatform (Windows vs Linux CI), jadi angka
    mentah membuat jawaban dan fixture kontrak tidak stabil.
    """
    return Pose(
        position=[round(float(v), 6) for v in center_model],
        rotation_xyzw=[round(float(v), 6) for v in world_from_cam.rotation.quat],
    )


class LocalizeResponse(BaseModel):
    contract_version: int = CONTRACT_VERSION
    status: Literal["ok", "failed"]
    inliers: int
    correspondences: int
    inlier_ratio: float | None = None
    reprojection_error_px_median: float | None = None
    retrieval_top1: float | None = None
    ambiguous: bool = False
    prior_used: bool = False
    outside_prior: bool = False
    deep_search: bool = False
    intrinsics_source: Literal["client", "map", "exif"]
    pose_model: Pose | None  # kerangka model SfM, tanpa skala meter
    pose_building: Pose | None  # kerangka gedung (meter), kalau peta sudah diselaraskan
    area_id: str | None  # None kalau layanan berjalan tanpa database
    map_version: int | None
    t_s: dict[str, float]


class Alignment4DofResponse(BaseModel):
    yaw_deg: float
    translation: list[float]


class MultiFrameResult(BaseModel):
    status: Literal["ok", "failed"]
    inliers: int
    inlier_ratio: float | None = None
    pose_building: Pose | None = None


class MultiLocalizeResponse(BaseModel):
    contract_version: int = CONTRACT_VERSION
    status: Literal["ok", "not_found"]
    reason: str | None = None
    alignment: Alignment4DofResponse | None = None
    frames_agreeing: int
    frames_total: int
    view_spread_deg: float | None = None
    view_diverse: bool = False
    frames: list[MultiFrameResult]
    # Bidang single-frame terbaik agar klien lama tetap dapat membaca bentuk yang dikenal
    inliers: int
    correspondences: int
    inlier_ratio: float | None = None
    reprojection_error_px_median: float | None = None
    retrieval_top1: float | None = None
    ambiguous: bool = False
    intrinsics_source: Literal["client", "map", "exif"]
    pose_model: Pose | None = None
    pose_building: Pose | None = None
    area_id: str | None = None
    map_version: int | None = None
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


def _parse_prior(
    prior_x: float | None, prior_y: float | None, prior_radius_m: float | None
) -> tuple[tuple[float, float] | None, float | None]:
    if (prior_x is None) != (prior_y is None):
        raise HTTPException(422, "send both prior_x and prior_y or neither")
    if prior_x is not None and not (math.isfinite(prior_x) and math.isfinite(prior_y)):
        raise HTTPException(422, "prior_x and prior_y must be finite numbers")
    if prior_radius_m is not None and not math.isfinite(prior_radius_m):
        raise HTTPException(422, "prior_radius_m must be a finite number")
    prior_xy = (prior_x, prior_y) if prior_x is not None else None
    return prior_xy, prior_radius_m


@app.post("/localize")
def localize(
    request: Request,
    image: Annotated[UploadFile, File(description="Foto JPEG atau PNG")],
    fx: Annotated[float | None, Form(gt=0)] = None,
    fy: Annotated[float | None, Form(gt=0)] = None,
    cx: Annotated[float | None, Form(gt=0)] = None,
    cy: Annotated[float | None, Form(gt=0)] = None,
    prior_x: Annotated[float | None, Form()] = None,
    prior_y: Annotated[float | None, Form()] = None,
    prior_radius_m: Annotated[float | None, Form()] = None,
) -> LocalizeResponse:
    """Intrinsik (fx, fy, cx, cy) opsional, untuk foto yang SUDAH tegak. Kalau tidak dikirim,
    dipakai intrinsik peta (resolusi sama) atau taksiran dari EXIF."""
    st = request.app.state
    entry = {"area_id": st.area_id, "map_version": st.map_version}
    return _logged_localize(
        entry,
        lambda: _localize(request, image, fx, fy, cx, cy, prior_x, prior_y, prior_radius_m, entry),
    )


@app.post("/localize-multi")
def localize_multi(
    request: Request,
    frames: Annotated[str, Form(description="Daftar JSON metadata 2 sampai 6 frame")],
    image_0: Annotated[UploadFile | None, File()] = None,
    image_1: Annotated[UploadFile | None, File()] = None,
    image_2: Annotated[UploadFile | None, File()] = None,
    image_3: Annotated[UploadFile | None, File()] = None,
    image_4: Annotated[UploadFile | None, File()] = None,
    image_5: Annotated[UploadFile | None, File()] = None,
) -> MultiLocalizeResponse:
    """Lokalisasi multi-frame (2-6 foto) dengan konsensus penyelarasan 4-DoF (R5)."""
    st = request.app.state
    entry = {"area_id": st.area_id, "map_version": st.map_version}
    uploads_list = [image_0, image_1, image_2, image_3, image_4, image_5]
    return _logged_localize_multi(
        entry, lambda: _localize_multi(request, uploads_list, frames, entry)
    )


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
    prior_x: Annotated[float | None, Form()] = None,
    prior_y: Annotated[float | None, Form()] = None,
    prior_radius_m: Annotated[float | None, Form()] = None,
) -> LocalizeResponse:
    entry = {"candidate": True}
    if app_tokens.is_app_identity(user):
        logging.getLogger("eutopos").info("candidate localization requested by %s", user)
    return _logged_localize(
        entry,
        lambda: _candidate_pose(
            request, s, version_id, image, fx, fy, cx, cy, prior_x, prior_y, prior_radius_m, entry
        ),
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
        log_json = {
            **resp.t_s,
            "inlier_ratio": resp.inlier_ratio,
            "ambiguous": resp.ambiguous,
        }
        entry.update(
            result=resp.status,
            http_status=200,
            inliers=resp.inliers,
            correspondences=resp.correspondences,
            intrinsics_source=resp.intrinsics_source,
            t_s=log_json,
        )
        return resp
    finally:
        entry["wall_s"] = round(time.perf_counter() - t0, 3)
        localize_log.record(entry)


def _logged_localize_multi(
    entry: dict, run_multi: Callable[[], tuple[MultiLocalizeResponse, int, int]]
) -> MultiLocalizeResponse:
    t0 = time.perf_counter()
    try:
        resp, total_inliers, total_correspondences = run_multi()
    except HTTPException as e:
        entry.update(result="rejected", http_status=e.status_code, reason=str(e.detail))
        raise
    except Exception:
        entry.update(result="error", http_status=500)
        raise
    else:
        log_json = {
            **resp.t_s,
            "inlier_ratio": resp.inlier_ratio,
            "ambiguous": resp.ambiguous,
            "frames_agreeing": resp.frames_agreeing,
            "frames_total": resp.frames_total,
            "view_spread_deg": resp.view_spread_deg,
            "view_diverse": resp.view_diverse,
            "multi": True,
        }
        entry.update(
            result=resp.status,
            http_status=200,
            reason=resp.reason,
            inliers=total_inliers,
            correspondences=total_correspondences,
            intrinsics_source=resp.intrinsics_source,
            t_s=log_json,
        )
        return resp
    finally:
        entry["wall_s"] = round(time.perf_counter() - t0, 3)
        localize_log.record(entry)


def _parse_multi_frames(raw_frames: str, expected_count: int) -> list[dict]:
    try:
        parsed = json.loads(raw_frames)
    except ValueError as e:
        raise HTTPException(422, f"frames harus JSON valid: {e}") from e
    if not isinstance(parsed, list) or len(parsed) != expected_count:
        raise HTTPException(
            422, f"frames harus daftar JSON berisi {expected_count} objek sesuai jumlah gambar"
        )
    validated = []
    for idx, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise HTTPException(422, f"frames[{idx}] harus objek JSON")
        pos = item.get("ar_position")
        rot = item.get("ar_rotation")
        if not (
            isinstance(pos, list)
            and len(pos) == 3
            and all(
                isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)
                for v in pos
            )
        ):
            raise HTTPException(422, f"frames[{idx}].ar_position harus 3 angka berhingga")
        if not (
            isinstance(rot, list)
            and len(rot) == 4
            and all(
                isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)
                for v in rot
            )
            and math.hypot(*rot) > 1e-6
        ):
            raise HTTPException(422, f"frames[{idx}].ar_rotation harus 4 angka tak nol")
        intr = [item.get(k) for k in ("fx", "fy", "cx", "cy")]
        given = [v is not None for v in intr]
        if any(given) and not all(given):
            raise HTTPException(422, f"frames[{idx}]: send all of fx, fy, cx, cy or none of them")
        if all(given):
            if not all(
                isinstance(v, int | float)
                and not isinstance(v, bool)
                and math.isfinite(v)
                and v > 0
                for v in intr
            ):
                raise HTTPException(422, f"frames[{idx}]: fx, fy, cx, cy harus positif berhingga")
        validated.append(
            {
                "fx": float(intr[0]) if all(given) else None,
                "fy": float(intr[1]) if all(given) else None,
                "cx": float(intr[2]) if all(given) else None,
                "cy": float(intr[3]) if all(given) else None,
                "given": given,
                "ar_position": [float(v) for v in pos],
                "ar_rotation": [float(v) for v in rot],
            }
        )
    return validated


def _localize_multi(
    request: Request,
    uploads_list: list[UploadFile | None],
    raw_frames: str,
    entry: dict,
) -> tuple[MultiLocalizeResponse, int, int]:
    # Gambar harus berurutan mulai image_0 tanpa celah, 2 sampai 6 gambar
    images: list[UploadFile] = []
    seen_none = False
    for idx, up in enumerate(uploads_list):
        if up is None:
            seen_none = True
        else:
            if seen_none:
                raise HTTPException(
                    422, f"image_{idx} tidak boleh melompati nomor gambar sebelumnya"
                )
            images.append(up)
    if not (MULTI_MIN_FRAMES <= len(images) <= MULTI_MAX_FRAMES):
        raise HTTPException(
            422, f"kirim {MULTI_MIN_FRAMES} sampai {MULTI_MAX_FRAMES} gambar (image_0..image_5)"
        )

    meta = _parse_multi_frames(raw_frames, len(images))

    rgbs: list[np.ndarray] = []
    raw_bytes: list[bytes] = []
    for idx, up in enumerate(images):
        m = meta[idx]
        rgb, data, _ = _read_photo(up, m["fx"], m["fy"], m["cx"], m["cy"], entry)
        rgbs.append(rgb)
        raw_bytes.append(data)

    st = request.app.state
    with st.lock:
        loc, area_id, map_version = st.localizer, st.area_id, st.map_version
        if loc is None:
            raise HTTPException(503, "no published map version for this area")
        if loc.align is None:
            raise HTTPException(409, "multi-frame localization requires an aligned map")
        entry.update(area_id=area_id, map_version=map_version)

        cameras = []
        sources: list[Literal["client", "map", "exif"]] = []
        for idx, rgb in enumerate(rgbs):
            h, w = rgb.shape[:2]
            m = meta[idx]
            if all(m["given"]):
                cam, src = pinhole(m["fx"], m["fy"], m["cx"], m["cy"], w, h), "client"
            elif loc.same_size_as_map(w, h):
                cam, src = loc.map_camera, "map"
            else:
                cam, src = exif_camera(raw_bytes[idx], w, h), "exif"
            cameras.append(cam)
            sources.append(src)

        t_batch = time.perf_counter()
        if hasattr(loc, "localize_batch"):
            results = loc.localize_batch(rgbs, cameras)
        else:
            results = [loc.localize(rgb, cam) for rgb, cam in zip(rgbs, cameras, strict=True)]
        batch_s = time.perf_counter() - t_batch

    per_frame: list[MultiFrameResult] = []
    poses_model: list[Pose | None] = []
    poses_building: list[Pose | None] = []
    candidates: list[align4dof.FrameAlignment] = []
    for idx, r in enumerate(results):
        p_model = p_building = None
        if r.ok and r.cam_from_world is not None:
            wfc = r.cam_from_world.inverse()
            p_model = _model_pose(r.center_model, wfc)
            if building := loc.to_building(r.cam_from_world):
                p_building = Pose(position=building[0], rotation_xyzw=building[1])
                solved = align4dof.solve_from_poses(
                    meta[idx]["ar_position"],
                    meta[idx]["ar_rotation"],
                    building[0],
                    building[1],
                )
                if solved is not None:
                    candidates.append(align4dof.FrameAlignment(idx, solved, r.inliers))
        poses_model.append(p_model)
        poses_building.append(p_building)
        per_frame.append(
            MultiFrameResult(
                status="ok" if r.ok else "failed",
                inliers=r.inliers,
                inlier_ratio=round(r.inlier_ratio, 4) if r.inlier_ratio is not None else None,
                pose_building=p_building,
            )
        )

    cons = align4dof.consensus(candidates)
    total_inliers = sum(r.inliers for r in results)
    total_correspondences = sum(r.correspondences for r in results)

    if cons is not None:
        best_idx = max(cons.agreeing_indices, key=lambda i: results[i].inliers)
        best = results[best_idx]
        headings = [align4dof.ar_heading_deg(meta[i]["ar_rotation"]) for i in cons.agreeing_indices]
        spread = align4dof.view_spread_deg(headings)
        resp = MultiLocalizeResponse(
            status="ok",
            reason=None,
            alignment=Alignment4DofResponse(
                yaw_deg=round(cons.alignment.yaw_deg, 4),
                translation=[round(float(v), 4) for v in cons.alignment.translation],
            ),
            frames_agreeing=len(cons.agreeing_indices),
            frames_total=len(results),
            view_spread_deg=round(spread, 2) if spread is not None else None,
            view_diverse=align4dof.is_view_diverse(spread),
            frames=per_frame,
            inliers=best.inliers,
            correspondences=best.correspondences,
            inlier_ratio=round(best.inlier_ratio, 4) if best.inlier_ratio is not None else None,
            reprojection_error_px_median=(
                round(best.reprojection_error_px_median, 3)
                if best.reprojection_error_px_median is not None
                else None
            ),
            retrieval_top1=(
                round(best.retrieval_top1, 4) if best.retrieval_top1 is not None else None
            ),
            ambiguous=bool(best.ambiguous),
            intrinsics_source=sources[best_idx],
            pose_model=poses_model[best_idx],
            pose_building=poses_building[best_idx],
            area_id=area_id,
            map_version=map_version,
            t_s={"total": round(batch_s, 3)},
        )
    else:
        best_idx = max(range(len(results)), key=lambda i: results[i].inliers)
        best = results[best_idx]
        resp = MultiLocalizeResponse(
            status="not_found",
            reason="no_consensus",
            alignment=None,
            frames_agreeing=0,
            frames_total=len(results),
            view_spread_deg=None,
            view_diverse=False,
            frames=per_frame,
            inliers=best.inliers,
            correspondences=best.correspondences,
            inlier_ratio=round(best.inlier_ratio, 4) if best.inlier_ratio is not None else None,
            reprojection_error_px_median=(
                round(best.reprojection_error_px_median, 3)
                if best.reprojection_error_px_median is not None
                else None
            ),
            retrieval_top1=(
                round(best.retrieval_top1, 4) if best.retrieval_top1 is not None else None
            ),
            ambiguous=bool(best.ambiguous),
            intrinsics_source=sources[best_idx],
            pose_model=None,
            pose_building=None,
            area_id=area_id,
            map_version=map_version,
            t_s={"total": round(batch_s, 3)},
        )
    return resp, total_inliers, total_correspondences


def _localize(
    request: Request,
    image: UploadFile,
    fx: float | None,
    fy: float | None,
    cx: float | None,
    cy: float | None,
    prior_x: float | None,
    prior_y: float | None,
    prior_radius_m: float | None,
    entry: dict,
) -> LocalizeResponse:
    prior_xy, prior_radius_m = _parse_prior(prior_x, prior_y, prior_radius_m)
    rgb, data, given = _read_photo(image, fx, fy, cx, cy, entry)
    st = request.app.state
    with st.lock:
        loc, area_id, map_version = st.localizer, st.area_id, st.map_version
    if loc is None:
        raise HTTPException(503, "no published map version for this area")
    entry.update(area_id=area_id, map_version=map_version)
    return _pose_response(
        loc,
        rgb,
        data,
        fx,
        fy,
        cx,
        cy,
        given,
        area_id,
        map_version,
        st.lock,
        prior_xy=prior_xy,
        prior_radius_m=prior_radius_m,
    )


def _candidate_pose(
    request,
    session,
    version_id,
    image,
    fx,
    fy,
    cx,
    cy,
    prior_x,
    prior_y,
    prior_radius_m,
    entry,
) -> LocalizeResponse:
    prior_xy, prior_radius_m = _parse_prior(prior_x, prior_y, prior_radius_m)
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
                served,
                rgb,
                data,
                fx,
                fy,
                cx,
                cy,
                given,
                area_id,
                map_version,
                st.lock,
                prior_xy=prior_xy,
                prior_radius_m=prior_radius_m,
            )

        # Pemuatan hanya memakai kunci cache. Inferensi mengambil st.lock dari dalam kunci cache.
        with cache.use(version_id) as (loc, area_id, map_version):
            entry.update(area_id=area_id, map_version=map_version)
            try:
                return _pose_response(
                    loc,
                    rgb,
                    data,
                    fx,
                    fy,
                    cx,
                    cy,
                    given,
                    area_id,
                    map_version,
                    st.lock,
                    prior_xy=prior_xy,
                    prior_radius_m=prior_radius_m,
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
    loc,
    rgb,
    data,
    fx,
    fy,
    cx,
    cy,
    given,
    area_id,
    map_version,
    lock,
    *,
    prior_xy: tuple[float, float] | None = None,
    prior_radius_m: float | None = None,
) -> LocalizeResponse:
    h, w = rgb.shape[:2]
    if all(given):
        camera, source = pinhole(fx, fy, cx, cy, w, h), "client"
    elif loc.same_size_as_map(w, h):
        camera, source = loc.map_camera, "map"
    else:
        camera, source = exif_camera(data, w, h), "exif"

    with lock:
        if prior_xy is not None:
            r = loc.localize(rgb, camera, prior_xy=prior_xy, prior_radius_m=prior_radius_m)
        else:
            r = loc.localize(rgb, camera)

    pose_model = pose_building = None
    if r.ok:
        world_from_cam = r.cam_from_world.inverse()
        pose_model = _model_pose(r.center_model, world_from_cam)
        if building := loc.to_building(r.cam_from_world):
            pose_building = Pose(position=building[0], rotation_xyzw=building[1])
    return LocalizeResponse(
        status="ok" if r.ok else "failed",
        inliers=r.inliers,
        correspondences=r.correspondences,
        inlier_ratio=round(r.inlier_ratio, 4) if r.inlier_ratio is not None else None,
        reprojection_error_px_median=(
            round(r.reprojection_error_px_median, 3)
            if r.reprojection_error_px_median is not None
            else None
        ),
        retrieval_top1=round(r.retrieval_top1, 4) if r.retrieval_top1 is not None else None,
        ambiguous=bool(r.ambiguous),
        prior_used=bool(r.prior_used),
        outside_prior=bool(r.outside_prior),
        deep_search=bool(r.deep_search),
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
