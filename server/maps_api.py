"""API dashboard: versi peta, laporan 3D, Terbitkan, status layanan (spesifikasi bagian 7 dan 9)."""

import os
from datetime import datetime
from pathlib import Path

import plotly
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import select

from server import active_map, uploads
from server.db import MapJob, MapVersion, publish
from server.db import active_version as active_of

MAPS_ROOT = Path("/maps")  # jalur peta di dalam container (deploy/compose.yaml)
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"

router = APIRouter()


class VersionOut(BaseModel):
    id: int
    area_id: str
    version: int
    status: str
    created_at: datetime
    published_by: str | None
    job_id: int | None
    has_report: bool


def _report(v: MapVersion) -> Path | None:
    p = (Path(v.path) / "report.html").resolve()
    if p.is_relative_to(MAPS_ROOT.resolve()) and p.is_file():
        return p
    return None


def _out(s, v: MapVersion) -> VersionOut:
    job = s.exec(select(MapJob.id).where(MapJob.map_version_id == v.id)).first()
    return VersionOut(
        **v.model_dump(
            include={"id", "area_id", "version", "status", "created_at", "published_by"}
        ),
        job_id=job,
        has_report=_report(v) is not None,
    )


@router.get("/api/versions")
def list_versions(user: uploads.User, s: uploads.DB) -> list[VersionOut]:
    stmt = select(MapVersion).order_by(MapVersion.area_id, MapVersion.version.desc())
    return [_out(s, v) for v in s.exec(stmt)]


@router.get("/api/versions/{version_id}/report")
def report(version_id: int, user: uploads.User, s: uploads.DB) -> FileResponse:
    v = s.get(MapVersion, version_id)
    if v is None or (path := _report(v)) is None:
        raise HTTPException(404, "laporan tidak ada")
    return FileResponse(path, media_type="text/html")


@router.post("/api/versions/{version_id}/publish")
def publish_version(version_id: int, request: Request, user: uploads.User, s: uploads.DB) -> dict:
    v = s.get(MapVersion, version_id)
    if v is None:
        raise HTTPException(404, "versi tidak ada")
    st = request.app.state
    serving = v.area_id == active_map.serving_area()
    # ponytail: pemeriksaan tanpa kunci, dua klik dalam milidetik yang sama masih bisa lolos.
    # Cukup untuk satu operator; kunci terbitkan kalau pengguna dashboard bertambah.
    if serving and st.reloading:
        raise HTTPException(409, "peta sebelumnya masih dimuat, coba lagi sebentar")
    previous = active_of(s, v.area_id)
    v = publish(s, version_id, by=user)
    if not serving:
        return {"version": _out(s, v), "reload": "other_area"}
    engine = uploads._engine(os.environ["DATABASE_URL"])
    prev_id = previous.id if previous and previous.id != v.id else None
    active_map.reload_in_background(st, engine, v.id, prev_id)
    return {"version": _out(s, v), "reload": "started"}


@router.get("/api/service")
def service(request: Request, user: uploads.User) -> dict:
    st = request.app.state
    return {
        "area_id": st.area_id,
        "map_version": st.map_version,
        "reloading": st.reloading,
        "reload_error": st.reload_error,
    }


@router.get("/assets/plotly.min.js")
def plotly_js() -> FileResponse:
    # Pustaka publik (MIT): laporan 3D merujuk berkas ini, bukan menyematkan 4,8 MB per laporan.
    return FileResponse(PLOTLY_JS, media_type="text/javascript")
