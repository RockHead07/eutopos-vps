# Unggahan Video dan Autentikasi (PR 2) Implementation Plan

**Status:** dieksekusi, merged sebagai PR #29 (2026-10-02). Verifikasi PC lab: spesifikasi web unggah bagian 13.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Video diunggah lewat protokol tus (bisa dilanjutkan, potongan di bawah batas Cloudflare) ke tusd, lalu otomatis menjadi pekerjaan bangun peta, dengan setiap langkah diperiksa terhadap identitas Cloudflare Access.

**Architecture:** Klien membuat pekerjaan lewat `POST /api/jobs` (status `uploading`, video didaftarkan dengan nama, peran, ukuran). Setiap video diunggah ke tusd dengan metadata `job_id` dan `name`. Hook `pre-create` di FastAPI memvalidasi JWT Access dari header klien yang diteruskan tusd, memeriksa pekerjaan, lalu memberi ID unggahan buatan server. Hook `pre-finish` menandai video lengkap (baris pekerjaan dikunci, aman untuk dua video selesai bersamaan) dan mengubah status ke `queued` setelah video terakhir. Pekerja dari PR 1 mengambil sisanya.

**Tech Stack:** FastAPI, SQLModel, PyJWT (`pyjwt[crypto]`), tusd v2.10.1 (container resmi), Docker Compose.

**Spec:** `docs/specs/2026-10-01-web-upload-and-map-build-design.md` (bagian 3, 4 langkah 2 sampai 5, 8, 10, 13 PR 2). Riset: `docs/web-upload-research.md` bagian 2 dan 5.

## Global Constraints

