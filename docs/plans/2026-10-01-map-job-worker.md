# Antrean dan Pekerja Bangun Peta (PR 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membangun peta dari video atau folder frame lewat satu perintah antrean, dikerjakan pekerja GPU di Docker, lalu hasilnya terdaftar sebagai versi kandidat yang bisa diterbitkan.

**Architecture:** Tabel `map_job` di PostgreSQL menjadi antrean (`FOR UPDATE SKIP LOCKED`). `server/worker.py` mengambil satu pekerjaan, menjalankan alat spike (`extract_frames.py`, `run.py --seq`, `inspect_map.py`) sebagai subprocess tahap demi tahap, lalu memanggil `server.db.register`. Perintah dibangun oleh fungsi murni di `server/pipeline.py` supaya bisa diuji tanpa GPU. Website (PR 2 sampai 4) nanti hanya menambah cara memasukkan pekerjaan.

**Tech Stack:** Python 3.12, SQLModel + Alembic, PostgreSQL 17 (SQLite di uji), Docker Compose, hloc (lewat alat spike).

**Spec:** `docs/specs/2026-10-01-web-upload-and-map-build-design.md` (bagian 4 sampai 6, 10, 11, 13 PR 1).

**Cakupan rencana ini:** hanya PR 1. PR 2 (unggahan tusd + autentikasi), PR 3 (dashboard), dan PR 4 (Tunnel) masing-masing mendapat rencana sendiri setelah PR 1 masuk `main`.

## Global Constraints

- **Prasyarat:** branch `feat/video-map-diagnostics` sudah di-merge ke `main` (`run.py --seq`, `spike/inspect_map.py`). Kerjakan di worktree baru dari `origin/main` sesudahnya: `git -c core.longpaths=true worktree add -b feat/map-job-worker D:/wt/map-job origin/main`.
- Nama berkas, fungsi, dan opsi CLI bahasa Inggris. Pesan, docstring, dan komentar bahasa Indonesia, mengikuti berkas di sekitarnya.
- **Tanpa em dash** di teks apa pun.
- Ruff 0.16.9, panjang baris 100: `uvx ruff@0.16.9 check .` dan `uvx ruff@0.16.9 format --check .` harus bersih.
- Uji di laptop: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q` dari akar worktree.
- Setelan peta tetap sama dengan bawaan layanan: keypoint 1024, resize 1024, global resize 512.
- Peran video hanya `peta` atau `uji`. `peta` diekstrak 2 fps ke `mapping/`, `uji` 0,5 fps ke `query/`.
- **Video mentah hanya dihapus kalau berada di dalam `<data>/uploads/`** (unggahan website). Berkas yang diberikan lewat CLI tidak pernah dihapus.
- Commit hanya setelah pemilik menyetujui eksekusi rencana. Push hanya atas perintah terpisah. Tanpa atribusi AI di pesan commit.
- Tidak menyimpan foto, frame, IP, atau kredensial di repo (repo publik).

## Review Focus

1. **Path CLI di luar folder unggahan** harus selamat: pekerjaan dari CLI tidak boleh menghapus video asli pemilik. Diuji di Task 3.
2. **Pekerjaan tanpa video berperan `peta`, atau peran salah ketik,** ditolak saat dibuat, bukan gagal setengah jalan di GPU. Diuji di Task 1.
3. **Pekerja mati di tengah** (container restart) meninggalkan status `running` selamanya kalau tidak dipulihkan. Diuji di Task 1 (`recover_stale`).
4. **Satu tahap gagal** harus membuat pekerjaan `failed` dengan potongan log, dan pekerja tetap hidup untuk pekerjaan berikutnya. Diuji di Task 3.
5. **Peta produksi tanpa video `uji`** (folder `query/` kosong) tidak boleh membuat `run.py` jatuh. Diuji manual di Task 2 dengan data demo.

---

### Task 1: Model `map_job`, migrasi, dan fungsi antrean

**Files:**
- Modify: `server/db.py` (tambah `MapJob`, kolom `MapVersion.published_by`, parameter `by` di `publish`)
- Create: `server/migrations/versions/0002_map_job.py`
- Create: `server/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `server.db.Area`, `server.db.register`, `server.db.publish`
- Produces:
  - `server.db.MapJob` (kolom spesifikasi bagian 5)
  - `server.db.publish(session, version_id: int, by: str | None = None) -> MapVersion`
  - `server.jobs.create_job(session, area_id: str, area_name: str, created_by: str, videos: list[dict], status: str = "uploading") -> MapJob`
  - `server.jobs.claim_next(session) -> MapJob | None`
  - `server.jobs.set_stage(session, job: MapJob, stage: str) -> None`
  - `server.jobs.finish(session, job: MapJob, map_version_id: int, summary: dict) -> None`
  - `server.jobs.fail(session, job: MapJob, error: str) -> None`
  - `server.jobs.recover_stale(session) -> int`
  - Setiap item `videos`: `{"path": str, "role": "peta" | "uji"}` (PR 2 menambah `name`, `size`, `upload_id`).

- [ ] **Step 1: Tulis uji yang gagal**

