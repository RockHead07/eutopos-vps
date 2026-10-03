# Dashboard Website Unggah Video (PR 3) Implementation Plan

**Status:** dieksekusi. PR 3a (Task 1-3) merged sebagai #31, PR 3b (Task 4-7) merged sebagai #32. Menyimpang dari
rencana setelah review: Terbitkan memuat peta dulu baru menulis `published` (versi gagal tetap `candidate`,
bukan `rejected`), Terbitkan ditolak 409 selama memuat dan 415 kalau bukan JSON, unggah dinilai dari
server, dan antarmuka berbahasa Inggris. Rinciannya di deskripsi PR #31 dan #32.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dari browser (termasuk HP) lewat `eutopos.rockhead07.tech`: unggah video dengan progress, lihat status pekerjaan, ringkasan dan tampilan 3D peta, lalu tekan **Terbitkan** supaya `/localize` memakai versi baru tanpa restart.

**Architecture:** Dua PR. **PR 3a (backend):** daftar pekerjaan, daftar versi peta, laporan 3D per versi, endpoint Terbitkan yang memuat peta baru di thread latar lalu menukarnya di bawah kunci yang sudah ada (spesifikasi bagian 7), dan `plotly.min.js` disajikan sekali. **PR 3b (web):** Next.js static export (empat halaman) dengan Uppy 6 + `@uppy/tus` (potongan 50 MiB), dibangun di tahap Node pada Dockerfile dan disajikan FastAPI dari `web/out`.

**Tech Stack:** FastAPI, SQLModel, Next.js 16.3.8 (App Router, `output: 'export'`), React 19.3.0, TypeScript 5.9.3, Uppy 6 (`@uppy/core` 6.2.0, `@uppy/react` 6.0.0, `@uppy/dashboard` 6.0.1, `@uppy/tus` 6.0.0), Node 24.21.0.

**Spec:** `docs/specs/2026-10-01-web-upload-and-map-build-design.md` bagian 7 dan 9. Riset: `docs/web-upload-research.md` bagian 6 (plotly) dan 8 (Next.js static export).

## Global Constraints

- **Versi diverifikasi 2026-10-02** (npm registry dan context7): `next` 16.3.8 (Node ≥ 20.9.0), `react`/`react-dom` 19.3.0, `typescript` 5.9.3 (bukan 7.x), `@uppy/*` 6.x. Image `node:24.21.0-bookworm-slim`. `actions/setup-node` v7.0.0 = `820762786026740c76f36085b0efc47a31fe5020`.
- **Uppy 6:** komponen React diimpor dari `@uppy/react/dashboard` (peta `exports` paket hanya membuka jalur itu; contoh dokumentasi `@uppy/react/lib/Dashboard` tidak jalan di v6). CSS: `@uppy/core/css/style.min.css` dan `@uppy/dashboard/css/style.min.css`.
- **Next.js static export:** `output: 'export'`, `trailingSlash: true`. Rute dinamis lewat parameter query (`/job/?id=3`). Komponen klien yang memakai `useSearchParams` wajib dibungkus `<Suspense>` (tanpa itu `next build` gagal).
- Tus: `endpoint: "/files/"`, `chunkSize: 50 * 1024 * 1024` (batas Cloudflare Free 100 MB per permintaan), `allowedMetaFields: ["job_id", "name"]` (hook `pre-create` mencocokkan `name` dengan video yang didaftarkan).
- Semua `fetch` ke asal yang sama. Cookie Access dikirim browser, tepi Cloudflare menambahkan `Cf-Access-Jwt-Assertion`. Tanpa CORS.
- **Teks antarmuka bahasa Indonesia**, tanpa em dash. Nama berkas, fungsi, opsi bahasa Inggris.
- Ruff 0.16.9 (baris 100). Uji Python: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q`.
- Laporan 3D baru merujuk `/assets/plotly.min.js` (±4,8 MB, sekali), bukan menyematkan plotly di setiap laporan.
- Commit per tugas setelah eksekusi disetujui. Push hanya atas perintah terpisah. Tanpa atribusi AI.

## Review Focus

1. **Sesi Access habis saat halaman terbuka:** `fetch` diarahkan ke halaman login lintas asal dan gagal sebagai galat jaringan. Pengguna harus melihat pesan "muat ulang halaman", bukan halaman diam. Pemilik: Task 4 (`lib/api.ts`), diuji manual Task 7.
2. **Peta yang diterbitkan gagal dimuat** (berkas rusak, GPU penuh): `/localize` tetap memakai peta lama, versi aktif di database dikembalikan, dan halaman Peta menampilkan galatnya. Pemilik: Task 1 (uji).
3. **Menerbitkan versi area lain** dari yang dilayani (`EUTOPOS_AREA`): database berubah, layanan tidak memuat ulang, dan respons mengatakannya dengan jelas. Pemilik: Task 2 (uji).
4. **Tab ditutup di tengah unggahan:** pekerjaan tertinggal `uploading`, kedaluwarsa 24 jam (PR 2). Di v1 tidak ada lanjut lintas sesi; `storeFingerprintForResuming: false` mencegah tus melanjutkan unggahan lama ke pekerjaan baru. Pemilik: Task 5, diuji manual Task 7.
5. **Jalur laporan di luar `/maps`** (data database rusak): endpoint laporan menolak 404, tidak menyajikan berkas lain. Pemilik: Task 2 (uji).

---

## PR 3a: Backend dashboard

Branch `feat/dashboard` (worktree `D:/wt/dashboard`, dari `main` setelah PR 4).

### Task 1: Peta aktif dan pemuatan ulang setelah Terbitkan

**Files:**
- Create: `server/active_map.py`
- Modify: `server/app.py` (memakai `active_map`, kunci dibuat sebelum memuat peta)
- Test: `tests/test_active_map.py`

**Interfaces:**
- Produces:
  - `server.active_map.load_localizer(map_dir: Path) -> Localizer` (pindahan `app._load_localizer`)
  - `server.active_map.serving_area() -> str` (`EUTOPOS_AREA`, bawaan `"demo"`)
  - `server.active_map.reload_in_background(state, engine, version_id: int, previous_id: int | None) -> threading.Thread`
  - Atribut `app.state`: `localizer`, `area_id`, `map_version`, `lock`, `reloading: bool`, `reload_error: str | None`

- [ ] **Step 1: Tulis uji yang gagal (`tests/test_active_map.py`)**

```python
"""Uji pemuatan ulang peta aktif dengan pemuat palsu (tanpa model, tanpa GPU)."""