- **Prasyarat:** PR 1 (`feat/map-job-worker`) sudah di `main`. Worktree baru: `git -c core.longpaths=true worktree add -b feat/upload-auth D:/wt/upload-auth origin/main`.
- Nama berkas, fungsi, opsi CLI bahasa Inggris. Pesan dan komentar bahasa Indonesia. **Tanpa em dash.**
- Ruff 0.16.9, baris 100: `uvx ruff@0.16.9 check .` dan `uvx ruff@0.16.9 format --check .` bersih (ruff juga memformat blok Python di berkas Markdown).
- Uji: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q` dari akar worktree.
- Dependensi baru lewat `uv add --no-sync`, lalu pasang ke `.venv` spike lewat `uv export` + `uv pip install` (sync penuh akan menghapus paket spike).
- **Gagal tertutup untuk rute terlindungi:** tanpa `CF_ACCESS_TEAM_DOMAIN` dan `CF_ACCESS_AUD`, `/api/*` dan hook `pre-create` menjawab 503. `/localize` dan `/health` tetap jalan (supaya layanan yang sudah berjalan tidak mati sebelum PR 4). Ini penyesuaian atas spesifikasi bagian 8 ("layanan menolak menyala"), dicatat di spesifikasi pada Task 4.
- `EUTOPOS_DEV_NO_AUTH=1` hanya untuk uji lokal dan verifikasi PC lab sebelum Tunnel; pengguna menjadi `dev@local`.
- `CF_ACCESS_TEAM_DOMAIN` berbentuk `https://<team>.cloudflareaccess.com` (sama dengan klaim `iss`). Nilai nyata dan AUD hanya di `deploy/.env`, **tidak pernah di repo**.
- Batas: maksimal 4 video per pekerjaan, maksimal 2 GiB per video (sama dengan `-max-size` tusd).
- ID unggahan dibuat server dengan pola `job<id>-v<indeks>-<16 hex>`. Path berkas selalu dihitung dari ID ini, **tidak pernah** dari `Storage.Path` kiriman hook.
- Commit per tugas setelah eksekusi disetujui. Push hanya atas perintah terpisah. Tanpa atribusi AI.

## Review Focus

1. **Dua video selesai bersamaan:** dua hook `pre-finish` memperbarui JSON `videos` yang sama. Tanpa kunci baris, satu pembaruan hilang dan pekerjaan tidak pernah `queued`. Pemilik: Task 3 (`with_for_update`, uji urutan selesai).
2. **Pengguna lain menebak `job_id`:** `pre-create` harus menolak kalau email JWT berbeda dari `created_by`. Pemilik: Task 3.
3. **Ukuran berkas berbeda dari yang didaftarkan, atau panjang tus ditunda** (`SizeIsDeferred`): ditolak sebelum unggahan dibuat. Pemilik: Task 3.
4. **Unggahan ditinggal:** pekerjaan `uploading` lebih dari 24 jam menjadi `failed` dan berkas parsialnya dihapus. Pemilik: Task 2.
5. **Hook palsu dari jaringan lokal** mengirim `Storage.Path` sembarang: path tidak pernah diambil dari hook, ID divalidasi polanya. Pemilik: Task 3.

---

### Task 1: Autentikasi Cloudflare Access

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (tambah `pyjwt[crypto]`)
- Create: `server/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces:
  - `server.auth.HEADER = "Cf-Access-Jwt-Assertion"`, `server.auth.DEV_USER = "dev@local"`
  - `class server.auth.AuthError(Exception)` dengan atribut `status: int`, `message: str`
  - `server.auth.email_from_token(token: str | None) -> str` (melempar `AuthError`)
  - `server.auth.current_user(request: Request) -> str` (dependency FastAPI, melempar `HTTPException`)
  - `server.auth.signing_key(token: str, team: str)` (dipisah supaya uji bisa menggantinya)

- [ ] **Step 1: Tambah dependensi**

```bash
uv add --no-sync "pyjwt[crypto]>=2.15.1"
uv export --frozen --no-dev --no-emit-project --no-hashes -o "$TMP/req.txt"
uv pip install --python /d/Dev/Projects/eutopos-vps/.venv/Scripts/python.exe -r "$TMP/req.txt"
```

Expected: `pyproject.toml` dan `uv.lock` berubah. `python -c "import jwt; print(jwt.__version__)"` dari `.venv` mencetak `2.15.x`.

- [ ] **Step 2: Tulis uji yang gagal (`tests/test_auth.py`)**

```python
"""Uji validasi JWT Cloudflare Access dengan kunci RSA uji, tanpa jaringan."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from server import auth

TEAM = "https://tim-uji.cloudflareaccess.com"
AUD = "aud-uji"


@pytest.fixture
def key(monkeypatch):
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("CF_ACCESS_AUD", AUD)
    monkeypatch.delenv("EUTOPOS_DEV_NO_AUTH", raising=False)
    monkeypatch.setattr(auth, "signing_key", lambda token, team: k.public_key())
    return k


def token(key, **claims):
    body = {"aud": AUD, "iss": TEAM, "email": "a@x.id", "exp": time.time() + 600, **claims}
    return jwt.encode(body, key, algorithm="RS256")


def test_valid_token_gives_email(key):
    assert auth.email_from_token(token(key)) == "a@x.id"


@pytest.mark.parametrize(
    "claims,status",
    [
        ({"aud": "aplikasi-lain"}, 403),
        ({"iss": "https://tim-lain.cloudflareaccess.com"}, 403),
        ({"exp": time.time() - 10}, 403),
        ({"email": None}, 403),
    ],
    ids=["aud-salah", "iss-salah", "kedaluwarsa", "tanpa-email"],
)
def test_bad_tokens_are_rejected(key, claims, status):
    with pytest.raises(auth.AuthError) as e:
        auth.email_from_token(token(key, **claims))
    assert e.value.status == status


def test_missing_token_is_401(key):
    with pytest.raises(auth.AuthError) as e:
        auth.email_from_token(None)
    assert e.value.status == 401


def test_unconfigured_is_503_not_open(monkeypatch):
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    monkeypatch.delenv("EUTOPOS_DEV_NO_AUTH", raising=False)
    with pytest.raises(auth.AuthError) as e:
        auth.email_from_token("apa saja")
    assert e.value.status == 503


def test_dev_mode(monkeypatch):
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    assert auth.email_from_token(None) == auth.DEV_USER
```

- [ ] **Step 3: Jalankan, pastikan gagal**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_auth.py`
Expected: FAIL, `ImportError: cannot import name 'auth' from 'server'`.

- [ ] **Step 4: Tulis `server/auth.py`**

```python
"""Identitas pengguna dari Cloudflare Access (spesifikasi web-upload bagian 8).

Cloudflare Access sudah menyaring pengguna di tepi (daftar email + kode sekali pakai). Di sini token
JWT-nya divalidasi lagi supaya salah konfigurasi di dashboard tidak membuka origin, dan supaya
diketahui siapa yang mengunggah atau menerbitkan.

    CF_ACCESS_TEAM_DOMAIN   https://<team>.cloudflareaccess.com (sama dengan klaim iss)
    CF_ACCESS_AUD           Application Audience (AUD) Tag aplikasi Access
    EUTOPOS_DEV_NO_AUTH=1   hanya untuk uji lokal: semua permintaan dianggap dev@local
"""

import os
from functools import lru_cache

import jwt
from fastapi import HTTPException, Request

HEADER = "Cf-Access-Jwt-Assertion"
DEV_USER = "dev@local"


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@lru_cache
def _jwks(team: str) -> jwt.PyJWKClient:
    # Kunci dirotasi Cloudflare tiap 6 minggu, PyJWKClient mengambil ulang kalau kid tidak dikenal.
    return jwt.PyJWKClient(f"{team}/cdn-cgi/access/certs", cache_keys=True)


def signing_key(token: str, team: str):
    return _jwks(team).get_signing_key_from_jwt(token).key


def email_from_token(token: str | None) -> str:
    if os.environ.get("EUTOPOS_DEV_NO_AUTH") == "1":
        return DEV_USER
    team = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "").rstrip("/")
    aud = os.environ.get("CF_ACCESS_AUD", "")
    if not (team and aud):
        # Gagal tertutup: tanpa konfigurasi, rute terlindungi tidak terbuka.
        raise AuthError(
            503, "autentikasi belum dikonfigurasi (CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD)"
        )
    if not token:
        raise AuthError(401, "tidak ada token Cloudflare Access")
    try:
        claims = jwt.decode(
            token, signing_key(token, team), algorithms=["RS256"], audience=aud, issuer=team
        )
    except jwt.PyJWTError as e:
        raise AuthError(403, f"token Cloudflare Access tidak sah: {e}") from e
    if not claims.get("email"):
        raise AuthError(403, "token tanpa email, service token tidak diizinkan")
    return claims["email"]


def current_user(request: Request) -> str:
    try:
        return email_from_token(request.headers.get(HEADER))
    except AuthError as e:
        raise HTTPException(e.status, e.message) from e
```

- [ ] **Step 5: Jalankan uji, pastikan lolos**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_auth.py`
Expected: 8 PASS.

- [ ] **Step 6: Lint lalu commit**

```bash
uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .
git add pyproject.toml uv.lock server/auth.py tests/test_auth.py
git commit -m "feat(server): validasi JWT Cloudflare Access, gagal tertutup tanpa konfigurasi"
```

---

### Task 2: Antrean menerima video unggahan dan membersihkan unggahan yang ditinggal

**Files:**
- Modify: `server/jobs.py` (`path` boleh kosong saat `uploading`, `expire_uploading`)
- Modify: `server/worker.py` (hapus juga `.info` tusd, panggil `expire_uploading` saat menganggur)
- Test: `tests/test_jobs.py`, `tests/test_worker.py`

**Interfaces:**
- Consumes: `server.jobs.*` dari PR 1.
- Produces:
  - Item `videos` untuk unggahan: `{"name": str, "role": str, "size": int, "upload_id": str | None, "path": str | None, "uploaded": bool}`
  - `server.jobs.expire_uploading(session, max_age: timedelta) -> list[MapJob]`
  - `server.worker.delete_upload_files(upload_ids: list[str], uploads: Path) -> None`

- [ ] **Step 1: Tulis uji yang gagal**

Tambahkan ke `tests/test_jobs.py`:

```python
def test_upload_job_may_have_no_path_yet(session):
    videos = [{"name": "a.mp4", "role": "peta", "size": 10, "upload_id": None, "path": None}]
    job = jobs.create_job(session, "floor10", "L10", "a@x.id", videos)
    assert job.status == "uploading"


def test_expire_uploading_fails_only_old_jobs(session):
    from datetime import UTC, datetime, timedelta

    old = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP])
    new = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP])
    old.created_at = datetime.now(UTC) - timedelta(hours=25)
    session.add(old)
    session.commit()
    expired = jobs.expire_uploading(session, timedelta(hours=24))
    assert [j.id for j in expired] == [old.id]
    assert session.get(MapJob, old.id).status == "failed"
    assert session.get(MapJob, new.id).status == "uploading"
```

Tambahkan ke `tests/test_worker.py`:

```python
def test_delete_upload_files_removes_data_and_info(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    for name in ["job1-v0-abc", "job1-v0-abc.info", "lain"]:
        (uploads / name).write_text("x")
    worker.delete_upload_files(["job1-v0-abc", "../lain"], uploads)
    assert sorted(p.name for p in uploads.iterdir()) == ["lain"]
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_jobs.py tests/test_worker.py`
Expected: FAIL (`TypeError` pada `Path(None)` di `create_job`, `AttributeError` untuk `expire_uploading` dan `delete_upload_files`).

- [ ] **Step 3: Ubah `server/jobs.py`**

Ganti baris pemeriksaan nama kembar:

```python
    # Frame dinamai <nama video>_<nomor>.jpg: dua video bernama sama saling menimpa frame.
    # Video unggahan belum punya path saat dibuat; namanya dibuat unik oleh server (ID unggahan).
    paths = [Path(v["path"]) for v in videos if v.get("path")]
    stems = [p.stem for p in paths if p.suffix]
```

Tambahkan di akhir berkas (dan `from datetime import UTC, datetime, timedelta` di import):

```python
def expire_uploading(session: Session, max_age: timedelta) -> list[MapJob]:
    """Unggahan yang ditinggal (spesifikasi bagian 10): uploading terlalu lama menjadi failed."""
    limit = datetime.now(UTC) - max_age
    stmt = select(MapJob).where(MapJob.status == "uploading", MapJob.created_at < limit)
    stale = session.exec(stmt).all()
    for job in stale:
        fail(session, job, "unggahan tidak selesai dalam 24 jam, buat sesi baru")
    return stale
```

Catatan: SQLite menyimpan `created_at` tanpa zona waktu. Kalau perbandingan di uji SQLite gagal karena itu, bandingkan dengan `limit.replace(tzinfo=None)` hanya untuk dialek SQLite (`session.get_bind().dialect.name == "sqlite"`), dan tulis alasannya di komentar.

- [ ] **Step 4: Ubah `server/worker.py`**

Tambahkan konstanta dan fungsi (import `re` dan `from datetime import timedelta`):

```python
UPLOAD_MAX_AGE = timedelta(hours=24)
UPLOAD_ID = re.compile(r"^[A-Za-z0-9-]+$")  # pola ID buatan server, tanpa / atau ..


def delete_upload_files(upload_ids: list[str], uploads: Path) -> None:
    """Hapus berkas tusd (data dan .info) untuk ID yang polanya sah. Berkas lain tidak disentuh."""
    for uid in upload_ids:
        if UPLOAD_ID.match(uid):
            for p in (uploads / uid, uploads / f"{uid}.info"):
                p.unlink(missing_ok=True)
```

Ganti isi `delete_uploaded_videos` supaya berkas `.info` ikut terhapus:

```python
def delete_uploaded_videos(videos: list[dict], uploads: Path) -> None:
    """Video mentah dari unggahan website dihapus setelah frame diekstrak (privasi). Berkas yang
    diberikan lewat CLI berada di luar folder uploads dan tidak pernah disentuh."""
    root = uploads.resolve()
    for v in videos:
        p = Path(v["path"]).resolve()
        if p.is_file() and p.is_relative_to(root):
            delete_upload_files([p.name], uploads)
```

Di `main`, ganti blok `if job is None:` dengan:

```python
            if job is None:
                for stale in jobs.expire_uploading(s, UPLOAD_MAX_AGE):
                    ids = [v["upload_id"] for v in stale.videos if v.get("upload_id")]
                    delete_upload_files(ids, DATA / "uploads")
                time.sleep(POLL_S)
                continue
```

- [ ] **Step 5: Jalankan uji, pastikan lolos**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q`
Expected: semua PASS (termasuk uji PR 1: video unggahan di `test_process_success_...` masih terhapus).

- [ ] **Step 6: Lint lalu commit**

```bash
uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .
git add server/jobs.py server/worker.py tests/test_jobs.py tests/test_worker.py
git commit -m "feat(server): antrean menerima video unggahan dan membersihkan unggahan yang ditinggal"
```

---

### Task 3: API pekerjaan dan hook tusd

**Files:**
- Create: `server/uploads.py`
- Modify: `server/app.py` (`app.include_router(uploads.router)`)
- Test: `tests/test_uploads.py`

**Interfaces:**
- Consumes: `server.auth.current_user`, `server.auth.email_from_token`, `server.auth.AuthError`, `server.auth.HEADER` (Task 1); `server.jobs.create_job` (Task 2).
- Produces:
  - `POST /api/jobs` body `{"area_id": str, "area_name": str, "videos": [{"name", "role", "size"}]}` -> 201 `JobOut`
  - `GET /api/jobs/{job_id}` -> `JobOut` (`id, area_id, status, stage, created_by, videos, summary, error, map_version_id`)
  - `POST /internal/tus-hook` (format hook HTTP tusd v2)
  - `server.uploads.UPLOADS = Path("/data/uploads")` (bisa diganti uji lewat `monkeypatch.setattr`)

- [ ] **Step 1: Tulis uji yang gagal (`tests/test_uploads.py`)**

```python
"""Uji API pekerjaan dan hook tusd, dengan SQLite dan mode autentikasi uji."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server import uploads
from server.db import MapJob

BODY = {
    "area_id": "floor10",
    "area_name": "Lantai 10",
    "videos": [
        {"name": "loop.mp4", "role": "peta", "size": 100},
        {"name": "uji.mp4", "role": "uji", "size": 50},
    ],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'u.db'}"
    SQLModel.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.setattr(uploads, "UPLOADS", tmp_path / "uploads")
    app = FastAPI()
    app.include_router(uploads.router)
    with TestClient(app) as c:
        c.db_url = url
        yield c


def hook(client, kind, job_id, name, size, upload_id=None, deferred=False):
    event = {
        "Upload": {
            "ID": upload_id,
            "Size": size,
            "SizeIsDeferred": deferred,
            "MetaData": {"job_id": str(job_id), "name": name},
        },
        "HTTPRequest": {"Header": {"Cf-Access-Jwt-Assertion": ["token"]}},
    }
    r = client.post("/internal/tus-hook", json={"Type": kind, "Event": event})
    assert r.status_code == 200, r.text
    return r.json()


def job_row(client, job_id):
    with Session(create_engine(client.db_url)) as s:
        return s.get(MapJob, job_id)


def test_full_upload_flow_queues_after_last_video(client, tmp_path):
    job = client.post("/api/jobs", json=BODY).json()
    assert job["status"] == "uploading" and job["created_by"] == "dev@local"

    ids = []
    for name, size in [("loop.mp4", 100), ("uji.mp4", 50)]:
        res = hook(client, "pre-create", job["id"], name, size)
        assert "RejectUpload" not in res
        ids.append(res["ChangeFileInfo"]["ID"])
    assert all(i.startswith(f"job{job['id']}-v") for i in ids)

    hook(client, "pre-finish", job["id"], "loop.mp4", 100, upload_id=ids[0])
    assert job_row(client, job["id"]).status == "uploading"  # masih menunggu video kedua
    hook(client, "pre-finish", job["id"], "uji.mp4", 50, upload_id=ids[1])

    row = job_row(client, job["id"])
    assert row.status == "queued"
    assert [v["path"] for v in row.videos] == [str(tmp_path / "uploads" / i) for i in ids]
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "queued"


@pytest.mark.parametrize(
    "name,size,deferred,status",
    [
        ("loop.mp4", 999, False, 400),  # ukuran berbeda dari yang didaftarkan
        ("loop.mp4", 0, True, 400),  # panjang tus ditunda
        ("lain.mp4", 100, False, 404),  # nama tidak terdaftar
    ],
    ids=["ukuran-beda", "panjang-ditunda", "nama-asing"],
)
def test_pre_create_rejects(client, name, size, deferred, status):
    job = client.post("/api/jobs", json=BODY).json()
    res = hook(client, "pre-create", job["id"], name, size, deferred=deferred)
    assert res["RejectUpload"] is True and res["HTTPResponse"]["StatusCode"] == status


def test_pre_create_rejects_other_user(client, monkeypatch):
    job = client.post("/api/jobs", json=BODY).json()
    monkeypatch.setattr(uploads.auth, "email_from_token", lambda token: "orang-lain@x.id")
    res = hook(client, "pre-create", job["id"], "loop.mp4", 100)
    assert res["RejectUpload"] is True and res["HTTPResponse"]["StatusCode"] == 403


def test_pre_finish_ignores_storage_path_from_hook(client, tmp_path):
    job = client.post("/api/jobs", json=BODY).json()
    uid = hook(client, "pre-create", job["id"], "loop.mp4", 100)["ChangeFileInfo"]["ID"]
    event = {
        "Upload": {"ID": uid, "Size": 100, "MetaData": {"job_id": str(job["id"])}},
        "Storage": {"Path": "/etc/passwd"},
    }
    client.post("/internal/tus-hook", json={"Type": "pre-finish", "Event": event})
    assert job_row(client, job["id"]).videos[0]["path"] == str(tmp_path / "uploads" / uid)


def test_create_job_validation(client):
    bad = {**BODY, "videos": [{"name": "a.mp4", "role": "uji", "size": 1}]}
    assert client.post("/api/jobs", json=bad).status_code == 422  # tanpa video peta
    twins = {**BODY, "videos": [BODY["videos"][0], BODY["videos"][0]]}
    assert client.post("/api/jobs", json=twins).status_code == 422  # nama kembar
    big = {**BODY, "videos": [{"name": "a.mp4", "role": "peta", "size": 3 * 1024**3}]}
    assert client.post("/api/jobs", json=big).status_code == 422  # lebih dari 2 GiB


def test_api_without_auth_config_is_closed(client, monkeypatch):
    monkeypatch.delenv("EUTOPOS_DEV_NO_AUTH")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    assert client.post("/api/jobs", json=BODY).status_code == 503
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_uploads.py`
Expected: FAIL, `ImportError: cannot import name 'uploads' from 'server'`.

- [ ] **Step 3: Tulis `server/uploads.py`**

```python
"""API pekerjaan bangun peta dan hook tusd (spesifikasi web-upload bagian 4 dan 8).

Alur: POST /api/jobs (status uploading) -> unggahan tus dengan metadata job_id dan name ->
hook pre-create (identitas, ID unggahan buatan server) -> hook pre-finish (tandai lengkap, queued
setelah video terakhir). /internal/* tidak dirutekan cloudflared, hanya tusd di jaringan internal.
"""

import json
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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
        raise HTTPException(503, "layanan berjalan tanpa database (EUTOPOS_MAP_DIR)")
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


class JobOut(BaseModel):
    id: int
    area_id: str
    status: str
    stage: str | None
    created_by: str
    videos: list[dict]
    summary: dict | None
    error: str | None
    map_version_id: int | None


@router.post("/api/jobs", status_code=201)
def create(body: JobIn, user: User, s: DB) -> JobOut:
    names = [v.name for v in body.videos]
    if len(set(names)) != len(names):
        raise HTTPException(422, "nama video kembar dalam satu pekerjaan")
    videos = [
        {**v.model_dump(), "upload_id": None, "path": None, "uploaded": False} for v in body.videos
    ]
    try:
        job = jobs.create_job(s, body.area_id, body.area_name, user, videos)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return JobOut.model_validate(job, from_attributes=True)


@router.get("/api/jobs/{job_id}")
def get(job_id: int, user: User, s: DB) -> JobOut:
    job = s.get(MapJob, job_id)
    if job is None:
        raise HTTPException(404, "pekerjaan tidak ada")
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


def _locked_job(s: Session, meta: dict) -> MapJob:
    try:
        job_id = int(meta.get("job_id", ""))
    except ValueError as e:
        raise HookReject(400, "metadata job_id tidak ada") from e
    # Kunci baris: dua video yang selesai bersamaan tidak saling menimpa daftar videos.
    stmt = select(MapJob).where(MapJob.id == job_id).with_for_update()
    job = s.exec(stmt).first()
    if job is None:
        raise HookReject(404, "pekerjaan tidak ada")
    return job


def _pre_create(s: Session, upload: dict, headers: dict) -> dict:
    try:
        email = auth.email_from_token(_header(headers, auth.HEADER))
    except auth.AuthError as e:
        raise HookReject(e.status, e.message) from e
    meta = upload.get("MetaData") or {}
    job = _locked_job(s, meta)
    if job.created_by != email:
        raise HookReject(403, "pekerjaan ini milik pengguna lain")
    if job.status != "uploading":
        raise HookReject(409, f"pekerjaan berstatus {job.status}, tidak menerima unggahan")
    idx = next((i for i, v in enumerate(job.videos) if v["name"] == meta.get("name")), None)
    if idx is None:
        raise HookReject(404, "nama video tidak terdaftar di pekerjaan ini")
    video = job.videos[idx]
    if video.get("uploaded"):
        raise HookReject(409, "video ini sudah lengkap diunggah")
    if upload.get("SizeIsDeferred") or upload.get("Size") != video["size"]:
        raise HookReject(400, "ukuran berkas berbeda dari yang didaftarkan")
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
    idx = next((i for i, v in enumerate(videos) if v["upload_id"] == upload.get("ID")), None)
    if idx is None:
        raise HookReject(404, "ID unggahan tidak dikenal")
    videos[idx] = {**videos[idx], "uploaded": True}
    job.videos = videos
    if job.status == "uploading" and all(v["uploaded"] for v in videos):
        job.status = "queued"
    s.add(job)
    s.commit()


@router.post("/internal/tus-hook")
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
```

Catatan: `RejectUpload` hanya berlaku di `pre-create`. Untuk `pre-finish`, tusd memakai `HTTPResponse` sebagai jawaban ke klien, jadi klien tetap menerima kode galat yang jelas.

- [ ] **Step 4: Daftarkan router di `server/app.py`**

Tambahkan `from server import uploads` di blok import server, dan setelah baris `app = FastAPI(title="eutopos-vps", lifespan=lifespan)`:

```python
app.include_router(uploads.router)
```

Tambahkan baris di docstring modul (bagian konfigurasi):

```text
    CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD   autentikasi /api/* (server/auth.py)
```

- [ ] **Step 5: Jalankan uji, pastikan lolos**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q`
Expected: semua PASS, termasuk `test_service_starts_without_active_map` (router baru tidak mengubah lifespan).

- [ ] **Step 6: Lint lalu commit**

```bash
uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .
git add server/uploads.py server/app.py tests/test_uploads.py
git commit -m "feat(server): API pekerjaan dan hook tusd pre-create dan pre-finish"
```

---

### Task 4: tusd di Compose, klien unggah CLI, dan verifikasi di PC lab

**Files:**
- Create: `server/upload_client.py` (klien tus berpotongan, stdlib saja)
- Modify: `deploy/compose.yaml` (layanan `tusd`, `/data` baca tulis untuk `api`)
- Modify: `deploy/.env.example` (`CF_ACCESS_*`, `EUTOPOS_DEV_NO_AUTH`)
- Modify: `deploy/README.md` (bagian unggahan)
- Modify: `docs/specs/2026-10-01-web-upload-and-map-build-design.md` (gagal tertutup per rute)

**Interfaces:**
- Consumes: `POST /api/jobs`, `GET /api/jobs/{id}` (Task 3).
- Produces: `python -m server.upload_client AREA NAME ROLE:PATH... [--api URL] [--tus URL] [--chunk-mb N]`

- [ ] **Step 1: Tulis `server/upload_client.py`**

```python
"""Unggah video ke eutopos lewat protokol tus, tanpa browser (stdlib saja).

Dipakai untuk menguji alur unggah di PC lab sebelum dashboard ada, dan untuk mengunggah dari skrip.
Potongan bawaan 50 MiB: di bawah batas 100 MB per permintaan Cloudflare Free.

    python -m server.upload_client floor10 "Lantai 10" peta:/data/inbox/loop.mp4 \
        --api http://api:8000 --tus http://tusd:8080/files/
"""

import argparse
import base64
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

TUS = {"Tus-Resumable": "1.0.0"}


def _request(method: str, url: str, headers: dict, data: bytes | None = None):
    token = os.environ.get("CF_ACCESS_TOKEN")  # opsional, lewat Tunnel nanti
    if token:
        headers = {**headers, "Cf-Access-Jwt-Assertion": token}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    return urllib.request.urlopen(req, timeout=300)


def _meta(**fields) -> str:
    return ",".join(f"{k} {base64.b64encode(v.encode()).decode()}" for k, v in fields.items())


def upload(path: Path, tus_url: str, job_id: int, chunk: int) -> None:
    size = path.stat().st_size
    headers = {**TUS, "Upload-Length": str(size)}
    headers["Upload-Metadata"] = _meta(job_id=str(job_id), name=path.name)
    with _request("POST", tus_url, headers) as r:
        location = urllib.parse.urljoin(tus_url, r.headers["Location"])
    offset = 0
    with path.open("rb") as f:
        while offset < size:
            data = f.read(chunk)
            headers = {**TUS, "Upload-Offset": str(offset)}
            headers["Content-Type"] = "application/offset+octet-stream"
            with _request("PATCH", location, headers, data) as r:
                offset = int(r.headers["Upload-Offset"])
            print(f"{path.name}: {offset * 100 // size}%", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("area_id")
    ap.add_argument("area_name")
    ap.add_argument("videos", nargs="+", help="peran:path, misalnya peta:/data/inbox/loop.mp4")
    ap.add_argument("--api", default="http://api:8000")
    ap.add_argument("--tus", default="http://tusd:8080/files/")
    ap.add_argument("--chunk-mb", type=int, default=50)
    a = ap.parse_args()
    items = [(role, Path(p)) for role, p in (v.split(":", 1) for v in a.videos)]
    body = {
        "area_id": a.area_id,
        "area_name": a.area_name,
        "videos": [{"name": p.name, "role": r, "size": p.stat().st_size} for r, p in items],
    }
    headers = {"Content-Type": "application/json"}
    with _request("POST", f"{a.api}/api/jobs", headers, json.dumps(body).encode()) as r:
        job = json.load(r)
    print(f"pekerjaan {job['id']} dibuat", flush=True)
    for _, p in items:
        upload(p, a.tus, job["id"], a.chunk_mb * 1024 * 1024)
    with _request("GET", f"{a.api}/api/jobs/{job['id']}", {}) as r:
        print(f"status pekerjaan {job['id']}: {json.load(r)['status']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Layanan `tusd` di `deploy/compose.yaml`**

Di layanan `api`, tambahkan bind data (baca tulis, untuk membuang sisa unggahan saat klien memulai ulang) dan variabel autentikasi:

```yaml
      - type: bind
        source: ${EUTOPOS_DATA_DIR:?isi EUTOPOS_DATA_DIR di deploy/.env}
        target: /data
        bind:
          create_host_path: false
```

```yaml
      CF_ACCESS_TEAM_DOMAIN: ${CF_ACCESS_TEAM_DOMAIN:-}
      CF_ACCESS_AUD: ${CF_ACCESS_AUD:-}
      EUTOPOS_DEV_NO_AUTH: ${EUTOPOS_DEV_NO_AUTH:-0}
```

Setelah layanan `worker`:

```yaml
  tusd:
    # Server tus resmi (MIT). Entrypoint image menjalankan "exec tusd $@", jadi command = flag tusd.
    image: tusproject/tusd:v2.10.1
    command:
      - -upload-dir=/data/uploads
      - -base-path=/files/
      - -behind-proxy
      - -disable-download  # video tidak bisa diambil kembali lewat Tunnel (ketentuan Cloudflare)
      - -max-size=2147483648  # 2 GiB, sama dengan MAX_VIDEO_BYTES di server/uploads.py
      - -hooks-http=http://api:8000/internal/tus-hook
      - -hooks-enabled-events=pre-create,pre-finish
    volumes:
      - type: bind
        source: ${EUTOPOS_DATA_DIR:?isi EUTOPOS_DATA_DIR di deploy/.env}
        target: /data
        bind:
          create_host_path: false
    # Sengaja tanpa "ports": diakses lewat cloudflared (PR 4) atau dari container lain.
    depends_on:
      api:
        condition: service_started
    restart: unless-stopped
```

- [ ] **Step 3: `.env.example`**

```text
# Cloudflare Access (PR 4). Tanpa keduanya, /api/* dan unggahan menjawab 503 (gagal tertutup).
# Isi di deploy/.env saja, jangan pernah di repo.
CF_ACCESS_TEAM_DOMAIN=
CF_ACCESS_AUD=
# 1 = tanpa autentikasi, HANYA untuk uji dari dalam PC lab sebelum Tunnel ada.
EUTOPOS_DEV_NO_AUTH=0
```

- [ ] **Step 4: README bagian unggahan, dan spesifikasi**

Tambahkan di `deploy/README.md` setelah bagian 4:

````markdown
## 5. Unggahan video (tusd)

Unggahan memakai protokol tus lewat container `tusd`, dengan hook ke `api` yang memeriksa identitas
Cloudflare Access dan mencatat video ke pekerjaan. Sebelum Tunnel (PR 4) ada, uji dari dalam PC lab
dengan `EUTOPOS_DEV_NO_AUTH=1` di `deploy/.env`, lalu kembalikan ke `0`.

```bash
mkdir -p ~/eutopos-data/work/uploads
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose exec worker python -m server.upload_client floor10 "Lantai 10" \
  peta:/data/inbox/floor10-20261001-loop/loop-inward.mp4
docker compose exec worker python -m server.manage jobs
```

Klien mengunggah dalam potongan 50 MiB, sama dengan dashboard nanti. Video unggahan dihapus pekerja
setelah frame diekstrak. Pekerjaan `uploading` lebih dari 24 jam ditandai gagal dan sisa unggahannya
dihapus.
````

Di spesifikasi bagian 8, ganti kalimat "Gagal tertutup: tanpa ... layanan menolak menyala, kecuali ..." dengan:

```markdown
  **Gagal tertutup per rute:** tanpa `CF_ACCESS_TEAM_DOMAIN` dan `CF_ACCESS_AUD`, `/api/*` dan hook
  `pre-create` menjawab 503, sementara `/localize` dan `/health` tetap jalan supaya layanan yang
  sudah berjalan tidak mati sebelum Tunnel ada. `EUTOPOS_DEV_NO_AUTH=1` hanya untuk uji lokal.
```

- [ ] **Step 5: Verifikasi di laptop**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q && uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .`
Expected: semua PASS, ruff bersih. `python -m server.upload_client --help` mencetak bantuan.

- [ ] **Step 6: Verifikasi di PC lab (pemilik menjalankan, hasil ditempel ke sesi)**

Branch sudah di-push atas perintah pemilik. Video uji harus ada di `~/eutopos-data/work/inbox/` (misalnya
`loop-inward.mp4` dari laptop). Di Ubuntu:

```bash
cd ~/eutopos-vps && git fetch && git switch feat/upload-auth
echo 'EUTOPOS_DEV_NO_AUTH=1' >> deploy/.env
mkdir -p ~/eutopos-data/work/uploads
cd deploy && docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose exec worker python -m server.upload_client floor10 "Lantai 10" \
  peta:/data/inbox/floor10-20261001-loop/loop-inward.mp4
docker compose exec worker python -m server.manage jobs
```

Expected:
- Klien mencetak `pekerjaan N dibuat`, persen naik per potongan 50 MiB, lalu `status pekerjaan N: queued`.
- `ls ~/eutopos-data/work/uploads/` menunjukkan `jobN-v0-...` dan `.info` selama belum diproses, lalu kosong setelah tahap `extract`.
- `manage jobs` menunjukkan pekerjaan berjalan sampai `done`.
- **Uji lanjut setelah putus:** jalankan klien dengan video besar, hentikan dengan Ctrl+C di tengah, lalu periksa `ls -la ~/eutopos-data/work/uploads/` (berkas parsial ada). Catatan: klien CLI ini tidak menyimpan lokasi unggahan, jadi melanjutkan dari offset diuji di PR 3 dengan Uppy di browser. Di sini cukup dipastikan pekerjaan yang ditinggal tetap `uploading` dan tidak `queued`.
- Kembalikan `EUTOPOS_DEV_NO_AUTH=0` lalu `docker compose up -d`. `curl -s -o /dev/null -w '%{http_code}' -X POST localhost:8000/api/jobs` menjawab `503` (gagal tertutup), sementara `curl -s localhost:8000/health` tetap `200`.

- [ ] **Step 7: Commit**

```bash
git add server/upload_client.py deploy/compose.yaml deploy/.env.example deploy/README.md docs/specs/2026-10-01-web-upload-and-map-build-design.md
git commit -m "feat(deploy): tusd di Compose dan klien unggah tus untuk uji tanpa browser"
```