```python
"""Uji antrean pekerjaan bangun peta, dengan SQLite di memori."""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from server import jobs
from server.db import Area, MapJob, publish, register

MAP = {"path": "/data/inbox/v1.mp4", "role": "peta"}
QUERY = {"path": "/data/inbox/v2.mp4", "role": "uji"}


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_create_job_makes_area_and_keeps_videos(session):
    job = jobs.create_job(session, "floor10", "Lantai 10", "a@x.id", [MAP, QUERY], "queued")
    assert session.get(Area, "floor10").name == "Lantai 10"
    assert (job.status, job.created_by, job.videos) == ("queued", "a@x.id", [MAP, QUERY])


@pytest.mark.parametrize(
    "videos",
    [[], [QUERY], [{"path": "/x.mp4", "role": "map"}]],
    ids=["kosong", "tanpa-peta", "peran-salah-ketik"],
)
def test_create_job_rejects_unusable_videos(session, videos):
    with pytest.raises(ValueError):
        jobs.create_job(session, "floor10", "Lantai 10", "a@x.id", videos, "queued")


def test_claim_next_is_fifo_and_skips_non_queued(session):
    jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "uploading")
    first = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "queued")
    second = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "queued")
    got = jobs.claim_next(session)
    assert (got.id, got.status) == (first.id, "running")
    assert got.started_at is not None
    assert jobs.claim_next(session).id == second.id
    assert jobs.claim_next(session) is None


def test_finish_and_fail_record_outcome(session):
    job = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "queued")
    jobs.claim_next(session)
    jobs.set_stage(session, job, "build")
    jobs.fail(session, job, "x" * 10_000)
    assert (job.status, job.stage) == ("failed", "build")
    assert len(job.error) == 4000 and job.finished_at is not None

    ok = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "queued")
    jobs.claim_next(session)
    v = register(session, "floor10", "L10", "/maps/floor10/job-2")
    jobs.finish(session, ok, v.id, {"run": {"map_registered": 80}})
    assert (ok.status, ok.map_version_id, ok.summary["run"]["map_registered"]) == ("done", v.id, 80)


def test_recover_stale_fails_running_jobs(session):
    job = jobs.create_job(session, "floor10", "L10", "a@x.id", [MAP], "queued")
    jobs.claim_next(session)
    assert jobs.recover_stale(session) == 1
    assert session.get(MapJob, job.id).status == "failed"
    assert "pekerja berhenti" in session.get(MapJob, job.id).error


def test_publish_records_who(session):
    v = register(session, "floor10", "L10", "/maps/v1")
    assert publish(session, v.id, by="a@x.id").published_by == "a@x.id"
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_jobs.py`
Expected: FAIL, `ImportError: cannot import name 'jobs' from 'server'`.

- [ ] **Step 3: Tambah model di `server/db.py`**

Ganti baris import SQLAlchemy dan tambahkan kolom serta kelas berikut. Ubah juga docstring modul baris pertama menjadi `"""Model data peta: area, versi petanya, dan antrean pekerjaan bangun peta."""`.

```python
from sqlalchemy import JSON, DateTime, Index, UniqueConstraint, func, text
```

Di `MapVersion`, setelah `created_at`:

```python
    published_by: str | None = None  # email dari JWT Access, null untuk versi lewat CLI
```

Setelah kelas `MapVersion`:

```python
class MapJob(SQLModel, table=True):
    """Satu pekerjaan bangun peta (spesifikasi web-upload bagian 5)."""

    __tablename__ = "map_job"

    id: int | None = Field(default=None, primary_key=True)
    area_id: str = Field(foreign_key="area.id", index=True)
    created_by: str
    status: str = "uploading"  # uploading, queued, running, done, failed
    stage: str | None = None  # tahap aktif, atau tahap tempat gagal
    videos: list[dict] = Field(default_factory=list, sa_type=JSON)
    summary: dict | None = Field(default=None, sa_type=JSON)
    error: str | None = None
    map_version_id: int | None = Field(default=None, foreign_key="map_version.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True)
    )
    started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    finished_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
```

Ganti `publish`:

```python
def publish(session: Session, version_id: int, by: str | None = None) -> MapVersion:
    """Jadikan versi ini aktif. Versi aktif sebelumnya menjadi "retired", dalam satu transaksi."""
    v = session.get(MapVersion, version_id)
    if v is None:
        raise LookupError(f"versi {version_id} tidak ada")
    current = active_version(session, v.area_id)
    if current is not None and current.id != v.id:
        current.status = "retired"
        session.add(current)
        session.flush()  # lepas status lama dulu supaya indeks unik tidak bentrok
    v.status = "published"
    v.published_by = by
    session.add(v)
    session.commit()
    session.refresh(v)
    return v
```

- [ ] **Step 4: Tulis migrasi `server/migrations/versions/0002_map_job.py`**

```python
"""map_job dan map_version.published_by

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("map_version", sa.Column("published_by", sa.String(), nullable=True))
    op.create_table(
        "map_job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_id", sa.String(), sa.ForeignKey("area.id"), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=True),
        sa.Column("videos", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "map_version_id", sa.Integer(), sa.ForeignKey("map_version.id"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_map_job_area_id", "map_job", ["area_id"])


def downgrade():
    op.drop_table("map_job")
    op.drop_column("map_version", "published_by")
```

- [ ] **Step 5: Tulis `server/jobs.py`**