import threading
from types import SimpleNamespace

import pytest
from sqlmodel import Session, SQLModel, create_engine

from server import active_map
from server.db import MapVersion, active_version, publish, register


@pytest.fixture
def engine(tmp_path):
    e = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    SQLModel.metadata.create_all(e)
    return e


def state():
    return SimpleNamespace(
        localizer="lama",
        area_id="floor10",
        map_version=1,
        lock=threading.Lock(),
        reloading=False,
        reload_error=None,
    )


def versions(engine):
    with Session(engine) as s:
        v1 = register(s, "floor10", "L10", "/maps/floor10/job-1")
        v2 = register(s, "floor10", "L10", "/maps/floor10/job-2")
        publish(s, v1.id)
        publish(s, v2.id)  # yang diterbitkan pengguna
        return v1.id, v2.id


def test_reload_swaps_localizer(engine, monkeypatch):
    v1, v2 = versions(engine)
    monkeypatch.setattr(active_map, "load_localizer", lambda path: f"baru:{path.name}")
    st = state()
    active_map.reload_in_background(st, engine, v2, v1).join(5)
    assert (st.localizer, st.map_version, st.reloading, st.reload_error) == (
        "baru:job-2",
        2,
        False,
        None,
    )


def test_failed_load_keeps_old_map_and_restores_version(engine, monkeypatch):
    v1, v2 = versions(engine)

    def broken(path):
        raise RuntimeError("berkas peta rusak")

    monkeypatch.setattr(active_map, "load_localizer", broken)
    st = state()
    active_map.reload_in_background(st, engine, v2, v1).join(5)
    assert (st.localizer, st.map_version, st.reloading) == ("lama", 1, False)
    assert "versi 2" in st.reload_error
    with Session(engine) as s:
        assert active_version(s, "floor10").id == v1
        assert s.get(MapVersion, v2).status == "rejected"
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_active_map.py`
Expected: FAIL, `ImportError: cannot import name 'active_map' from 'server'`.

- [ ] **Step 3: Tulis `server/active_map.py`**

```python
"""Peta aktif yang dimuat /localize, dan penukarannya setelah Terbitkan (spesifikasi bagian 7).

Peta baru dimuat di thread latar. Selama memuat, /localize tetap memakai peta lama. Kalau gagal,
peta lama tetap dipakai, versi aktif di database dikembalikan, dan galatnya ditampilkan dashboard.
"""

import logging
import os
import threading
from pathlib import Path

from sqlmodel import Session

from server.db import MapVersion, publish
from server.localizer import MIN_INLIERS, Localizer

log = logging.getLogger("eutopos")


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def serving_area() -> str:
    return os.environ.get("EUTOPOS_AREA", "demo")


def load_localizer(map_dir: Path) -> Localizer:
    return Localizer(
        map_dir,
        max_kp=_env_int("EUTOPOS_MAX_KP", 1024),
        resize=_env_int("EUTOPOS_RESIZE", 1024),
        global_resize=_env_int("EUTOPOS_GLOBAL_RESIZE", 512),
        k=_env_int("EUTOPOS_K", 5),
        device=os.environ.get("EUTOPOS_DEVICE", "cpu"),
        min_inliers=_env_int("EUTOPOS_MIN_INLIERS", MIN_INLIERS),
    )


def reload_in_background(state, engine, version_id: int, previous_id: int | None):
    """ponytail: memuat ulang seluruh model untuk peta baru (beberapa detik, memori sementara dua
    kali lipat). Pakai ulang model yang sudah dimuat kalau penukaran jadi sering."""
    state.reloading = True

    def run():
        with Session(engine) as s:
            v = s.get(MapVersion, version_id)
            try:
                localizer = load_localizer(Path(v.path))
            except Exception as e:
                log.exception("gagal memuat versi peta %s", version_id)
                if previous_id is not None:
                    publish(s, previous_id)  # versi lama aktif lagi
                v = s.get(MapVersion, version_id)
                v.status = "rejected"
                s.add(v)
                s.commit()
                state.reload_error = (
                    f"versi {v.version} gagal dimuat ({e}), peta lama tetap dipakai"
                )
                state.reloading = False
                return
            with state.lock:
                state.localizer, state.area_id, state.map_version = localizer, v.area_id, v.version
            state.reload_error, state.reloading = None, False

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t
```

- [ ] **Step 4: Ubah `server/app.py`**

Hapus fungsi `_load_localizer` dan `_env_int` (pindah ke `active_map`), tambahkan `from server import active_map, uploads` (ganti `from server import uploads`), dan hapus `MIN_INLIERS` dari impor `server.localizer` (sisakan `Localizer`). Ganti isi `lifespan`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    if threads := int(os.environ.get("EUTOPOS_THREADS", 0)):
        torch.set_num_threads(threads)
    st = app.state
    st.area_id = st.map_version = st.localizer = st.reload_error = None
    st.reloading = False
    # ponytail: satu lokalisasi dalam satu waktu. Model torch dipakai bersama dan server kecil
    # (2 vCPU). Kalau antrean permintaan jadi masalah, jalankan beberapa proses pekerja.
    st.lock = threading.Lock()
    if os.environ.get("DATABASE_URL"):
        with Session(engine_from_env()) as s:
            v = active_version(s, active_map.serving_area())
        map_dir = Path(v.path) if v else None
        if v:
            st.area_id, st.map_version = v.area_id, v.version
    else:
        map_dir = Path(os.environ["EUTOPOS_MAP_DIR"])
    if map_dir is not None:
        st.localizer = active_map.load_localizer(map_dir)
    yield
```

