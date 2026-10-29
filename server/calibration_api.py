"""API kalibrasi di dashboard: set titik, impor pengamatan, hitung, terapkan, riwayat, batalkan.

Rencana `docs/plans/2026-10-29-kalibrasi-dashboard.md`. `fit` tidak menyimpan apa pun; `apply`
selalu menghitung ulang dari set yang tersimpan (klien tidak pernah mengirim parameter), lalu
menulis align.json atomik yang dibaca Localizer tanpa memuat ulang layanan. Penerapan dijaga tiga
hal: `base_alignment_id` (dua admin tidak saling menimpa), penulisan berkas sebelum commit, dan
indeks unik "satu applied per versi" di database.
"""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from server import alignment, area_api, calibration, content_migration, maps_api, uploads
from server.active_map import _env_int  # ponytail: pembaca env yang sama dengan load_localizer
from server.area_api import _write  # ponytail: aturan JSON + admin yang sama dengan area_api
from server.db import (
    Alignment,
    CalibrationObservation,
    CalibrationPoint,
    CalibrationSet,
    MapVersion,
    iso_utc,
)

log = logging.getLogger("eutopos")
router = APIRouter()

MAX_POINTS = 500
MAX_ID_LEN = 40
MAX_CSV_BYTES = 2 * 1024 * 1024
NO_MOVE = {"rooms": 0, "strokes": 0, "edits": 0}


class PointIn(BaseModel):
    # Berhingga atau tidaknya koordinat diperiksa di _check_points: galat validasi pydantic yang
    # memuat NaN tidak bisa disajikan FastAPI (jadi 500), jadi NaN tidak boleh jadi galat pydantic.
    point_id: str
    x_m: float
    y_m: float
    role: Literal["reference", "test"]


class SetIn(BaseModel):
    note: str | None = None
    points: list[PointIn]


class ImportIn(BaseModel):
    csv: str


class BaseIn(BaseModel):
    base_alignment_id: int | None


def _check_points(body: SetIn) -> None:
    if not 1 <= len(body.points) <= MAX_POINTS:
        raise HTTPException(422, f"points must have 1 to {MAX_POINTS} entries")
    seen = set()
    for p in body.points:
        pid = p.point_id.strip()
        if not 1 <= len(pid) <= MAX_ID_LEN or pid != p.point_id:
            raise HTTPException(422, f"point_id must be 1 to {MAX_ID_LEN} characters, no spaces")
        if pid in seen:
            raise HTTPException(422, f"duplicate point_id: {pid}")
        seen.add(pid)
        if not calibration._finite(p.x_m, p.y_m):
            raise HTTPException(422, f"coordinates of {pid} must be finite numbers")
    if body.note is not None and len(body.note) > 500:
        raise HTTPException(422, "note is too long")


def _set(s, set_id: int) -> CalibrationSet:
    cal = s.get(CalibrationSet, set_id)
    if cal is None:
        raise HTTPException(404, "calibration set not found")
    return cal


def _version(s, version_id: int) -> MapVersion:
    v = s.get(MapVersion, version_id)
    if v is None:
        raise HTTPException(404, "version not found")
    return v


@router.post("/api/versions/{version_id}/calibration", status_code=201)
def create_set(version_id: int, body: SetIn, request: Request, user: uploads.User, s: uploads.DB):
    _write(request, user)
    v = _version(s, version_id)
    _check_points(body)
    cal = CalibrationSet(area_id=v.area_id, map_version_id=v.id, created_by=user, note=body.note)
    s.add(cal)
    s.flush()
    for p in body.points:
        s.add(
            CalibrationPoint(set_id=cal.id, point_id=p.point_id, x_m=p.x_m, y_m=p.y_m, role=p.role)
        )
    s.commit()
    return {"id": cal.id}


def _fail(e: calibration.CalibrationError) -> HTTPException:
    return HTTPException(422, {"code": e.code, "message": str(e)})


@router.post("/api/calibration/{set_id}/observations/import")
def import_observations(
    set_id: int, body: ImportIn, request: Request, user: uploads.User, s: uploads.DB
) -> dict:
    _write(request, user)
    cal = _set(s, set_id)
    if len(body.csv.encode()) > MAX_CSV_BYTES:
        raise HTTPException(413, "results.csv is larger than 2 MB")
    try:
        parsed = calibration.parse_results_csv(body.csv)
    except calibration.CalibrationError as e:
        raise _fail(e) from e
    known = set(s.exec(select(CalibrationPoint.point_id).where(CalibrationPoint.set_id == cal.id)))
    accepted, low, unknown = 0, set(), set()
    for o in parsed:
        if o.point_id not in known:
            unknown.add(o.point_id)
        elif o.inliers < calibration.MIN_INLIERS:
            low.add(o.point_id)
        else:
            accepted += 1
            s.add(
                CalibrationObservation(
                    set_id=cal.id,
                    point_id=o.point_id,
                    model_xyz=list(o.model_xyz),
                    inliers=o.inliers,
                    source="import",
                )
            )
    s.commit()
    return {
        "accepted": accepted,
        "rejected_low_inliers": sorted(low),
        "unknown_points": sorted(unknown),
    }


def _compute(s, cal: CalibrationSet) -> calibration.FitResult:
    points = [
        calibration.CalPoint(p.point_id, p.x_m, p.y_m, p.role)
        for p in s.exec(
            select(CalibrationPoint).where(CalibrationPoint.set_id == cal.id).order_by("id")
        )
    ]
    obs = [
        calibration.Observation(o.point_id, tuple(o.model_xyz), o.inliers)
        for o in s.exec(
            select(CalibrationObservation).where(CalibrationObservation.set_id == cal.id)
        )
    ]
    try:
        return calibration.fit_alignment(points, calibration.aggregate(obs))
    except calibration.CalibrationError as e:
        raise _fail(e) from e


