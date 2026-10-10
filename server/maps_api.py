"""API dashboard: versi peta, laporan 3D, Terbitkan, status layanan (spesifikasi bagian 7 dan 9)."""

from datetime import datetime
from pathlib import Path

import plotly
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import select

from server import active_map, auth, jobs, system, uploads
from server.db import MapJob, MapVersion, publish

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


def preview_path(job: MapJob) -> Path | None:
    """Pratinjau job (preview.jpg di folder petanya), hanya kalau tepat di bawah /maps."""
    p = (MAPS_ROOT / job.area_id / f"job-{job.id}" / "preview.jpg").resolve()
    return p if p.is_relative_to(MAPS_ROOT.resolve()) and p.is_file() else None


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


@router.get("/api/jobs/{job_id}/preview")
def job_preview(job_id: int, user: uploads.User, s: uploads.DB) -> FileResponse:
    job = s.get(MapJob, job_id)
    if job is None or (path := preview_path(job)) is None:
        raise HTTPException(404, "preview not found")
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/api/versions/{version_id}/report")
def report(version_id: int, user: uploads.User, s: uploads.DB) -> FileResponse:
    v = s.get(MapVersion, version_id)
    if v is None or (path := _report(v)) is None:
        raise HTTPException(404, "report not found")
    return FileResponse(path, media_type="text/html")


@router.post("/api/versions/{version_id}/publish")
def publish_version(version_id: int, request: Request, user: uploads.User, s: uploads.DB) -> dict:
    # Tanpa isi, rute ini bisa dipicu formulir situs lain yang menumpang cookie Access (CSRF).
    # application/json butuh preflight CORS, dan layanan ini tidak mengizinkan CORS.
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(415, "send with Content-Type: application/json")
    v = s.get(MapVersion, version_id)
    if v is None:
        raise HTTPException(404, "version not found")
    if s.exec(
        select(MapJob.id).where(MapJob.map_version_id == v.id, MapJob.status == "deleting")
    ).first():
        raise HTTPException(409, "its job is being deleted")
    st = request.app.state
    serving = v.area_id == active_map.serving_area()
    # ponytail: pemeriksaan tanpa kunci, dua klik dalam milidetik yang sama masih bisa lolos.
    # Cukup untuk satu operator; kunci terbitkan kalau pengguna dashboard bertambah.
    if serving and st.reloading:
        raise HTTPException(409, "a map is still loading; try again shortly")
    if not serving:
        v = publish(s, version_id, by=user)
        return {"version": _out(s, v), "reload": "other_area"}
    # Diterbitkan oleh thread setelah peta terbukti bisa dimuat (server/active_map.py).
    active_map.reload_in_background(st, s.get_bind(), v.id, user)
    return {"version": _out(s, v), "reload": "started"}


@router.delete("/api/versions/{version_id}", status_code=202)
def delete_version(version_id: int, response: Response, user: uploads.User, s: uploads.DB) -> dict:
    """Hapus sebuah versi peta (khusus admin).

    Versi hasil job ikut menghapus job-nya, lewat jalur yang sama dengan DELETE /api/jobs/{id}:
    api hanya menandai, pekerja yang menghapus folder petanya (api memasang /maps hanya-baca).
    Versi tanpa job (didaftarkan lewat CLI) hanya dihapus barisnya. Berkasnya milik pemilik dan
    tidak pernah disentuh, sama seperti berkas CLI di pekerja.
    """
    if not auth.is_admin(user):
        raise HTTPException(403, "only admins can delete map versions")
    v = s.get(MapVersion, version_id)
    if v is None:
        raise HTTPException(404, "version not found")
    if v.status == "published":
        raise HTTPException(409, "this version is published; publish another version first")
    job = s.exec(select(MapJob).where(MapJob.map_version_id == v.id)).first()
    if job is None:
        s.delete(v)
        s.commit()
        response.status_code = 200
        return {"status": "deleted"}
    if reason := jobs.delete_block_reason(s, job):
        raise HTTPException(409, reason)
    if job.status != "deleting":
        jobs.request_delete(s, job)
    return {"status": "deleting", "job_id": job.id}


@router.get("/api/me")
def me(user: uploads.User) -> dict:
    """Identitas untuk menu akun. is_admin hanya menentukan tombol hapus, server tetap memeriksa."""
    return {"email": user, "is_admin": auth.is_admin(user)}


@router.get("/api/service")
def service(request: Request, user: uploads.User) -> dict:
    st = request.app.state
    return {
        "area_id": st.area_id,
        "map_version": st.map_version,
        "reloading": st.reloading,
        "reload_error": st.reload_error,
    }


@router.get("/api/system")
def system_diagnostics(request: Request, user: uploads.User) -> system.SystemDiagnostics:
    """Telemetri sistem nyata: kapasitas penyimpanan (/maps dan /data),
    komputasi GPU, suhu, dan uptime.
    """
    st = request.app.state
    return system.get_system_diagnostics(
        area_id=getattr(st, "area_id", None),
        map_version=getattr(st, "map_version", None),
        reloading=getattr(st, "reloading", False),
        reload_error=getattr(st, "reload_error", None),
    )


@router.get("/assets/plotly.min.js")
def plotly_js() -> FileResponse:
    # Pustaka publik (MIT): laporan 3D merujuk berkas ini, bukan menyematkan 4,8 MB per laporan.
    return FileResponse(PLOTLY_JS, media_type="text/javascript")