```python
"""Antrean pekerjaan bangun peta di tabel map_job (spesifikasi web-upload bagian 4 sampai 6).

Satu pekerja, jadi FOR UPDATE SKIP LOCKED di sini lebih sebagai pengaman daripada kebutuhan. Pola
antrean ini disebut di dokumentasi PostgreSQL untuk SELECT ... FOR UPDATE.
"""

from datetime import UTC, datetime

from sqlmodel import Session, select

from server.db import Area, MapJob

ROLES = {"peta", "uji"}
ERROR_MAX = 4000  # cukup untuk 50 baris log terakhir


def _save(session: Session, job: MapJob) -> None:
    session.add(job)
    session.commit()
    session.refresh(job)


def create_job(
    session: Session,
    area_id: str,
    area_name: str,
    created_by: str,
    videos: list[dict],
    status: str = "uploading",
) -> MapJob:
    """Buat pekerjaan. Ditolak di sini, bukan di GPU, kalau videonya tidak bisa jadi peta."""
    if unknown := {v["role"] for v in videos} - ROLES:
        raise ValueError(f"peran video tidak dikenal: {sorted(unknown)}, pakai peta atau uji")
    if not any(v["role"] == "peta" for v in videos):
        raise ValueError("butuh minimal satu video berperan peta")
    if session.get(Area, area_id) is None:
        session.add(Area(id=area_id, name=area_name))
    job = MapJob(area_id=area_id, created_by=created_by, status=status, videos=videos)
    _save(session, job)
    return job


def claim_next(session: Session) -> MapJob | None:
    """Ambil pekerjaan queued tertua dan tandai running."""
    stmt = (
        select(MapJob)
        .where(MapJob.status == "queued")
        .order_by(MapJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = session.exec(stmt).first()
    if job is None:
        session.rollback()  # lepas transaksi yang dibuka SELECT
        return None
    job.status, job.stage, job.started_at = "running", None, datetime.now(UTC)
    _save(session, job)
    return job


def set_stage(session: Session, job: MapJob, stage: str) -> None:
    job.stage = stage
    _save(session, job)


def finish(session: Session, job: MapJob, map_version_id: int, summary: dict) -> None:
    job.status, job.map_version_id, job.summary = "done", map_version_id, summary
    job.finished_at = datetime.now(UTC)
    _save(session, job)


def fail(session: Session, job: MapJob, error: str) -> None:
    job.status, job.error, job.finished_at = "failed", error[-ERROR_MAX:], datetime.now(UTC)
    _save(session, job)


def recover_stale(session: Session) -> int:
    """Saat pekerja mulai: pekerjaan running tidak punya pemilik lagi (hanya ada satu pekerja)."""
    stale = session.exec(select(MapJob).where(MapJob.status == "running")).all()
    for job in stale:
        fail(session, job, "pekerja berhenti di tengah pekerjaan, unggah atau antrekan ulang")
    return len(stale)
```

- [ ] **Step 6: Jalankan uji, pastikan lolos**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_jobs.py tests/test_db.py`
Expected: semua PASS, termasuk `test_migration_matches_models` (migrasi 0002 sama dengan model) dan `test_migration_cli_runs_like_the_container`.

- [ ] **Step 7: Lint lalu commit**

```bash
uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .
git add server/db.py server/jobs.py server/migrations/versions/0002_map_job.py tests/test_jobs.py
git commit -m "feat(server): antrean pekerjaan bangun peta di tabel map_job"
```

---

### Task 2: Alat spike siap dipanggil pekerja

**Files:**
- Modify: `spike/inspect_map.py` (opsi `--json`)
- Modify: `spike/run.py` (tanpa foto uji tidak jatuh)

**Interfaces:**
- Produces:
  - `inspect_map.py RUN_DIR --json PATH` menulis `{"parts": [{"label": str, "frames": int, "ranges": [str]}], "queries": int, "accepted": int, "min_inliers": int}`
  - `run.py` dengan `query/` kosong menulis `summary.json` berisi `"queries": 0` dan keluar 0, tanpa `results.csv` baris data.

- [ ] **Step 1: Tambah opsi `--json` di `spike/inspect_map.py`**

Tambah argumen setelah `--html`:

```python
    ap.add_argument("--json", type=Path, help="simpan ringkasan potongan dan query")
```

Di loop potongan, kumpulkan barisnya. Ganti `step = main_model = None` dengan:

```python
    step = main_model = None
    part_rows = []
```

dan tambahkan di akhir badan loop `for label, d in parts:` (setelah `print(...)`):

```python
        part_rows.append({"label": label, "frames": len(ids), "ranges": ranges(ids)})
```

Ganti blok `with open(a.run_dir / "results.csv", ...)` supaya tidak jatuh kalau berkasnya tidak ada:

```python
    results = a.run_dir / "results.csv"  # tidak ada kalau peta dibangun tanpa foto uji
    with open(results if results.exists() else os.devnull, encoding="utf-8") as f:
```

(tambahkan `import os` di blok import). Setelah `print(f"\nditerima layanan: ...")`:

```python
    if a.json:
        summary = {"parts": part_rows, "queries": rows, "accepted": accepted}
        a.json.write_text(json.dumps({**summary, "min_inliers": MIN_INLIERS}), encoding="utf-8")
```

- [ ] **Step 2: Jalankan self-test dan coba di data demo**

Run: `/d/Dev/Projects/eutopos-vps/.venv/Scripts/python.exe spike/inspect_map.py --self-test`
Expected: `self-test ok`

Run (data demo yang sudah ada di salinan utama):
`/d/Dev/Projects/eutopos-vps/.venv/Scripts/python.exe spike/inspect_map.py /d/Dev/Projects/eutopos-vps/outputs/bench-verify/kp1024-r1024 --json "$TMP/i.json" && cat "$TMP/i.json"`
Expected: JSON dengan `"parts": [{"label": "utama", "frames": 9, ...}]`, `"queries": 1`, `"accepted": 1`, `"min_inliers": 50`.

- [ ] **Step 3: `spike/run.py` tidak jatuh tanpa foto uji**

Sisipkan tepat sebelum baris `    # 2. Foto uji (diproses sekaligus; ...)`:

```python
    base = {
        "max_keypoints": a.max_kp,
        "resize_max": a.resize,
        "covisibility_clustering": a.covis,
        "sequential_pairs": a.seq,
        "map_images": len(refs),
        "map_registered": model.num_reg_images(),
        "map_points3D": model.num_points3D(),
        "t_map_s": t_map,
    }
    if not queries:  # peta produksi: semua video berperan peta, tidak ada foto uji
        summary = {**base, "queries": 0, "env": env()}
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return
```