Di `localize`, ganti dua baris yang membaca `request.app.state.area_id` dan `map_version` di akhir supaya diambil bersama `loc` di bawah kunci (peta bisa tertukar di tengah permintaan):

```python
    st = request.app.state
    with st.lock:
        loc, area_id, map_version = st.localizer, st.area_id, st.map_version
    if loc is None:
        raise HTTPException(503, "belum ada versi peta aktif untuk area ini")
```

(baris `loc: Localizer | None = request.app.state.localizer` dan pemeriksaan `None` yang lama diganti blok di atas), lalu `with st.lock: r = loc.localize(rgb, camera)`, dan di `LocalizeResponse(...)` pakai `area_id=area_id, map_version=map_version`.

- [ ] **Step 5: Jalankan semua uji, pastikan lolos**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q`
Expected: semua PASS, termasuk `test_service_starts_without_active_map`.

- [ ] **Step 6: Lint lalu commit**

```bash
uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .
git add server/active_map.py server/app.py tests/test_active_map.py
git commit -m "feat(server): peta aktif dimuat ulang di latar setelah Terbitkan"
```

---

### Task 2: API dashboard (daftar, versi, laporan, Terbitkan)

**Files:**
- Modify: `server/uploads.py` (`GET /api/jobs`)
- Create: `server/maps_api.py`
- Modify: `server/app.py` (`app.include_router(maps_api.router)`)
- Test: `tests/test_maps_api.py`

**Interfaces:**
- Consumes: `active_map.reload_in_background`, `active_map.serving_area` (Task 1); `uploads.get_session`, `uploads._engine`, `uploads.JobOut`, `auth.current_user`.
- Produces:
  - `GET /api/jobs?limit=50` -> `list[JobOut]` (terbaru dulu)
  - `GET /api/versions` -> `list[VersionOut]` dengan `id, area_id, version, status, created_at, published_by, job_id, has_report`
  - `GET /api/versions/{id}/report` -> `report.html` (404 kalau tidak ada atau jalur di luar `MAPS_ROOT`)
  - `POST /api/versions/{id}/publish` -> `{"version": VersionOut, "reload": "started" | "other_area"}`
  - `GET /api/service` -> `{"area_id", "map_version", "reloading", "reload_error"}`
  - `GET /assets/plotly.min.js` (tanpa autentikasi asal, pustaka publik)
  - `server.maps_api.MAPS_ROOT = Path("/maps")` (bisa diganti uji)

- [ ] **Step 1: Tulis uji yang gagal (`tests/test_maps_api.py`)**

```python
"""Uji API dashboard dengan SQLite, mode autentikasi uji, dan pemuat peta palsu."""

import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server import active_map, jobs, maps_api, uploads
from server.db import register


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    SQLModel.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("EUTOPOS_DEV_NO_AUTH", "1")
    monkeypatch.setenv("EUTOPOS_AREA", "floor10")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    monkeypatch.setattr(maps_api, "MAPS_ROOT", tmp_path / "maps")
    monkeypatch.setattr(active_map, "load_localizer", lambda path: f"loc:{path.name}")
    app = FastAPI()
    app.include_router(uploads.router)
    app.include_router(maps_api.router)
    st = app.state
    st.localizer, st.area_id, st.map_version, st.lock = None, None, None, threading.Lock()
    st.reloading, st.reload_error = False, None
    with TestClient(app) as c:
        c.db = Session(create_engine(url))
        c.maps = tmp_path / "maps"
        c.st = st
        yield c


def make_version(client, area="floor10", job=True, report=True):
    d = client.maps / area / f"job-{len(list(client.maps.glob('*/*'))) + 1}"
    d.mkdir(parents=True)
    if report:
        (d / "report.html").write_text("<html>laporan</html>")
    v = register(client.db, area, "Lantai 10", str(d))
    if job:
        j = jobs.create_job(client.db, area, "L10", "dev@local", [{"path": "/x", "role": "peta"}])
        jobs.finish(client.db, j, v.id, {"inspect": {"parts": []}})
    return v


def wait_reload(st):
    for _ in range(100):
        if not st.reloading:
            return
        time.sleep(0.02)


def test_lists_jobs_newest_first(client):
    make_version(client)
    make_version(client)
    ids = [j["id"] for j in client.get("/api/jobs").json()]
    assert ids == sorted(ids, reverse=True) and len(ids) == 2


def test_versions_have_job_and_report(client):
    v = make_version(client)
    make_version(client, job=False, report=False)
    rows = {r["id"]: r for r in client.get("/api/versions").json()}
    assert rows[v.id]["job_id"] is not None and rows[v.id]["has_report"] is True
    assert client.get(f"/api/versions/{v.id}/report").text == "<html>laporan</html>"


def test_report_outside_maps_root_is_404(client, tmp_path):
    outside = tmp_path / "rahasia"
    outside.mkdir()
    (outside / "report.html").write_text("jangan")
    v = register(client.db, "floor10", "L10", str(outside))
    assert client.get(f"/api/versions/{v.id}/report").status_code == 404


def test_publish_reloads_served_area(client):
    v = make_version(client)
    r = client.post(f"/api/versions/{v.id}/publish").json()
    assert r["reload"] == "started" and r["version"]["published_by"] == "dev@local"
    wait_reload(client.st)
    s = client.get("/api/service").json()
    assert (s["area_id"], s["map_version"], s["reload_error"]) == ("floor10", v.version, None)
    assert client.st.localizer.startswith("loc:job-")


