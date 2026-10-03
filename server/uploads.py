"""API pekerjaan bangun peta dan hook tusd (spesifikasi web-upload bagian 4 dan 8).

Alur: POST /api/jobs (status uploading) -> unggahan tus dengan metadata job_id dan name ->
hook pre-create (identitas, ID unggahan buatan server) -> hook pre-finish (tandai lengkap, queued
setelah video terakhir). /internal/* tidak dirutekan cloudflared, hanya tusd di jaringan internal.

Kanal hook diautentikasi dengan rahasia bersama di URL hook (TUS_HOOK_SECRET, parameter key): port
api terbuka di jaringan lab, dan hook palsu bisa mengantrekan atau merusak pekerjaan siapa pun.
"""

import json
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import create_engine
from sqlmodel import Session, select

from server import auth, jobs
from server.db import MapJob

UPLOADS = Path("/data/uploads")  # -upload-dir tusd, dilihat dari container api
MAX_VIDEOS = 4
MAX_VIDEO_BYTES = 2 * 1024**3  # sama dengan -max-size tusd

router = APIRouter()


@lru_cache
def _engine(url: str):
    return create_engine(url)


def get_session():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise HTTPException(503, "service is running without a database (EUTOPOS_MAP_DIR)")
    with Session(_engine(url)) as s:
        yield s


DB = Annotated[Session, Depends(get_session)]
User = Annotated[str, Depends(auth.current_user)]


class VideoIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: Literal["peta", "uji"]
    size: int = Field(gt=0, le=MAX_VIDEO_BYTES)


class JobIn(BaseModel):
    area_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")
    area_name: str = Field(min_length=1, max_length=100)
    videos: list[VideoIn] = Field(min_length=1, max_length=MAX_VIDEOS)


class VideoOut(BaseModel):
    # Tanpa upload_id dan path: dengan ID unggahan orang bisa mengganggu unggahan milik orang lain.
    name: str
    role: str
    size: int | None = None  # None: pekerjaan dari manage job (CLI), videonya tidak diunggah
    uploaded: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_cli(cls, v):
        # manage job menyimpan {"path", "role"} saja: nama diambil dari nama berkas.
        if isinstance(v, dict) and "name" not in v and v.get("path"):
            return {**v, "name": Path(v["path"]).name}
        return v


class JobOut(BaseModel):
    id: int
    area_id: str
    status: str
    stage: str | None
    created_by: str
    videos: list[VideoOut]
    summary: dict | None
    error: str | None
    map_version_id: int | None


@router.post("/api/jobs", status_code=201)
def create(body: JobIn, user: User, s: DB) -> JobOut:
    names = [v.name for v in body.videos]
    if len(set(names)) != len(names):
        raise HTTPException(422, "duplicate video names in one job")
    videos = [
        {**v.model_dump(), "upload_id": None, "path": None, "uploaded": False} for v in body.videos
    ]
    try:
        job = jobs.create_job(s, body.area_id, body.area_name, user, videos)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return JobOut.model_validate(job, from_attributes=True)


@router.get("/api/jobs")
def list_jobs(user: User, s: DB, limit: int = Query(50, ge=1, le=200)) -> list[JobOut]:
    stmt = select(MapJob).order_by(MapJob.id.desc()).limit(limit)
    return [JobOut.model_validate(j, from_attributes=True) for j in s.exec(stmt)]