Lalu di akhir berkas ganti delapan baris pertama isi `summary = {` (dari `"max_keypoints"` sampai `"t_map_s": t_map,`) dengan `**base,`, sehingga menjadi:

```python
    summary = {
        **base,
        "queries": len(queries),
        "queries_localized": sum(r["ok"] for r in rows),
```

(sisa kunci tidak berubah).

- [ ] **Step 4: Uji manual tanpa foto uji di data demo (CPU laptop, beberapa menit)**

```bash
D=$TMP/demo-noquery && rm -rf "$D" && mkdir -p "$D/query"
cp -r /d/Dev/Projects/eutopos-vps/third_party/Hierarchical-Localization/datasets/sacre_coeur/mapping "$D/mapping"
/d/Dev/Projects/eutopos-vps/.venv/Scripts/python.exe spike/run.py "$D" --out "$D-out"
/d/Dev/Projects/eutopos-vps/.venv/Scripts/python.exe spike/inspect_map.py "$D-out/kp1024-r1024" --json "$D-out/i.json"
```

Expected: `run.py` mencetak ringkasan dengan `"queries": 0` dan keluar 0. `inspect_map.py` mencetak `diterima layanan: 0/0 query` dan menulis `i.json`.

- [ ] **Step 5: Lint lalu commit**

```bash
uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .
git add spike/inspect_map.py spike/run.py
git commit -m "spike: inspect_map --json dan run.py tanpa foto uji untuk peta produksi"
```

---

### Task 3: Perintah pipeline dan pekerja

**Files:**
- Create: `server/pipeline.py`
- Create: `server/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `server.jobs.*` (Task 1), `server.db.register`, `server.map_layout.missing_files`, keluaran Task 2.
- Produces:
  - `server.pipeline.MAX_KP`, `RESIZE`, `GLOBAL_RESIZE`, `SEQ`, `ROLES`
  - `server.pipeline.run_dir(map_dir: Path) -> Path`
  - `server.pipeline.missing_inputs(videos: list[dict]) -> list[str]`
  - `server.pipeline.copy_frame_dirs(videos: list[dict], dataset: Path) -> None`
  - `server.pipeline.extract_commands(videos: list[dict], dataset: Path) -> list[list[str]]`
  - `server.pipeline.build_command(dataset: Path, map_dir: Path) -> list[str]`
  - `server.pipeline.inspect_command(map_dir: Path) -> list[str]`
  - `server.worker.process(session, job, data: Path, maps: Path, runner=run, free_bytes=...) -> None`
  - `python -m server.worker` (loop)

- [ ] **Step 1: Tulis uji yang gagal**

```python
"""Uji pekerja dengan perintah subprocess palsu: tanpa GPU, tanpa hloc."""

import sys
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from server import jobs, pipeline, worker
from server.db import MapVersion
from server.map_layout import required_files


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def fake_runner(calls, fail_on=None):
    """Meniru alat spike: buat berkas yang biasanya ditulis tiap skrip."""

    def run(argv, log):
        script = Path(argv[1]).name
        calls.append(script)
        if script == fail_on:
            raise worker.StageError(f"perintah gagal (kode 1): {script}")
        if script == "run.py":
            map_dir = Path(argv[argv.index("--out") + 1])
            for p in required_files(map_dir, 1024, 1024, 512):
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
            (pipeline.run_dir(map_dir) / "summary.json").write_text('{"map_registered": 80}')
        if script == "inspect_map.py":
            Path(argv[argv.index("--json") + 1]).write_text('{"parts": [], "accepted": 20}')

    return run


def make_inputs(tmp_path):
    data, maps = tmp_path / "data", tmp_path / "maps"
    (data / "uploads").mkdir(parents=True)
    uploaded = data / "uploads" / "abc"
    uploaded.write_bytes(b"video")
    own = tmp_path / "pemilik" / "v2.mp4"  # berkas milik pemilik, diberikan lewat CLI
    own.parent.mkdir()
    own.write_bytes(b"video")
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "f_00000.jpg").write_bytes(b"jpg")
    videos = [
        {"path": str(uploaded), "role": "peta"},
        {"path": str(own), "role": "uji"},
        {"path": str(frames), "role": "peta"},
    ]
    return data, maps, uploaded, own, videos


def test_extract_commands_split_by_role(tmp_path):
    v1, v2 = tmp_path / "v1.mp4", tmp_path / "v2.mp4"
    v1.touch()
    v2.touch()
    videos = [{"path": str(v1), "role": "peta"}, {"path": str(v2), "role": "uji"}]
    cmds = pipeline.extract_commands(videos, tmp_path / "ds")
    assert [c[c.index("--fps") + 1] for c in cmds] == ["2.0", "0.5"]
    assert cmds[0][cmds[0].index("--out") + 1].endswith("mapping")
    assert cmds[1][cmds[1].index("--out") + 1].endswith("query")


def test_build_command_matches_service_settings(tmp_path):
    cmd = pipeline.build_command(tmp_path / "ds", tmp_path / "map")
    for flag, value in [("--max-kp", "1024"), ("--resize", "1024"), ("--global-resize", "512")]:
        assert cmd[cmd.index(flag) + 1] == value
    assert cmd[cmd.index("--seq") + 1] == "10"