def test_publish_other_area_does_not_reload(client):
    v = make_version(client, area="floor9")
    r = client.post(f"/api/versions/{v.id}/publish").json()
    assert r["reload"] == "other_area" and r["version"]["status"] == "published"
    assert client.st.localizer is None


def test_plotly_asset_is_served(client):
    r = client.get("/assets/plotly.min.js")
    assert r.status_code == 200 and len(r.content) > 1_000_000
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_maps_api.py`
Expected: FAIL, `ImportError: cannot import name 'maps_api' from 'server'`.

- [ ] **Step 3: Tambah `GET /api/jobs` di `server/uploads.py`**

Setelah fungsi `create`:

```python
@router.get("/api/jobs")
def list_jobs(user: User, s: DB, limit: int = Query(50, ge=1, le=200)) -> list[JobOut]:
    stmt = select(MapJob).order_by(MapJob.id.desc()).limit(limit)
    return [JobOut.model_validate(j, from_attributes=True) for j in s.exec(stmt)]
```

- [ ] **Step 4: Tulis `server/maps_api.py`**

```python
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
    previous = active_of(s, v.area_id)
    v = publish(s, version_id, by=user)
    st = request.app.state
    if v.area_id != active_map.serving_area():
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
```

Di `server/app.py`: `from server import active_map, maps_api, uploads` dan `app.include_router(maps_api.router)` setelah `uploads.router`.

- [ ] **Step 5: Jalankan semua uji, pastikan lolos**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q`
Expected: semua PASS.

- [ ] **Step 6: Lint lalu commit**

```bash
uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .
git add server/uploads.py server/maps_api.py server/app.py tests/test_maps_api.py
git commit -m "feat(server): API dashboard untuk daftar pekerjaan, versi peta, laporan, dan Terbitkan"
```

---

### Task 3: Laporan 3D merujuk plotly.min.js yang disajikan sekali

**Files:**
- Modify: `spike/inspect_map.py` (opsi `--plotly-url`)
- Modify: `server/pipeline.py` (`inspect_command` mengirim `--plotly-url /assets/plotly.min.js`)
- Test: `tests/test_worker.py`

**Interfaces:**
- Produces: `inspect_map.py RUN_DIR --html PATH --plotly-url URL` menulis HTML yang memuat plotly dari `URL` (tanpa opsi: plotly disematkan seperti sebelumnya, untuk dibuka luring di laptop).

- [ ] **Step 1: Tulis uji yang gagal (tambah ke `tests/test_worker.py`)**

```python
def test_inspect_command_links_plotly_once(tmp_path):
    cmd = pipeline.inspect_command(tmp_path / "map")
    assert cmd[cmd.index("--plotly-url") + 1] == "/assets/plotly.min.js"
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_worker.py -k plotly`
Expected: FAIL, `ValueError: '--plotly-url' is not in list`.

- [ ] **Step 3: Implementasi**

Di `server/pipeline.py`, tambahkan konstanta dan dua elemen di akhir daftar `inspect_command`:

```python
PLOTLY_URL = "/assets/plotly.min.js"  # disajikan server/maps_api.py
```

```python
        "--json",
        str(map_dir / "inspect.json"),
        "--plotly-url",
        PLOTLY_URL,
    ]
```

Di `spike/inspect_map.py`, tambah argumen setelah `--html`:

```python
    ap.add_argument("--plotly-url", help="muat plotly dari URL ini, bukan disematkan")
```

Ubah pemanggilan `save_html(a.html, main_model, located)` menjadi `save_html(a.html, main_model, located, a.plotly_url)`, tanda tangan fungsi menjadi `def save_html(path: Path, model, located, plotly_url: str | None = None):`, dan baris tulisnya:

```python
    # Tanpa URL: plotly disematkan (±4,8 MB) supaya bisa dibuka tanpa internet di laptop.
    fig.write_html(path, include_plotlyjs=plotly_url or True)
```

- [ ] **Step 4: Jalankan uji dan coba di data demo**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q`
Expected: semua PASS.

Run: `/d/Dev/Projects/eutopos-vps/.venv/Scripts/python.exe spike/inspect_map.py /d/Dev/Projects/eutopos-vps/outputs/bench-verify/kp1024-r1024 --html "$TMP/r.html" --plotly-url /assets/plotly.min.js && ls -la "$TMP/r.html" && grep -c 'src="/assets/plotly.min.js"' "$TMP/r.html"`
Expected: ukuran berkas di bawah 300 KB, `grep` mencetak `1`.

- [ ] **Step 5: Lint lalu commit**

```bash
uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .
git add spike/inspect_map.py server/pipeline.py tests/test_worker.py
git commit -m "feat(server): laporan 3D merujuk plotly.min.js yang disajikan sekali"
```

PR 3a selesai: review independen seluruh branch, push atas perintah, PR, merge. Verifikasi PC lab cukup lewat browser setelah PR 3b (API tanpa tampilan bisa dicek dengan `curl` di dalam PC lab memakai `EUTOPOS_DEV_NO_AUTH` hanya kalau `CF_ACCESS_*` dikosongkan sementara; tidak wajib).

---

## PR 3b: Web dashboard

Branch `feat/dashboard-web` dari `main` setelah PR 3a.

### Task 4: Kerangka Next.js, klien API, dan halaman daftar pekerjaan

**Files:**
- Create: `web/package.json`, `web/package-lock.json` (oleh npm), `web/next.config.ts`, `web/tsconfig.json`, `web/app/layout.tsx`, `web/app/globals.css`, `web/app/page.tsx`, `web/lib/api.ts`, `web/lib/usePoll.ts`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `api.jobs()`, `api.job(id)`, `api.createJob(body)`, `api.versions()`, `api.publish(id)`, `api.service()`; tipe `Job`, `Video`, `Summary`, `Version`, `ServiceStatus`; hook `usePoll(load, ms, deps)` -> `{ data, error }`.

- [ ] **Step 1: `web/package.json` lalu pasang dependensi dengan versi persis**

```json
{
  "name": "eutopos-dashboard",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build"
  }
}
```

```bash
cd web
npm install --save-exact next@16.3.8 react@19.3.0 react-dom@19.3.0 @uppy/core@6.2.0 @uppy/react@6.0.0 @uppy/dashboard@6.0.1 @uppy/tus@6.0.0
npm install --save-exact --save-dev typescript@5.9.3 @types/node@24 @types/react@19 @types/react-dom@19
```

Expected: `package.json` berisi versi persis, `package-lock.json` terbuat.

- [ ] **Step 2: Konfigurasi**

`web/next.config.ts`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Disajikan FastAPI dari web/out. Tanpa server Node: rute dinamis lewat parameter query.
  output: "export",
  trailingSlash: true,
};

export default nextConfig;
```

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "strict": true,
    "noEmit": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "skipLibCheck": true,
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