@router.get("/api/jobs/{job_id}")
def get(job_id: int, user: User, s: DB) -> JobOut:
    job = s.get(MapJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return JobOut.model_validate(job, from_attributes=True)


class HookReject(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _header(headers: dict, name: str) -> str | None:
    """tusd (Go) mengirim nama header dalam bentuk kanonik. Cocokkan tanpa peka huruf."""
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v[0] if v else None
    return None


def _locked_job(s: Session, meta) -> MapJob:
    if not isinstance(meta, dict):
        raise HookReject(400, "invalid metadata")
    try:
        job_id = int(meta.get("job_id", ""))
    except ValueError as e:
        raise HookReject(400, "missing job_id metadata") from e
    # Kunci baris: dua video yang selesai bersamaan tidak saling menimpa daftar videos.
    stmt = select(MapJob).where(MapJob.id == job_id).with_for_update()
    job = s.exec(stmt).first()
    if job is None:
        raise HookReject(404, "job not found")
    return job


def _pre_create(s: Session, upload: dict, headers: dict) -> dict:
    try:
        email = auth.email_from_token(_header(headers, auth.HEADER))
    except auth.AuthError as e:
        raise HookReject(e.status, e.message) from e
    meta = upload.get("MetaData") or {}
    job = _locked_job(s, meta)
    if job.created_by != email:
        raise HookReject(403, "this job belongs to another user")
    if job.status != "uploading":
        raise HookReject(409, f"job is {job.status}; it no longer accepts uploads")
    idx = next((i for i, v in enumerate(job.videos) if v["name"] == meta.get("name")), None)
    if idx is None:
        raise HookReject(404, "video name is not registered in this job")
    video = job.videos[idx]
    if video.get("uploaded"):
        raise HookReject(409, "this video is already fully uploaded")
    if upload.get("SizeIsDeferred") or upload.get("Size") != video["size"]:
        raise HookReject(400, "file size differs from the registered size")
    upload_id = f"job{job.id}-v{idx}-{secrets.token_hex(8)}"
    old = video.get("upload_id")
    videos = list(job.videos)  # JSON tidak dilacak per elemen: ganti seluruh daftar
    videos[idx] = {**video, "upload_id": upload_id, "path": str(UPLOADS / upload_id)}
    job.videos = videos
    s.add(job)
    s.commit()
    if old:  # klien memulai ulang dari nol: sisa unggahan lama dibuang
        for p in (UPLOADS / old, UPLOADS / f"{old}.info"):
            p.unlink(missing_ok=True)
    return {"ChangeFileInfo": {"ID": upload_id}}


def _pre_finish(s: Session, upload: dict) -> None:
    # Path tidak pernah diambil dari hook (Storage.Path): selalu dari ID buatan server.
    job = _locked_job(s, upload.get("MetaData") or {})
    videos = list(job.videos)
    uid = upload.get("ID")
    idx = next((i for i, v in enumerate(videos) if uid and v["upload_id"] == uid), None)
    if idx is None:
        raise HookReject(404, "unknown upload ID")
    # Jangan percaya kata hook saja: berkas di disk harus sudah selengkap ukuran yang didaftarkan.
    data = UPLOADS / uid
    if not data.is_file() or data.stat().st_size != videos[idx]["size"]:
        raise HookReject(409, "upload is not complete yet")
    videos[idx] = {**videos[idx], "uploaded": True}
    job.videos = videos
    if job.status == "uploading" and all(v["uploaded"] for v in videos):
        job.status = "queued"
    s.add(job)
    s.commit()


def _hook_key(key: Annotated[str | None, Query()] = None) -> None:
    secret = os.environ.get("TUS_HOOK_SECRET", "")
    if not secret:
        raise HTTPException(503, "TUS_HOOK_SECRET is not set; hook is closed")
    if not key or not secrets.compare_digest(key, secret):
        raise HTTPException(403, "wrong hook key")


@router.post("/internal/tus-hook", dependencies=[Depends(_hook_key)])
def tus_hook(hook: dict, s: DB) -> dict:
    kind, event = hook.get("Type"), hook.get("Event") or {}
    upload = event.get("Upload") or {}
    try:
        if kind == "pre-create":
            headers = (event.get("HTTPRequest") or {}).get("Header") or {}
            return _pre_create(s, upload, headers)
        if kind == "pre-finish":
            _pre_finish(s, upload)
    except HookReject as e:
        s.rollback()
        body = json.dumps({"message": e.message})
        response = {"StatusCode": e.status, "Body": body}
        response["Header"] = {"Content-Type": "application/json"}
        return {"RejectUpload": True, "HTTPResponse": response}
    return {}