def test_process_success_registers_candidate_and_spares_cli_files(session, tmp_path):
    data, maps, uploaded, own, videos = make_inputs(tmp_path)
    job = jobs.create_job(session, "floor10", "Lantai 10", "cli", videos, "queued")
    jobs.claim_next(session)
    calls = []

    worker.process(session, job, data, maps, runner=fake_runner(calls), free_bytes=lambda p: 10**12)

    assert job.status == "done", job.error
    assert calls == ["extract_frames.py", "extract_frames.py", "run.py", "inspect_map.py"]
    v = session.get(MapVersion, job.map_version_id)
    assert (v.status, v.path) == ("candidate", str(maps / "floor10" / f"job-{job.id}"))
    assert job.summary == {"run": {"map_registered": 80}, "inspect": {"parts": [], "accepted": 20}}
    assert not uploaded.exists()  # video unggahan dihapus setelah ekstraksi
    assert own.exists()  # berkas CLI di luar uploads tidak pernah dihapus
    assert (data / "jobs" / str(job.id) / "dataset" / "mapping" / "f_00000.jpg").exists()


def test_process_failure_keeps_stage_and_log(session, tmp_path):
    data, maps, _, _, videos = make_inputs(tmp_path)
    job = jobs.create_job(session, "floor10", "Lantai 10", "cli", videos, "queued")
    jobs.claim_next(session)
    worker.process(
        session, job, data, maps, runner=fake_runner([], "run.py"), free_bytes=lambda p: 10**12
    )
    assert (job.status, job.stage) == ("failed", "build")
    assert "run.py" in job.error
    assert job.map_version_id is None


def test_process_refuses_when_disk_is_low(session, tmp_path):
    data, maps, uploaded, _, videos = make_inputs(tmp_path)
    job = jobs.create_job(session, "floor10", "Lantai 10", "cli", videos, "queued")
    jobs.claim_next(session)
    calls = []
    worker.process(session, job, data, maps, runner=fake_runner(calls), free_bytes=lambda p: 10)
    assert (job.status, job.stage) == ("failed", "extract")
    assert "ruang disk" in job.error and calls == []
    assert uploaded.exists()  # tidak ada yang dihapus kalau belum diekstrak


def test_process_reports_missing_input(session, tmp_path):
    data, maps, *_ = make_inputs(tmp_path)
    videos = [{"path": str(tmp_path / "tidak-ada.mp4"), "role": "peta"}]
    job = jobs.create_job(session, "floor10", "Lantai 10", "cli", videos, "queued")
    jobs.claim_next(session)
    worker.process(session, job, data, maps, runner=fake_runner([]), free_bytes=lambda p: 10**12)
    assert job.status == "failed" and "tidak-ada.mp4" in job.error


def test_run_appends_command_and_raises_on_failure(tmp_path):
    log = tmp_path / "log.txt"
    with pytest.raises(worker.StageError, match="kode 3"):
        worker.run([sys.executable, "-c", "print('halo'); raise SystemExit(3)"], log)
    text = log.read_text(encoding="utf-8")
    assert text.startswith("$ ") and "halo" in text
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_worker.py`
Expected: FAIL, `ImportError: cannot import name 'pipeline' from 'server'`.

- [ ] **Step 3: Tulis `server/pipeline.py`**

```python
"""Perintah alat spike untuk satu pekerjaan bangun peta. Fungsi murni supaya bisa diuji tanpa GPU."""

import shutil
import sys
from pathlib import Path

SPIKE = Path(__file__).resolve().parents[1] / "spike"
# Sama dengan bawaan layanan (server/app.py), supaya peta hasil langsung bisa dimuat /localize.
MAX_KP, RESIZE, GLOBAL_RESIZE = 1024, 1024, 512
SEQ = 10  # pasangan berurutan untuk video (docs/spike-plan.md, uji video lantai 10)
ROLES = {"peta": ("mapping", 2.0), "uji": ("query", 0.5)}  # subfolder, fps ekstraksi


def run_dir(map_dir: Path) -> Path:
    return map_dir / f"kp{MAX_KP}-r{RESIZE}"


def missing_inputs(videos: list[dict]) -> list[str]:
    return [v["path"] for v in videos if not Path(v["path"]).exists()]


def copy_frame_dirs(videos: list[dict], dataset: Path) -> None:
    """Masukan berupa folder frame (misalnya hasil ekstraksi lama) disalin apa adanya."""
    for v in videos:
        src = Path(v["path"])
        if src.is_dir():
            shutil.copytree(src, dataset / ROLES[v["role"]][0], dirs_exist_ok=True)


def extract_commands(videos: list[dict], dataset: Path) -> list[list[str]]:
    cmds = []
    for role, (sub, fps) in ROLES.items():
        files = [v["path"] for v in videos if v["role"] == role and Path(v["path"]).is_file()]
        if files:
            script = str(SPIKE / "extract_frames.py")
            out = ["--out", str(dataset / sub), "--fps", str(fps)]
            cmds.append([sys.executable, script, *files, *out])
    return cmds


def build_command(dataset: Path, map_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(SPIKE / "run.py"),
        str(dataset),
        "--out",
        str(map_dir),
        "--max-kp",
        str(MAX_KP),
        "--resize",
        str(RESIZE),
        "--global-resize",
        str(GLOBAL_RESIZE),
        "--seq",
        str(SEQ),
    ]


def inspect_command(map_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(SPIKE / "inspect_map.py"),
        str(run_dir(map_dir)),
        "--html",
        str(map_dir / "report.html"),
        "--json",
        str(map_dir / "inspect.json"),
    ]
```

- [ ] **Step 4: Tulis `server/worker.py`**

```python
"""Pekerja bangun peta (spesifikasi web-upload bagian 6).

Mengambil satu pekerjaan queued, menjalankan alat spike tahap demi tahap sebagai subprocess, lalu
mendaftarkan hasilnya sebagai versi kandidat. Satu pekerja, satu pekerjaan dalam satu waktu.

    python -m server.worker
"""