Tambahkan ke `.gitignore` akar repo:

```text
# Dashboard (Next.js)
web/node_modules/
web/.next/
web/out/
web/next-env.d.ts
```

- [ ] **Step 3: `web/lib/api.ts`**

```ts
export type Video = { name: string; role: "peta" | "uji"; size: number; uploaded: boolean };
export type Summary = {
  run?: { map_images?: number; map_registered?: number; queries?: number; queries_localized?: number };
  inspect?: {
    parts?: { label: string; frames: number; ranges: string[] }[];
    queries?: number;
    accepted?: number;
    min_inliers?: number;
  };
};
export type Job = {
  id: number;
  area_id: string;
  status: string;
  stage: string | null;
  created_by: string;
  videos: Video[];
  summary: Summary | null;
  error: string | null;
  map_version_id: number | null;
};
export type Version = {
  id: number;
  area_id: string;
  version: number;
  status: string;
  created_at: string;
  published_by: string | null;
  job_id: number | null;
  has_report: boolean;
};
export type ServiceStatus = {
  area_id: string | null;
  map_version: number | null;
  reloading: boolean;
  reload_error: string | null;
};
export type NewJob = {
  area_id: string;
  area_name: string;
  videos: { name: string; role: "peta" | "uji"; size: number }[];
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(path, { ...init, headers: { "Content-Type": "application/json" } });
  } catch {
    // Sesi Cloudflare Access habis: permintaan diarahkan ke halaman login lain asal dan gagal.
    throw new Error("Tidak bisa menghubungi server. Kalau sesi login habis, muat ulang halaman.");
  }
  if (!r.ok) {
    let detail = `galat ${r.status}`;
    try {
      const body = await r.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new Error(detail);
  }
  return (await r.json()) as T;
}

export const api = {
  jobs: () => call<Job[]>("/api/jobs"),
  job: (id: number) => call<Job>(`/api/jobs/${id}`),
  createJob: (body: NewJob) => call<Job>("/api/jobs", { method: "POST", body: JSON.stringify(body) }),
  versions: () => call<Version[]>("/api/versions"),
  publish: (id: number) =>
    call<{ version: Version; reload: "started" | "other_area" }>(`/api/versions/${id}/publish`, {
      method: "POST",
    }),
  service: () => call<ServiceStatus>("/api/service"),
};

export const STATUS: Record<string, string> = {
  uploading: "mengunggah",
  queued: "antre",
  running: "diproses",
  done: "selesai",
  failed: "gagal",
  candidate: "kandidat",
  published: "aktif",
  retired: "lama",
  rejected: "ditolak",
};

export const mb = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(0)} MB`;
```

- [ ] **Step 4: `web/lib/usePoll.ts`**

```ts
"use client";
import { useEffect, useState } from "react";