@router.post("/api/calibration/{set_id}/fit")
def fit(set_id: int, request: Request, user: uploads.User, s: uploads.DB) -> dict:
    """Hitung saja, tanpa menyimpan apa pun."""
    _write(request, user)
    r = _compute(s, _set(s, set_id))
    return {"align": r.align, "stats": r.stats, "rows": r.rows}


def _align_path(v: MapVersion) -> Path:
    """align.json di folder run versi itu, sama dengan yang dibaca active_map.load_localizer."""
    run = Path(v.path) / f"kp{_env_int('EUTOPOS_MAX_KP', 1024)}-r{_env_int('EUTOPOS_RESIZE', 1024)}"
    run = run.resolve()
    if not run.is_relative_to(maps_api.MAPS_ROOT.resolve()):
        raise HTTPException(409, "the map folder of this version is outside the maps root")
    if not run.is_dir():
        raise HTTPException(409, "the map folder of this version has no run directory")
    return run / "align.json"


def _current(s, version_id: int) -> Alignment | None:
    return s.exec(
        select(Alignment).where(
            Alignment.map_version_id == version_id, Alignment.status == "applied"
        )
    ).first()


def _check_base(current: Alignment | None, base_id: int | None) -> None:
    if (current.id if current else None) != base_id:
        raise HTTPException(409, "the alignment changed since you loaded this page; reload")


def _restore(dst: Path, old: str | None) -> None:
    try:
        if old is None:
            dst.unlink(missing_ok=True)
        else:
            tmp = dst.with_name(dst.name + ".tmp")
            tmp.write_text(old, encoding="utf-8")
            os.replace(tmp, dst)
    except OSError:
        log.exception("align.json lama tidak bisa dipulihkan: %s", dst)


def _migrate(s, v: MapVersion, old: dict | None, new: dict) -> dict:
    """Konten area berpindah hanya bila versi ini yang terbit; kandidat tidak menyentuhnya."""
    if v.status != "published":
        return {**NO_MOVE, "republish_required": False}
    return content_migration.migrate(s, v.area_id, old, new)


def _install(s, v, current, params, stats, set_id, source, user) -> dict:
    """Ubah database tanpa commit, tulis berkas, baru commit; gagal di mana pun berarti tidak
    ada yang berubah (berkas lama dipulihkan bila commit yang gagal)."""
    dst = _align_path(v)
    old = dst.read_text(encoding="utf-8") if dst.exists() else None
    row = Alignment(
        map_version_id=v.id,
        set_id=set_id,
        params=params,
        stats=stats,
        status="applied",
        source=source,
        created_by=user,
        applied_at=datetime.now(UTC),
    )
    try:
        if current is not None:
            current.status = "superseded"
            s.add(current)
            s.flush()  # indeks unik: yang lama harus lepas sebelum yang baru masuk
        s.add(row)
        moved = _migrate(s, v, current.params if current else None, params)
        s.flush()
    except IntegrityError as e:
        s.rollback()
        raise HTTPException(409, "another alignment was applied at the same time") from e
    try:
        alignment._write_atomic(dst, params)
    except OSError as e:
        s.rollback()
        dst.with_name(dst.name + ".tmp").unlink(missing_ok=True)
        log.exception("gagal menulis %s", dst)
        raise HTTPException(500, f"could not write align.json: {e.__class__.__name__}") from e
    try:
        s.commit()
    except IntegrityError as e:
        _restore(dst, old)
        raise HTTPException(409, "another alignment was applied at the same time") from e
    except Exception:
        _restore(dst, old)
        raise
    area_api.clear_cache()
    republish = moved.pop("republish_required")
    return {"alignment_id": row.id, "republish_required": republish, "moved": moved}


@router.post("/api/calibration/{set_id}/apply")
def apply(set_id: int, body: BaseIn, request: Request, user: uploads.User, s: uploads.DB) -> dict:
    _write(request, user)
    cal = _set(s, set_id)
    v = _version(s, cal.map_version_id)
    current = _current(s, v.id)
    _check_base(current, body.base_alignment_id)
    r = _compute(s, cal)
    return _install(s, v, current, r.align, r.stats, cal.id, "fit", user)


@router.post("/api/alignments/{alignment_id}/revert")
def revert(
    alignment_id: int, body: BaseIn, request: Request, user: uploads.User, s: uploads.DB
) -> dict:
    _write(request, user)
    target = s.get(Alignment, alignment_id)
    if target is None:
        raise HTTPException(404, "alignment not found")
    v = _version(s, target.map_version_id)
    current = _current(s, v.id)
    _check_base(current, body.base_alignment_id)
    if current is not None and current.id == target.id:
        raise HTTPException(409, "this alignment is already in effect")
    return _install(s, v, current, target.params, target.stats, target.set_id, "revert", user)


@router.get("/api/versions/{version_id}/alignments")
def alignments(version_id: int, user: uploads.User, s: uploads.DB) -> list[dict]:
    _version(s, version_id)
    rows = s.exec(
        select(Alignment)
        .where(Alignment.map_version_id == version_id)
        .order_by(Alignment.id.desc())
    )
    return [
        {
            "id": a.id,
            "status": a.status,
            "source": a.source,
            "created_by": a.created_by,
            "created_at": iso_utc(a.created_at),
            "stats": a.stats,
            "scale": a.params["meter_from_model"]["scale"],
        }
        for a in rows
    ]