import json
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from sqlmodel import Session

from server import jobs
from server.db import Area, MapJob, engine_from_env, register
from server.map_layout import missing_files
from server.pipeline import (
    GLOBAL_RESIZE,
    MAX_KP,
    RESIZE,
    build_command,
    copy_frame_dirs,
    extract_commands,
    inspect_command,
    missing_inputs,
    run_dir,
)

DATA, MAPS = Path("/data"), Path("/maps")  # jalur di dalam container (deploy/compose.yaml)
MIN_FREE_BYTES = 20 * 1024**3
POLL_S = 5
LOG_LINES = 50


class StageError(RuntimeError):
    pass


def run(argv: list[str], log: Path) -> None:
    """Jalankan satu perintah, keluarannya ditambahkan ke log pekerjaan."""
    with open(log, "a", encoding="utf-8") as f:
        f.write("$ " + " ".join(argv) + "\n")
        f.flush()
        code = subprocess.run(argv, stdout=f, stderr=subprocess.STDOUT).returncode
    if code:
        raise StageError(f"perintah gagal (kode {code}): {Path(argv[1]).name}")


def log_tail(log: Path) -> str:
    if not log.exists():
        return ""
    return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_LINES:])


def delete_uploaded_videos(videos: list[dict], uploads: Path) -> None:
    """Video mentah dari unggahan website dihapus setelah frame diekstrak (privasi). Berkas yang
    diberikan lewat CLI berada di luar folder uploads dan tidak pernah disentuh."""
    root = uploads.resolve()
    for v in videos:
        p = Path(v["path"]).resolve()
        if p.is_file() and p.is_relative_to(root):
            p.unlink()


def process(
    session: Session,
    job: MapJob,
    data: Path,
    maps: Path,
    runner: Callable[[list[str], Path], None] = run,
    free_bytes: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free,
) -> None:
    job_dir = data / "jobs" / str(job.id)
    dataset, log = job_dir / "dataset", job_dir / "log.txt"
    map_dir = maps / job.area_id / f"job-{job.id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        jobs.set_stage(session, job, "extract")
        if free_bytes(data) < MIN_FREE_BYTES:
            raise StageError("ruang disk kurang dari 20 GB, pekerjaan tidak dimulai")
        if missing := missing_inputs(job.videos):
            raise StageError(f"berkas masukan tidak ditemukan: {', '.join(missing)}")
        for sub in ("mapping", "query"):
            (dataset / sub).mkdir(parents=True, exist_ok=True)
        copy_frame_dirs(job.videos, dataset)
        for argv in extract_commands(job.videos, dataset):
            runner(argv, log)
        delete_uploaded_videos(job.videos, data / "uploads")

        jobs.set_stage(session, job, "build")
        runner(build_command(dataset, map_dir), log)

        jobs.set_stage(session, job, "inspect")
        runner(inspect_command(map_dir), log)

        jobs.set_stage(session, job, "register")
        if missing := missing_files(map_dir, MAX_KP, RESIZE, GLOBAL_RESIZE):
            raise StageError(f"peta tidak lengkap: {', '.join(map(str, missing))}")
        summary = {
            "run": json.loads((run_dir(map_dir) / "summary.json").read_text(encoding="utf-8")),
            "inspect": json.loads((map_dir / "inspect.json").read_text(encoding="utf-8")),
        }
        version = register(session, job.area_id, session.get(Area, job.area_id).name, str(map_dir))
        jobs.finish(session, job, version.id, summary)
    except Exception as e:  # pekerjaan gagal, pekerja tetap hidup untuk pekerjaan berikutnya
        session.rollback()
        jobs.fail(session, job, f"{e}\n{log_tail(log)}".strip())


def main() -> None:
    engine = engine_from_env()
    with Session(engine) as s:
        if n := jobs.recover_stale(s):
            print(f"{n} pekerjaan tertinggal ditandai gagal", flush=True)
    print("pekerja siap", flush=True)
    while True:
        with Session(engine) as s:
            job = jobs.claim_next(s)
            if job is None:
                time.sleep(POLL_S)
                continue
            print(f"pekerjaan {job.id} ({job.area_id}) mulai", flush=True)
            process(s, job, DATA, MAPS)
            print(f"pekerjaan {job.id}: {job.status}", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Jalankan uji, pastikan lolos**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q`
Expected: semua PASS (uji lama + `test_jobs.py` + `test_worker.py`).

- [ ] **Step 6: Lint lalu commit**

```bash
uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .
git add server/pipeline.py server/worker.py tests/test_worker.py
git commit -m "feat(server): pekerja bangun peta menjalankan alat spike tahap demi tahap"
```

---

### Task 4: Perintah antrean di `server.manage`

**Files:**
- Modify: `server/manage.py`
- Test: `tests/test_jobs.py` (tambah uji CLI)

**Interfaces:**
- Consumes: `server.jobs.create_job` (Task 1), `server.pipeline.missing_inputs` (Task 3)
- Produces:
  - `python -m server.manage job AREA NAME --map PATH... [--query PATH...] [--by EMAIL]` mencetak `pekerjaan <id> diantrekan`
  - `python -m server.manage jobs` mencetak satu baris per pekerjaan: `id`, area, status, tahap, waktu

- [ ] **Step 1: Tulis uji yang gagal (tambahkan ke `tests/test_jobs.py`)**

```python
def test_manage_job_queues_and_lists(tmp_path, monkeypatch, capsys):
    from server import manage

    url = f"sqlite:///{tmp_path / 'm.db'}"
    SQLModel.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    frames = tmp_path / "mapping"
    frames.mkdir()
    monkeypatch.setattr("sys.argv", ["manage", "job", "floor10", "Lantai 10", "--map", str(frames)])
    manage.main()
    assert "pekerjaan 1 diantrekan" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["manage", "jobs"])
    manage.main()
    listing = capsys.readouterr().out
    assert "floor10" in listing and "queued" in listing