/** Muat data sekarang lalu tiap `ms` milidetik. Berhenti saat komponen dilepas. */
export function usePoll<T>(load: () => Promise<T>, ms: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      load()
        .then((d) => alive && (setData(d), setError(null)))
        .catch((e: Error) => alive && setError(e.message));
    tick();
    const timer = setInterval(tick, ms);
    return () => {
      alive = false;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}
```

- [ ] **Step 5: Tata letak, gaya, halaman daftar**

`web/app/layout.tsx`:

```tsx
import Link from "next/link";
import "./globals.css";

export const metadata = { title: "eutopos" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>
        <nav>
          <strong>eutopos</strong>
          <Link href="/">Pekerjaan</Link>
          <Link href="/new/">Sesi peta baru</Link>
          <Link href="/maps/">Versi peta</Link>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
```

`web/app/globals.css`:

```css
body { margin: 0; font-family: system-ui, sans-serif; color: #1c1c1c; background: #f7f7f5; }
nav { display: flex; gap: 1rem; align-items: center; padding: 0.75rem 1rem; background: #fff; border-bottom: 1px solid #ddd; flex-wrap: wrap; }
nav a { color: #1a56b0; text-decoration: none; }
main { max-width: 960px; margin: 0 auto; padding: 1rem; }
table { width: 100%; border-collapse: collapse; background: #fff; }
th, td { text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid #eee; font-size: 0.95rem; }
.badge { padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.8rem; background: #e8e8e8; }
.badge.done, .badge.published { background: #d6f2dc; }
.badge.failed, .badge.rejected { background: #f8d7d7; }
.badge.running, .badge.uploading, .badge.queued { background: #fff1c2; }
.error { color: #a40000; white-space: pre-wrap; }
button { padding: 0.4rem 0.9rem; cursor: pointer; }
iframe { width: 100%; height: 70vh; border: 1px solid #ddd; background: #fff; }
label { display: block; margin: 0.5rem 0; }
```

`web/app/page.tsx`:

```tsx
"use client";
import Link from "next/link";
import { api, STATUS } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function JobsPage() {
  const { data: jobs, error } = usePoll(api.jobs, 5000);
  return (
    <>
      <h1>Pekerjaan bangun peta</h1>
      {error && <p className="error">{error}</p>}
      {jobs && jobs.length === 0 && <p>Belum ada pekerjaan. Mulai dari Sesi peta baru.</p>}
      {jobs && jobs.length > 0 && (
        <table>
          <thead>
            <tr><th>#</th><th>Area</th><th>Status</th><th>Tahap</th><th>Oleh</th></tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td><Link href={`/job/?id=${j.id}`}>{j.id}</Link></td>
                <td>{j.area_id}</td>
                <td><span className={`badge ${j.status}`}>{STATUS[j.status] ?? j.status}</span></td>
                <td>{j.stage ?? "-"}</td>
                <td>{j.created_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
```

- [ ] **Step 6: Build**

Run: `cd web && npm run build`
Expected: build sukses, folder `web/out/` berisi `index.html`. (Halaman lain menyusul di Task 5 dan 6.)

- [ ] **Step 7: Commit**

```bash
git add .gitignore web/package.json web/package-lock.json web/next.config.ts web/tsconfig.json web/app web/lib
git commit -m "feat(web): kerangka dashboard Next.js static export dan halaman daftar pekerjaan"
```

---

### Task 5: Halaman sesi peta baru dengan Uppy

**Files:**
- Create: `web/app/new/page.tsx`

**Interfaces:**
- Consumes: `api.createJob` (Task 4), `POST /api/jobs` dan tus `/files/` (PR 2).

- [ ] **Step 1: Tulis `web/app/new/page.tsx`**

```tsx
"use client";
import Uppy from "@uppy/core";
import Dashboard from "@uppy/react/dashboard";
import Tus from "@uppy/tus";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, mb } from "@/lib/api";
import "@uppy/core/css/style.min.css";
import "@uppy/dashboard/css/style.min.css";

const CHUNK = 50 * 1024 * 1024; // di bawah batas Cloudflare Free 100 MB per permintaan

function createUppy() {
  return new Uppy({
    autoProceed: false,
    restrictions: { allowedFileTypes: ["video/*"], maxNumberOfFiles: 4, maxFileSize: 2 * 1024 ** 3 },
  }).use(Tus, {
    endpoint: "/files/",
    chunkSize: CHUNK,
    retryDelays: [0, 1000, 3000, 5000, 10000],
    allowedMetaFields: ["job_id", "name"], // dicocokkan hook pre-create dengan video terdaftar
    // Unggahan lama terikat ke pekerjaan lamanya: jangan dilanjutkan ke pekerjaan baru.
    storeFingerprintForResuming: false,
  });
}

type Role = "peta" | "uji";
type Picked = { id: string; name: string; size: number };

export default function NewSessionPage() {
  const router = useRouter();
  const [uppy] = useState(createUppy);
  const [files, setFiles] = useState<Picked[]>([]);
  const [roles, setRoles] = useState<Record<string, Role>>({});
  const [areaId, setAreaId] = useState("floor10");
  const [areaName, setAreaName] = useState("Lantai 10");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const sync = () =>
      setFiles(uppy.getFiles().map((f) => ({ id: f.id, name: f.name ?? "", size: f.size ?? 0 })));
    uppy.on("file-added", sync);
    uppy.on("file-removed", sync);
    return () => {
      uppy.off("file-added", sync);
      uppy.off("file-removed", sync);
    };
  }, [uppy]);

  // Bawaan seperti uji 2026-09-30: video pertama untuk peta, sisanya untuk uji.
  const roleOf = (f: Picked, i: number): Role => roles[f.id] ?? (i === 0 ? "peta" : "uji");

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const videos = files.map((f, i) => ({ name: f.name, size: f.size, role: roleOf(f, i) }));
      const job = await api.createJob({ area_id: areaId, area_name: areaName, videos });
      uppy.setMeta({ job_id: String(job.id) });
      const result = await uppy.upload();
      if (result?.failed?.length) throw new Error(`${result.failed.length} video gagal diunggah`);
      router.push(`/job/?id=${job.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Sesi peta baru</h1>
      <label>
        ID area (huruf kecil, angka, tanda hubung){" "}
        <input value={areaId} onChange={(e) => setAreaId(e.target.value)} pattern="[a-z0-9][a-z0-9-]{0,39}" />
      </label>
      <label>
        Nama area <input value={areaName} onChange={(e) => setAreaName(e.target.value)} />
      </label>
      <Dashboard uppy={uppy} hideUploadButton proudlyDisplayPoweredByUppy={false} height={320} />
      {files.length > 0 && (
        <table>
          <thead>
            <tr><th>Video</th><th>Ukuran</th><th>Peran</th></tr>
          </thead>
          <tbody>
            {files.map((f, i) => (
              <tr key={f.id}>
                <td>{f.name}</td>
                <td>{mb(f.size)}</td>
                <td>
                  <select value={roleOf(f, i)} onChange={(e) => setRoles({ ...roles, [f.id]: e.target.value as Role })}>
                    <option value="peta">peta</option>
                    <option value="uji">uji</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>Peta produksi: tandai semua video sebagai peta. Jangan tutup tab sampai unggahan selesai.</p>
      <button onClick={start} disabled={busy || files.length === 0}>
        {busy ? "Mengunggah..." : "Mulai unggah"}
      </button>
      {error && <p className="error">{error}</p>}
    </>
  );
}
```

Kalau TypeScript menolak `storeFingerprintForResuming` (opsi tus-js-client yang diteruskan Uppy), periksa tipe `TusOpts` di `node_modules/@uppy/tus/lib/index.d.ts` dan pakai nama opsi yang tersedia di sana. Jangan menghapus pencegahannya tanpa pengganti.

- [ ] **Step 2: Build**

Run: `cd web && npm run build`
Expected: sukses, `web/out/new/index.html` ada.

- [ ] **Step 3: Commit**

```bash
git add web/app/new
git commit -m "feat(web): halaman sesi peta baru dengan Uppy, tus potongan 50 MiB, dan peran video"
```

---

### Task 6: Halaman detail pekerjaan dan versi peta

**Files:**
- Create: `web/app/job/page.tsx`, `web/app/maps/page.tsx`

**Interfaces:**
- Consumes: `api.job`, `api.publish`, `api.versions`, `api.service`, `STATUS`, `mb` (Task 4).

- [ ] **Step 1: `web/app/job/page.tsx`**

```tsx
"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, mb, STATUS } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

function JobDetail() {
  const id = Number(useSearchParams().get("id"));
  const { data: job, error } = usePoll(() => api.job(id), 5000, [id]);
  const [message, setMessage] = useState<string | null>(null);

  async function publish(versionId: number) {
    if (!window.confirm("Terbitkan peta ini? /localize akan memakai versi ini.")) return;
    try {
      const r = await api.publish(versionId);
      setMessage(
        r.reload === "started"
          ? `Versi ${r.version.version} diterbitkan dan sedang dimuat layanan. Pantau di Versi peta.`
          : `Versi ${r.version.version} diterbitkan, tetapi layanan ini melayani area lain.`,
      );
    } catch (e) {
      setMessage((e as Error).message);
    }
  }

  if (!id) return <p className="error">Parameter id tidak ada.</p>;
  if (error) return <p className="error">{error}</p>;
  if (!job) return <p>Memuat...</p>;
  const run = job.summary?.run;
  const ins = job.summary?.inspect;
  return (
    <>
      <h1>Pekerjaan {job.id}: {job.area_id}</h1>
      <p>
        <span className={`badge ${job.status}`}>{STATUS[job.status] ?? job.status}</span>{" "}
        tahap {job.stage ?? "-"}, oleh {job.created_by}
      </p>
      <table>
        <tbody>
          {job.videos.map((v) => (
            <tr key={v.name}>
              <td>{v.name}</td><td>{v.role}</td><td>{mb(v.size)}</td>
              <td>{v.uploaded ? "terunggah" : "belum lengkap"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {job.error && <pre className="error">{job.error}</pre>}
      {run && ins && (
        <ul>
          <li>Frame terdaftar: {run.map_registered} dari {run.map_images}</li>
          <li>Potongan peta: {ins.parts?.length ?? 0} (1 berarti utuh)</li>
          <li>Foto uji diterima: {ins.accepted} dari {ins.queries} (ambang {ins.min_inliers} inlier)</li>
        </ul>
      )}
      {job.map_version_id && (
        <>
          <button onClick={() => publish(job.map_version_id!)}>Terbitkan versi ini</button>{" "}
          <Link href="/maps/">Versi peta</Link>
          {message && <p>{message}</p>}
          <h2>Tampilan 3D</h2>
          <iframe src={`/api/versions/${job.map_version_id}/report`} title="Tampilan 3D peta" />
        </>
      )}
    </>
  );
}

export default function JobPage() {
  // useSearchParams wajib di dalam Suspense pada static export (tanpa ini next build gagal).
  return (
    <Suspense fallback={<p>Memuat...</p>}>
      <JobDetail />
    </Suspense>
  );
}
```

- [ ] **Step 2: `web/app/maps/page.tsx`**

```tsx
"use client";
import Link from "next/link";
import { useState } from "react";
import { api, STATUS } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function MapsPage() {
  const [tick, setTick] = useState(0);
  const versions = usePoll(api.versions, 10000, [tick]);
  const service = usePoll(api.service, 3000, [tick]);
  const [error, setError] = useState<string | null>(null);

  async function publish(id: number, version: number) {
    if (!window.confirm(`Jadikan versi ${version} aktif?`)) return;
    try {
      await api.publish(id);
      setTick(tick + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const s = service.data;
  return (
    <>
      <h1>Versi peta</h1>
      {s && (
        <p>
          Layanan melayani area <strong>{s.area_id ?? "-"}</strong> versi {s.map_version ?? "-"}
          {s.reloading && ", sedang memuat versi baru..."}
        </p>
      )}
      {s?.reload_error && <p className="error">{s.reload_error}</p>}
      {(error || versions.error) && <p className="error">{error ?? versions.error}</p>}
      <table>
        <thead>
          <tr><th>Area</th><th>Versi</th><th>Status</th><th>Pekerjaan</th><th>Diterbitkan oleh</th><th></th></tr>
        </thead>
        <tbody>
          {versions.data?.map((v) => (
            <tr key={v.id}>
              <td>{v.area_id}</td>
              <td>{v.version}</td>
              <td><span className={`badge ${v.status}`}>{STATUS[v.status] ?? v.status}</span></td>
              <td>{v.job_id ? <Link href={`/job/?id=${v.job_id}`}>{v.job_id}</Link> : "-"}</td>
              <td>{v.published_by ?? "-"}</td>
              <td>
                {v.status !== "published" && (
                  <button onClick={() => publish(v.id, v.version)}>
                    {v.status === "retired" ? "Kembalikan" : "Terbitkan"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
```

- [ ] **Step 3: Build**

Run: `cd web && npm run build`
Expected: sukses. `web/out/` berisi `index.html`, `new/index.html`, `job/index.html`, `maps/index.html`.

- [ ] **Step 4: Commit**

```bash
git add web/app/job web/app/maps
git commit -m "feat(web): halaman detail pekerjaan dengan tampilan 3D dan halaman versi peta"
```

---

### Task 7: Disajikan FastAPI, dibangun di Docker, CI, dan verifikasi PC lab

**Files:**
- Modify: `server/app.py` (mount `web/out` di akhir berkas)
- Modify: `deploy/Dockerfile` (tahap Node), `.dockerignore`
- Modify: `.github/workflows/ci.yml` (job build dashboard)
- Modify: `deploy/README.md` (bagian 7), `CLAUDE.md` (Status)
- Test: `tests/test_web_mount.py`

**Interfaces:**
- Consumes: semua halaman (Task 4 sampai 6), API (PR 3a).
- Produces: `server.app.mount_web(app, directory: Path) -> bool`

- [ ] **Step 1: Uji yang gagal (`tests/test_web_mount.py`)**

```python
"""Dashboard statis dipasang di / tanpa menutup rute API yang terdaftar lebih dulu."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.app import mount_web


def test_static_mount_keeps_api_routes(tmp_path):
    (tmp_path / "job").mkdir()
    (tmp_path / "index.html").write_text("beranda")
    (tmp_path / "job" / "index.html").write_text("detail")
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    assert mount_web(app, tmp_path) is True
    c = TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}
    assert c.get("/").text == "beranda"
    assert c.get("/job/?id=3").text == "detail"


def test_missing_build_is_skipped(tmp_path):
    assert mount_web(FastAPI(), tmp_path / "tidak-ada") is False
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_web_mount.py`
Expected: FAIL, `ImportError: cannot import name 'mount_web'`.

- [ ] **Step 3: Implementasi di `server/app.py`**

Tambah impor `from fastapi.staticfiles import StaticFiles`. Di **akhir berkas** (setelah semua rute, karena mount di `/` menangkap semua jalur yang belum cocok):

```python
WEB_DIR = Path(__file__).resolve().parents[1] / "web" / "out"


def mount_web(app: FastAPI, directory: Path) -> bool:
    """Dashboard hasil next build (static export). Dipasang terakhir supaya rute API menang."""
    if not directory.is_dir():
        return False
    app.mount("/", StaticFiles(directory=directory, html=True), name="web")
    return True


mount_web(app, WEB_DIR)
```

- [ ] **Step 4: Dockerfile dan `.dockerignore`**

Di `deploy/Dockerfile`, sebelum tahap `runtime`:

```dockerfile
# ---- web: dashboard Next.js static export ----
FROM node:24.21.0-bookworm-slim AS web
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY web/ ./
RUN npm run build
```

Di tahap `runtime`, setelah `COPY --chown=eutopos:eutopos spike ./spike`:

```dockerfile
COPY --from=web --chown=eutopos:eutopos /web/out ./web/out
```

`.dockerignore` menjadi:

```text
# Konteks build: pyproject.toml, uv.lock, server/, spike/, dan web/ (dashboard).
*
!pyproject.toml
!uv.lock
!server/
!spike/
!web/
**/__pycache__
web/node_modules
web/.next
web/out
```

- [ ] **Step 5: CI**

Tambahkan job di `.github/workflows/ci.yml` setelah job `python`:

```yaml
  web:
    name: Dashboard build
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: 24.21.0
      - run: npm ci
        working-directory: web
      - run: npm run build
        working-directory: web
```

(Tanpa cache npm: build singkat, dan audit zizmor tidak perlu menimbang risiko cache.)

- [ ] **Step 6: README bagian 7 dan Status**

Tambahkan di `deploy/README.md`:

```markdown
## 7. Dashboard

`https://eutopos.rockhead07.tech/` setelah login kode email. Dibangun `next build` di Dockerfile dan
disajikan `api` dari `web/out`.

| Halaman | Isi |
|---|---|
| `/` | Daftar pekerjaan, status diperbarui tiap 5 detik |
| `/new/` | Pilih area, tambah video, tentukan peran (peta atau uji), unggah dengan progress |
| `/job/?id=N` | Status, ringkasan peta, galat, tampilan 3D, tombol Terbitkan |
| `/maps/` | Versi per area, versi yang dilayani, Terbitkan atau Kembalikan |

Terbitkan memuat peta baru di latar. Selama memuat, `/localize` tetap memakai peta lama. Kalau gagal,
peta lama tetap dipakai dan galatnya tampil di `/maps/`. Layanan hanya memuat ulang untuk area
`EUTOPOS_AREA`.

Pengembangan di laptop: `cd web && npm install && npm run build` (pemeriksaan tipe). Halaman bisa
dilihat dengan `npx serve out`, tetapi data hanya muncul lewat layanan sungguhan.
```

Di `CLAUDE.md` bagian Status, ganti "Dashboard (PR 3) belum." dengan "Dashboard (PR 3) di `web/`, disajikan dari `/`."

- [ ] **Step 7: Verifikasi di laptop**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q && uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check . && (cd web && npm ci && npm run build)`
Expected: semua PASS, build sukses.

- [ ] **Step 8: Verifikasi di PC lab (pemilik menjalankan, hasil ditempel ke sesi)**

Branch sudah di-push atas perintah pemilik. Di Ubuntu:

```bash
cd ~/eutopos-vps && git fetch && git switch feat/dashboard-web
cd deploy && docker compose up -d --build
```

Lalu dari browser (HP dengan data seluler, untuk benar-benar dari luar):
- `https://eutopos.rockhead07.tech/` menampilkan daftar pekerjaan 1 sampai 3.
- `/job/?id=3` menampilkan ringkasan dan tampilan 3D (laporan lama tetap tampil karena plotly disematkan).
- `/new/`: unggah video pendek (misalnya rekaman 20 detik dari HP), peran peta, lalu progress berjalan, halaman pindah ke detail, status berlanjut sampai `selesai`.
- **Terbitkan** versi baru untuk area `demo` tidak memuat ulang (area lain). Untuk menguji muat ulang: isi `EUTOPOS_AREA=floor10` di `deploy/.env`, `docker compose up -d`, lalu Terbitkan versi floor10 dan pantau `/maps/` sampai versinya tampil sebagai yang dilayani.
- Biarkan tab terbuka sampai sesi Access habis tidak praktis: cukup buka `/` di jendela penyamaran tanpa login dan pastikan diarahkan ke halaman login.

- [ ] **Step 9: Commit**

```bash
git add server/app.py tests/test_web_mount.py deploy/Dockerfile .dockerignore .github/workflows/ci.yml deploy/README.md CLAUDE.md
git commit -m "feat(deploy): dashboard disajikan api, dibangun di Docker, dan diperiksa CI"
```