def test_manage_job_rejects_missing_path(tmp_path, monkeypatch):
    from server import manage

    url = f"sqlite:///{tmp_path / 'm.db'}"
    SQLModel.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr("sys.argv", ["manage", "job", "floor10", "L10", "--map", "/tidak/ada"])
    with pytest.raises(SystemExit, match="tidak ditemukan"):
        manage.main()
```

- [ ] **Step 2: Jalankan, pastikan gagal**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q tests/test_jobs.py -k manage`
Expected: FAIL, `SystemExit: 2` (argparse tidak mengenal subperintah `job`).

- [ ] **Step 3: Tambah subperintah di `server/manage.py`**

Perbarui docstring contoh:

```python
"""Kelola versi peta dan antrean bangun peta dari baris perintah (butuh DATABASE_URL).

Contoh (di dalam container):
    python -m server.manage register demo "Data contoh" /maps/demo --publish
    python -m server.manage list
    python -m server.manage publish 3
    python -m server.manage job floor10 "Lantai 10" --map /data/inbox/video1.mp4 \
        --query /data/inbox/video2.mp4
    python -m server.manage jobs
Setelah menerbitkan versi baru, muat ulang layanan: docker compose restart api
"""
```

Tambahkan import:

```python
from server import jobs
from server.db import MapJob, MapVersion, engine_from_env, publish, register
from server.pipeline import missing_inputs
```

(ganti baris import `server.db` yang lama). Setelah parser `list`:

```python
    j = sub.add_parser("job", help="antrekan pembangunan peta dari video atau folder frame")
    j.add_argument("area_id")
    j.add_argument("name")
    j.add_argument("--map", nargs="+", required=True, help="video atau folder frame untuk peta")
    j.add_argument("--query", nargs="*", default=[], help="video atau folder frame untuk uji")
    j.add_argument("--by", default="cli", help="dicatat sebagai pembuat pekerjaan")
    sub.add_parser("jobs", help="tampilkan antrean pekerjaan")
```

Di dalam `with Session(...)`, sebelum `else:` terakhir:

```python
        elif a.cmd == "job":
            videos = [{"path": p, "role": "peta"} for p in a.map]
            videos += [{"path": p, "role": "uji"} for p in a.query]
            if missing := missing_inputs(videos):
                raise SystemExit(f"berkas tidak ditemukan: {', '.join(missing)}")
            job = jobs.create_job(s, a.area_id, a.name, a.by, videos, status="queued")
            print(f"pekerjaan {job.id} diantrekan untuk {job.area_id}")
        elif a.cmd == "jobs":
            for job in s.exec(select(MapJob).order_by(MapJob.id.desc())):
                when = f"{job.created_at:%Y-%m-%d %H:%M}"
                version = f"  versi id {job.map_version_id}" if job.map_version_id else ""
                stage = job.stage or "-"
                print(f"{job.id:4d}  {job.area_id}  {job.status:9}  {stage:8}  {when}{version}")
```

- [ ] **Step 4: Jalankan uji, pastikan lolos**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q`
Expected: semua PASS.

- [ ] **Step 5: Lint lalu commit**

```bash
uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .
git add server/manage.py tests/test_jobs.py
git commit -m "feat(server): perintah manage job dan jobs untuk antrean bangun peta"
```

---

### Task 5: Pekerja di Docker Compose dan verifikasi di PC lab

**Files:**
- Modify: `.dockerignore` (ikutkan `spike/`)
- Modify: `deploy/Dockerfile` (salin `spike/`)
- Modify: `deploy/compose.yaml` (layanan `worker` dengan `/maps` baca tulis dan `/data`)
- Modify: `deploy/compose.gpu.yaml` (GPU untuk `worker`)
- Modify: `deploy/.env.example` (`EUTOPOS_DATA_DIR`)
- Modify: `deploy/README.md` (bagian antrean dan pekerja)
- Modify: `CLAUDE.md` (Status)

**Interfaces:**
- Consumes: `python -m server.worker`, `python -m server.manage job|jobs` (Task 3 dan 4)

- [ ] **Step 1: Ikutkan `spike/` ke image**

`.dockerignore` menjadi:

```text
# Konteks build: pyproject.toml, uv.lock, server/, dan spike/ (alat yang dipanggil pekerja).
*
!pyproject.toml
!uv.lock
!server/
!spike/
**/__pycache__
```

Di `deploy/Dockerfile`, setelah `COPY --chown=eutopos:eutopos server ./server`:

```dockerfile
COPY --chown=eutopos:eutopos spike ./spike
```

- [ ] **Step 2: Tambah layanan `worker` di `deploy/compose.yaml`**

Layanan `api` tidak berubah (baru butuh `/data` di PR 2). Setelah layanan `api`:

```yaml
  worker:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    command: ["python", "-m", "server.worker"]
    environment:
      DATABASE_URL: postgresql+psycopg://eutopos:${POSTGRES_PASSWORD}@db:5432/eutopos
    volumes:
      # Pekerja menulis peta baru, jadi /maps baca tulis (api tetap baca saja).
      - type: bind
        source: ${EUTOPOS_MAPS_DIR:?isi EUTOPOS_MAPS_DIR di deploy/.env}
        target: /maps
        bind:
          create_host_path: false
      - type: bind
        source: ${EUTOPOS_DATA_DIR:?isi EUTOPOS_DATA_DIR di deploy/.env}
        target: /data
        bind:
          create_host_path: false
      - cache:/cache
    healthcheck:
      disable: true  # healthcheck image memeriksa HTTP :8000, pekerja tidak melayani HTTP
    depends_on:
      api:
        condition: service_healthy  # migrasi Alembic dijalankan api saat menyala
    restart: unless-stopped
```

- [ ] **Step 3: GPU untuk pekerja di `deploy/compose.gpu.yaml`**

Tambahkan di bawah `services:` (setelah blok `api`):

```yaml
  worker:
    build:
      args:
        TORCH_INDEX: https://download.pytorch.org/whl/cu130
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

Tambahkan komentar di kepala berkas: `# Pekerja bangun peta butuh GPU. Tanpa berkas ini, pekerja tetap jalan di CPU tapi sangat lambat.`

- [ ] **Step 4: `.env.example`**

Tambahkan:

```text
# Folder data pekerja di host WSL (frame, log, nanti unggahan website). Harus sudah ada,
# dimiliki uid 1000. Contoh: /home/USER/eutopos-data/work
EUTOPOS_DATA_DIR=/home/USER/eutopos-data/work
```

- [ ] **Step 5: Panduan di `deploy/README.md`**

Tambahkan bagian baru setelah bagian yang menjelaskan `server.manage`:

````markdown
## Antrean bangun peta (pekerja)

Pekerja (`worker`) mengambil pekerjaan dari tabel `map_job`, mengekstrak frame, membangun peta
dengan GPU, lalu mendaftarkan versi kandidat. Masukan berupa video atau folder frame di dalam
`EUTOPOS_DATA_DIR` (terlihat sebagai `/data` di container).

```bash
mkdir -p ~/eutopos-data/work/inbox
cp -r /mnt/c/Users/<user>/eutopos-vps/data/floor10-v1 ~/eutopos-data/work/inbox/
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose exec api python -m server.manage job floor10 "Lantai 10" \
  --map /data/inbox/floor10-v1/mapping --query /data/inbox/floor10-v1/query
docker compose exec api python -m server.manage jobs        # pantau status dan tahap
docker compose logs -f worker                                # log pekerja
docker compose exec api python -m server.manage publish <versi id>
docker compose restart api                                   # muat peta baru (sampai PR 3)
```

Hasil per pekerjaan: peta di `/maps/<area>/job-<id>/` (berisi `report.html` tampilan 3D), log di
`/data/jobs/<id>/log.txt`. Video dari folder `uploads/` dihapus setelah diekstrak. Berkas yang
diberikan lewat perintah di atas tidak pernah dihapus.
````

- [ ] **Step 6: Verifikasi di laptop**

Run: `PATH="/d/Dev/Projects/eutopos-vps/.venv/Scripts:$PATH" python -m pytest -q && uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .`
Expected: semua PASS, ruff bersih.

- [ ] **Step 7: Verifikasi di PC lab (pemilik menjalankan, hasil ditempel ke sesi)**

Branch `feat/map-job-worker` sudah di-push (atas perintah pemilik). Di Ubuntu WSL, salinan
`~/eutopos-vps`. Folder host `EUTOPOS_DATA_DIR` harus dimiliki uid 1000 (pengguna WSL pertama), sama
dengan pengguna di container:

```bash
git fetch && git switch feat/map-job-worker && git pull --ff-only
mkdir -p ~/eutopos-data/work/inbox
cp -r /mnt/c/Users/danab/eutopos-vps/data/floor10-v1 ~/eutopos-data/work/inbox/
echo 'EUTOPOS_DATA_DIR=/home/danab/eutopos-data/work' >> deploy/.env
cd deploy && docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose exec api python -m server.manage job floor10 "Lantai 10" \
  --map /data/inbox/floor10-v1/mapping --query /data/inbox/floor10-v1/query
docker compose exec api python -m server.manage jobs
```

Expected:
- Dalam beberapa menit, status pekerjaan berubah `running` (tahap `extract`, `build`, `inspect`, `register`) lalu `done` dengan `versi id`.
- `ls ~/eutopos-data/maps/floor10/job-1/` berisi `report.html`, `inspect.json`, `kp1024-r1024/`.
- Ringkasan di `inspect.json` menunjukkan potongan peta. Kalau `--seq` menyambung potongan, jumlah potongan lebih sedikit dari 3 (uji 2026-09-30).
- `manage publish <versi id>` lalu `docker compose restart api` dan `curl localhost:8000/health` menunjukkan `area_id` `floor10` dengan versi baru.
- Uji pemulihan: jalankan pekerjaan kedua, `docker compose restart worker` di tengah tahap `build`, lalu `manage jobs` menunjukkan pekerjaan itu `failed` dengan alasan "pekerja berhenti".

- [ ] **Step 8: Perbarui `CLAUDE.md` bagian Status**

Ganti butir layanan di "Posisi terakhir" dengan:

```markdown
- Layanan: `server/` (FastAPI `/localize`, `/health`), Docker Compose + PostgreSQL (versi peta per
  area), dan **antrean bangun peta** (`map_job`, pekerja GPU, `python -m server.manage job`) di
  `main`. Website unggah (PR 2 sampai 4) mengikuti `docs/specs/2026-10-01-web-upload-and-map-build-design.md`.
```

- [ ] **Step 9: Commit**

```bash
git add .dockerignore deploy/Dockerfile deploy/compose.yaml deploy/compose.gpu.yaml deploy/.env.example deploy/README.md CLAUDE.md
git commit -m "feat(deploy): layanan pekerja bangun peta di Docker Compose dengan GPU"
```
