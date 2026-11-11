# Tahap Splat Otomatis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Setelah sebuah versi peta jadi, server melatih, memeriksa, mengonversi, memangkas, dan menaruh `splat/scene.sog` sendiri, sehingga tombol "Lihat 3D" muncul tanpa ada yang menjalankan perintah.

**Architecture:** Layanan compose baru `splat-worker` (image sendiri) mengambil baris `splat_job` dari DB dengan pola `claim_next` yang sudah ada. `worker` dan `splat-worker` berbagi satu `pg_advisory_lock` selama memakai GPU. Hasil ditulis atomik; kegagalan splat tidak menyentuh `map_job` maupun `map_version`.

**Tech Stack:** Python 3.12, SQLModel/Alembic, FastAPI, Next.js (dashboard), gsplat 1.5.3 (CUDA devel), `@playcanvas/splat-transform` 3.10.3, numpy, Pillow, pycolmap.

**Spec:** `docs/specs/2026-11-09-splat-pipeline-design.md` (arsitektur A disetujui Bagus 9 Nov 2026).

**Status pelaksanaan (11 Nov 2026):** Task 1 sampai 9 selesai di cabang `feat/splat-convert` dan Task 8 terbukti
di PC lab (dua latihan penuh, angka di `docs/splat-pipeline-measurements.md`). Kotak centang di bawah sengaja
tidak dicentang: langkah Commit menunggu perintah Bagus. Penyimpangan dari rencana yang disengaja: (a) pemicu
Task 9 bawaan MATI dan hidup lewat `EUTOPOS_SPLAT_AUTO=1` bersama profil `splat`; (b) metrik pelatih ikut masuk
`report.json`; (c) pemeriksaan VRAM bebas 4.096 MiB dan batas RAM 8 GB ditambahkan (keputusan D8); (d) image memuat
dua environment Python. Catatan: `docs/plans/2026-11-01-gaussian-splat-lantai-10.md` yang disebut di Task 10 tidak
ada di cabang ini (ada di worktree spike, belum digabung), jadi catatannya ditunda sampai berkas itu masuk.

## Global Constraints

- Tanpa commit, push, atau merge tanpa perintah Bagus. `main` hanya lewat PR. Tanpa atribusi AI di commit atau PR.
- Dokumen berbahasa Indonesia, tanpa em dash. Pin versi eksak untuk dependensi baru.
- Perintah yang mengubah PC lab (membangun image, menjalankan pelatihan, menyalin berkas, `docker compose`) minta izin Bagus per langkah; membaca boleh. Jangan cetak `deploy/.env` atau hasil `docker compose config`. Jaga `C:` >= 30 GB kosong.
- Jangan menerbitkan versi peta hasil pindai baru dan jangan mengubah peta aktif. Catat `/health` (area, versi, `aligned`) sebelum dan sesudah tiap uji GPU.
- Fully local: tidak mengunggah video, frame, atau splat ke layanan pihak ketiga.
- gsplat, CUDA devel, dan Node tidak masuk image `worker` maupun `api`.
- Data (video, frame, checkpoint, `.ply`, `.sog`) tidak masuk git.
- GPU 8 GB dibagi dengan `/localize` (sekitar 1,8 GB). Hentikan dan tanya bila VRAM > 7,5 GB, `/health` gagal, atau RAM tersedia < 3 GB.
- Normalisasi dunia gsplat DIMATIKAN (splat harus tetap di kerangka COLMAP) dan `--disable-viewer` WAJIB (tanpa itu proses tidur selamanya setelah selesai).
- Tes unit tanpa GPU, tanpa Docker, tanpa jaringan; bagian GPU diverifikasi di PC lab, bukan CI. Tes dijalankan dengan `D:/Dev/Projects/eutopos-vps/.venv/Scripts/python.exe -m pytest`; sebutkan shell (di PowerShell `bash` di PATH adalah peluncur WSL mati, 6 tes `test_host_disk_feed` gagal; garis dasar Git Bash: 1 gagal `alembic`).

## Review Focus

1. **Job peta datang saat pelatihan sedang jalan.** Tidak ada penyelaan: `worker` menunggu kunci GPU sampai pelatihan selesai (kira-kira 16 menit). Pengguna harus melihat tahap "menunggu GPU", bukan job yang tampak macet. (Task 5)
2. **`splat-worker` mati di tengah pekerjaan.** Baris `running` tidak boleh tertinggal selamanya; saat layanan mulai lagi ditandai `failed`. (Task 3)
3. **Versi atau job dihapus saat splat dibangun.** `place` tidak boleh membuat folder di versi yang sudah hilang atau menulis ke peta orang lain. (Task 6)
4. **Berkas `scene.sog` setengah jadi.** `has_splat` benar begitu berkas ada, jadi penulisan wajib atomik dan `scene.sog` lama tetap disajikan sampai yang baru siap. (Task 6)
5. **Bangun ulang saat masih `running`, dan versi tanpa job atau tanpa frame (versi dari CLI).** Ditolak dengan alasan jelas, bukan crash. (Task 3 dan 7)
6. **Frame splat tidak sama dengan kerangka model.** `check` gagal (rasio >= 0,02) sehingga tidak ada `scene.sog` yang overlay-nya bergeser diam-diam. (Task 6)

---

### Task 1: Dokumentasikan asal numpy dan Pillow, dan masukkan modul pemangkas

Temuan 9 Nov 2026 (mengoreksi draf pertama rencana ini): `uv.lock` TIDAK memuat `numpy`, `pillow`, `opencv`, `pycolmap`, `torch`, `hloc`, `scipy`, atau `matplotlib`. Konvensi repo (komentar di `pyproject.toml`): dependensi runtime berat dipasang oleh langkah 1 dan 2 `deploy/Dockerfile` (torch, hloc). `numpy` datang dari `requirements.txt` hloc pada commit yang dipin, `Pillow` dari `matplotlib` (dependensi keras hloc). Mendeklarasikannya di `pyproject.toml` akan menambah paket baru ke `uv.lock` dan langkah 3 Dockerfile dengan risiko menggeser versi yang dipilih hloc, jadi TIDAK dilakukan. Image `splat-worker` (Task 8) tidak memakai hloc, jadi versi di sana dipin eksplisit di `deploy/Dockerfile.splat`.

**Files:**
- Modify: `pyproject.toml` (HANYA teks komentar di atas `dependencies`)
- Add (sudah ada, uncommitted di cabang ini): `spike/splat_prune.py`, `tests/test_splat_prune.py`, `docs/splat-prune.md`

**Interfaces:**
- Produces: `spike.splat_prune.prune_sog(src, dst, *, min_opacity=DEFAULT_MIN_OPACITY, drop_zero=False, max_scale=None) -> dict`, `DEFAULT_MIN_OPACITY = 0.02`, `SogError(ValueError)`.

- [ ] **Step 1: Buktikan asal kedua paket.** `grep -c -i '^name = "numpy"' uv.lock` dan untuk `pillow` harus 0; ambil `requirements.txt` hloc pada commit `c13273bd0ecc2917a35910fd843712a1c6243193` (tertulis `numpy`); dan jalankan `importlib.metadata.requires("matplotlib")` di `.venv` (harus memuat `pillow`). Laporkan keluaran mentahnya.
- [ ] **Step 2: Ubah komentar di `pyproject.toml`** supaya menyebut bahwa `numpy`, `Pillow`, `pycolmap`, `opencv-python`, dan `scipy` datang dari hloc dan torch (Dockerfile langkah 1 dan 2), bukan dari `uv.lock`. Jangan menyentuh `dependencies`, `[dependency-groups]`, atau `uv.lock`.
- [ ] **Step 3: Bukti tidak ada yang bergeser.** `git diff --stat` hanya `pyproject.toml` (komentar); `uv lock --check` lulus (`uv` lokal 0.12.19 sama dengan `required-version`).
- [ ] **Step 4: Suite penuh dan lint.** `pytest -q`, `ruff check`, `ruff format --check`. Expected: 1 gagal (`alembic`, garis dasar Git Bash), sisanya lulus.
- [ ] **Step 5: Commit** (atas perintah Bagus): `feat(splat): prune a SOG without requantizing`.

### Task 2: Bawa alat `prepare` dan `check_frame` ke repo

**Files:**
- Create: `spike/splat_prepare.py`, `spike/splat_check_frame.py`, `tests/test_splat_frame.py` (salin dari `D:\wt\splat-spike`, berkas itu masih untracked di sana)

**Interfaces:**
- Produces: `python spike/splat_prepare.py --sfm <dir> --images <dir> --out <dir> [--max-side 1280]` (menulis `images/` tak terdistorsi dan `sparse/0/`); `python spike/splat_check_frame.py --ply <file> --sfm <dir> [--threshold 0.02]` (keluar 0 bila rasio < ambang, selain itu 1).

- [ ] **Step 1: Salin tiga berkas dan bandingkan hash dengan sumber** (`sha256sum` di dua lokasi harus sama). Catatan memori: `splat_prepare.py` c7d6ca1e..., `splat_check_frame.py` b34f1549... (hash di PC lab; berkas laptop bisa berbeda, laporkan keduanya).
- [ ] **Step 2: Jalankan `pytest tests/test_splat_frame.py -q`.** Expected: lulus.
- [ ] **Step 3: Tambahkan tes bahwa `splat_check_frame` mengembalikan 1 untuk splat di kerangka salah** bila belum ada (cari di `test_splat_frame.py` dulu; jangan menduplikasi).
- [ ] **Step 4: `ruff check` dan `ruff format --check` pada ketiganya; perbaiki hanya gaya, bukan perilaku.**
- [ ] **Step 5: Commit** (atas perintah Bagus): `feat(splat): add the data prepare and frame check tools`.

### Task 3: Migrasi `0007`, model `SplatJob`, dan fungsi antrean `server/splat_jobs.py`

**Files:**
- Create: `server/migrations/versions/0007_splat_job.py`, `server/splat_jobs.py`, `tests/test_splat_jobs.py`
- Modify: `server/db.py` (model `SplatJob`)

**Interfaces:**
- Produces (`server/db.py`): `class SplatJob(SQLModel, table=True)`, tabel `splat_job`: `id: int | None` PK; `map_version_id: int` FK `map_version.id`, UNIK; `status: str = "queued"` (`queued|running|done|failed`); `stage: str | None`; `params: dict` JSON (bawaan `{"steps": 30000, "min_opacity": 0.02}`); `summary: dict | None` JSON; `error: str | None`; `created_at`, `started_at`, `finished_at` (`DateTime(timezone=True)`, pola `MapJob`).
- Produces (`server/splat_jobs.py`): `enqueue(session, map_version_id: int, params: dict | None = None) -> SplatJob` (baris baru `queued`, atau bila sudah ada dan `done|failed`, setel ulang menjadi `queued` dengan `error`/`summary`/`stage`/waktu dikosongkan; bila `queued|running` lempar `ValueError("already queued or running")`); `claim_next(session) -> SplatJob | None` (urut `id`, `with_for_update(skip_locked=True)`, menandai `running`, sama dengan `jobs.claim_next`); `set_stage(session, job, stage: str) -> None`; `finish(session, job, summary: dict) -> None`; `fail(session, job, error: str) -> None` (galat dipotong ke `jobs.ERROR_MAX`); `recover_stale(session) -> int` (semua `running` menjadi `failed` dengan pesan "the splat worker stopped mid-job; rebuild it"; sah karena satu instance).

- [ ] **Step 1: Tes merah.** `test_enqueue_creates_queued_row_with_default_params`, `test_enqueue_resets_a_failed_row_and_clears_error`, `test_enqueue_rejects_queued_and_running` (kedua mengangkat `ValueError`), `test_claim_next_takes_oldest_queued_and_marks_running`, `test_claim_next_returns_none_when_empty`, `test_recover_stale_marks_running_failed_and_counts_them`, `test_fail_truncates_error_to_jobs_error_max`, `test_one_row_per_version` (baris kedua untuk versi sama gagal, `IntegrityError`). Pola fixture sqlite seperti `tests/test_jobs.py`. Run: `pytest tests/test_splat_jobs.py -q`. Expected: FAIL (modul belum ada).
- [ ] **Step 2: Model `SplatJob`** di `server/db.py` mengikuti gaya `MapJob`.
- [ ] **Step 3: Implementasi `server/splat_jobs.py`** dengan helper `_save` sendiri: `session.add` + `commit` TANPA `refresh` (koreksi 9 Nov: `jobs._save` sengaja tanpa refresh karena refresh membuka transaksi yang tertahan selama subprocess panjang, "idle in transaction"; pelatihan splat ~16 menit). `enqueue` memilih baris lama dengan `with_for_update()` dan memetakan `IntegrityError` saat insert (dua permintaan bersamaan) ke `ValueError("already queued or running")` setelah `rollback`. `params` digabung di atas bawaan dan divalidasi: kunci hanya `steps` (int > 0, bukan bool) dan `min_opacity` (0 <= x < 1), selain itu `ValueError`.
- [ ] **Step 3b: Tes `test_migration_0006_up_down_up` di `tests/test_calibration_db.py` menegaskan head == "0006"** dan PASTI pecah begitu 0007 ada. Ubah HANYA pernyataan itu menjadi "0006 ada di rantai revisi" (bukan hard-code head baru, supaya migrasi berikutnya tidak memecahkannya lagi); sisanya tes itu tidak diubah.
- [ ] **Step 4: Migrasi `0007`** (`down_revision = "0006"`) membuat tabel, indeks unik `map_version_id`, dan `downgrade` yang menjatuhkannya. Tes `test_migration_0007_up_and_down` pada sqlite lewat Alembic `upgrade head` lalu `downgrade 0006` (ikuti cara `tests/test_db.py` menjalankan migrasi).
- [ ] **Step 5: Run `pytest tests/test_splat_jobs.py tests/test_db.py -q`.** Expected: lulus (kecuali kegagalan `alembic` garis dasar).
- [ ] **Step 6: Commit** (atas perintah Bagus): `feat(splat): splat_job table and queue functions`.

### Task 4: Pembuat perintah dan jalur `server/splat_pipeline.py`

**Files:**
- Create: `server/splat_pipeline.py`, `tests/test_splat_pipeline.py`

**Interfaces:**
- Consumes: `server.pipeline.run_dir(map_dir) -> Path`, `server.pipeline.SPIKE`.
- Produces (fungsi murni): `work_dir(data: Path, job_id: int) -> Path` (`data/jobs/<job_id>/splat`); `sfm_dir(map_dir: Path) -> Path` (`run_dir(map_dir) / "sfm"`); `dataset_dir(data: Path, job_id: int) -> Path` (`data/jobs/<job_id>/dataset`); `prepare_command(sfm: Path, images: Path, out: Path) -> list[str]`; `train_command(prepared: Path, result: Path, steps: int) -> list[str]`; `ply_path(result: Path, steps: int) -> Path` (`result/ply/point_cloud_<steps-1>.ply`); `check_command(ply: Path, sfm: Path) -> list[str]`; `convert_command(ply: Path, sog: Path) -> list[str]`; konstanta `TRAINER = "/opt/gsplat/examples/simple_trainer.py"` dan `SPLAT_TRANSFORM_CLI` (jalur skrip Node di image, diisi di Task 8 setelah diverifikasi).
- Semua argv berbentuk `[interpreter, SKRIP, ...]` karena `worker.run` melaporkan `Path(argv[1]).name` saat gagal.

- [ ] **Step 1: Tes merah.** `test_train_command_disables_viewer_and_world_normalization` (argv memuat `--disable-viewer`, `--no-normalize-world-space`, `--data-factor` `1`, `--max-steps` sama dengan `steps`, `--save-ply`, dan `--ply-steps` sama dengan `steps`), `test_ply_path_uses_last_step_index` (30000 menjadi `point_cloud_29999.ply`), `test_check_command_uses_default_threshold`, `test_convert_command_drops_spherical_harmonics` (argv memuat `-H` diikuti `0`), `test_every_command_has_a_script_at_argv1`, `test_paths_are_under_job_dir`. Run: `pytest tests/test_splat_pipeline.py -q`. Expected: FAIL.
- [ ] **Step 2: Implementasi** semua fungsi di atas.
- [ ] **Step 3: Tandai dua hal yang BELUM terverifikasi di komentar kode** dan di laporan: nama folder PLY (`ply/` dan pola `point_cloud_<step>.ply` dari pengamatan 3 Nov) serta bentuk pemanggilan `splat-transform` (`... -H 0 ...`). Keduanya dikunci di Task 8, bukan di sini.
- [ ] **Step 4: Run tes dan `ruff`.** Expected: lulus.
- [ ] **Step 5: Commit** (atas perintah Bagus): `feat(splat): command builders for the splat stages`.

### Task 5: Kunci GPU bersama `server/gpu_lock.py`

**Files:**
- Create: `server/gpu_lock.py`, `tests/test_gpu_lock.py`
- Modify: `server/worker.py` (`process` dan `main` membungkus pekerjaan dengan kunci), `tests/test_worker.py`

**Interfaces:**
- Produces: `GPU_LOCK_KEY: int` (satu konstanta); `gpu_lock(engine) -> ContextManager[None]`. Di PostgreSQL: buka satu `Connection` khusus dengan `isolation_level="AUTOCOMMIT"`, jalankan `SELECT pg_advisory_lock(:k)` (menunggu bila dipegang), lepas dengan `SELECT pg_advisory_unlock(:k)` di `finally`, lalu tutup koneksi. Di dialek lain (sqlite untuk tes): tidak melakukan apa pun. Kunci memakai koneksi khusus karena kunci sesi menempel pada koneksi, bukan pada `Session`, dan koneksi pool bisa berpindah antar transaksi; koneksi yang putus melepas kunci sendiri.
- Consumes: `worker.process(session, job, data, maps, runner, ...)` yang ada; tambahkan parameter opsional `lock: Callable[[], ContextManager[None]] | None = None` (bila `None`, dipakai `lambda: gpu_lock(session.get_bind())`) agar tes memberi kunci palsu.

- [ ] **Step 1: Tes merah.** `test_gpu_lock_is_a_noop_on_sqlite`; `test_gpu_lock_executes_lock_then_unlock_on_postgres` (engine palsu yang merekam SQL dan dialek `postgresql`, urutan: lock, unlock; unlock tetap jalan saat isi blok melempar); `test_worker_process_holds_the_lock_around_the_stages` (kunci palsu merekam enter/exit; `fake_runner` memverifikasi kunci sedang dipegang saat tiap perintah jalan); `test_worker_process_sets_gpu_wait_stage_before_blocking` (tahap job menjadi `gpu_wait` sebelum kunci diperoleh, lalu `extract`). Run. Expected: FAIL.
- [ ] **Step 2: Implementasi `gpu_lock`.**
- [ ] **Step 3: Ubah `worker.process`**: set tahap `gpu_wait`, ambil kunci, lalu jalankan tahap yang ada tanpa mengubah urutan atau perilakunya.
- [ ] **Step 4: Dashboard mengenal tahap `gpu_wait`**: cari daftar tahap (`web/components/PipelineStageIndicator.tsx` dan i18n) dan tambahkan teks "menunggu GPU" dua bahasa; bila daftar itu tertutup (hanya empat tahap tetap), ikuti pola yang ada dan laporkan. Verifikasi di browser dikerjakan Claude.
- [ ] **Step 5: Run `pytest tests/test_gpu_lock.py tests/test_worker.py -q`.** Expected: lulus.
- [ ] **Step 6: Commit** (atas perintah Bagus): `feat(worker): share one GPU lock with the splat worker`.

### Task 6: `server/splat_worker.py` (proses, tempatkan, pulihkan)

**Files:**
- Create: `server/splat_worker.py`, `tests/test_splat_worker.py`

**Interfaces:**
- Consumes: Task 3 (`splat_jobs.*`), Task 4 (pembuat perintah), Task 5 (`gpu_lock`), `worker.run`, `worker.StageError`, `worker.MIN_FREE_BYTES`, `spike.splat_prune.prune_sog`, `db.MapVersion`, `db.MapJob`.
- Produces: `process(session, job, data: Path, maps: Path, runner=worker.run, lock=...) -> None` dan `main() -> None` (pola `worker.main`: `recover_stale` saat mulai, lalu putaran `claim_next` dengan `POLL_S`).
- Urutan tahap dan nama `stage`: `prepare`, `train`, `check`, `convert`, `prune`, `place`. Gagal pada tahap mana pun menghasilkan `splat_jobs.fail` dengan pesan galat dan ekor log, dan **tidak menyentuh `map_job` maupun `map_version`**.

- [ ] **Step 1: Tes merah dengan `fake_runner` (pola `tests/test_worker.py`)** yang menulis keluaran palsu tiap tahap (PLY kecil, `.sog` sintetis dari helper `make_synthetic_sog` di `tests/test_splat_prune.py` bila bisa diimpor, atau buat helper bersama di `tests/`): `test_happy_path_writes_scene_sog_and_report_and_removes_work_dir`; `test_stage_failure_marks_job_failed_with_that_stage_and_leaves_map_untouched` (parametrik untuk lima tahap pertama); `test_check_failure_when_ratio_fails_leaves_no_scene_sog` (Review Focus 6); `test_place_is_atomic_old_scene_sog_survives_a_failed_rebuild` (Review Focus 4); `test_place_refuses_when_version_folder_is_gone` (tidak membuat folder; Review Focus 3); `test_version_without_job_or_frames_fails_with_clear_error` (Review Focus 5); `test_low_disk_fails_before_any_stage` (memakai `free_bytes` palsu seperti `worker.process`); `test_work_dir_kept_on_failure_and_removed_on_rebuild`; `test_recover_on_start_marks_running_failed` (Review Focus 2). Run: `pytest tests/test_splat_worker.py -q`. Expected: FAIL.
- [ ] **Step 2: Implementasi `process`.** Cari `MapJob` lewat `map_version_id`; frame di `dataset_dir`, SfM di `sfm_dir(map_dir)`. Setiap tahap lewat `runner(argv, log)` dengan log `<work_dir>/log.txt`. `prune` memanggil `prune_sog(..., min_opacity=job.params["min_opacity"])`. `place` menulis `splat/scene.sog` dan `splat/report.json` (ringkasan: jumlah Gaussian sebelum dan sesudah, `steps`, `min_opacity`, rasio `check`, durasi tahap) lewat berkas sementara + `os.replace`, hanya bila folder versi masih ada.
- [ ] **Step 3: Implementasi `main`.** `gpu_lock` dipegang hanya selama tahap `train` (satu-satunya yang memakai GPU; `convert -H 0` jalan di CPU); `prepare`, `check`, `convert`, `prune`, `place` tidak memegang kunci.
- [ ] **Step 4: Run tes dan `ruff`.** Expected: lulus.
- [ ] **Step 5: Commit** (atas perintah Bagus): `feat(splat): the splat worker process`.

### Task 7: API `splat_status` dan bangun ulang, dan dashboard

**Files:**
- Modify: `server/maps_api.py`, `tests/test_maps_api.py`, `web/lib/api.ts`, `web/app/maps/page.tsx`, `web/lib/i18n/id.ts`, `web/lib/i18n/en.ts`

**Interfaces:**
- Consumes: `splat_jobs.enqueue`, `db.SplatJob`.
- Produces: `VersionOut.splat_status: str | None` (`queued|running|done|failed`, null bila tanpa baris); `POST /api/versions/{id}/splat/rebuild` → 202 `{"status": "queued"}`; 404 bila versi tidak ada; 409 `{"detail": {"code": "splat_busy", ...}}` bila `queued|running`. `has_splat` tetap berbasis berkas.

- [ ] **Step 1: Tes merah** di `tests/test_maps_api.py`: `test_splat_status_is_null_without_a_row_and_reflects_the_row`, `test_rebuild_queues_a_failed_or_done_job`, `test_rebuild_creates_a_row_when_none_exists`, `test_rebuild_409_when_queued_or_running`, `test_rebuild_404_for_unknown_version`, `test_rebuild_requires_login`.
- [ ] **Step 2: Implementasi** rute dan field.
- [ ] **Step 3: Dashboard**: tipe `Version.splat_status`, lencana status di baris versi dan drawer (id dan en, `splat.status.*`), tombol "Bangun ulang 3D" (teks, tanpa ikon baru), pesan galat jujur dari status `failed`. Tanpa data karangan dan tanpa ikon yang tidak ada di `web/public/icons`.
- [ ] **Step 4: Run `pytest`, `ruff`, `npx tsc --noEmit`, `npm run build`.** Verifikasi di browser dikerjakan Claude (desktop dan 375 px).
- [ ] **Step 5: Commit** (atas perintah Bagus): `feat(splat): splat status and rebuild in the API and dashboard`.

### Task 8: Image `splat-worker`, compose, dan verifikasi PC lab (setiap langkah minta izin Bagus)

**Files:**
- Create: `deploy/Dockerfile.splat`
- Modify: `deploy/compose.yaml`, `deploy/compose.gpu.yaml`, `deploy/README.md`

**Interfaces:**
- Produces: layanan `splat-worker` (`python -m server.splat_worker`), image dari `deploy/Dockerfile.splat`, mount `/maps` dan `/data` baca tulis (bind mount tidak bisa sebagian), `DATABASE_URL` sama dengan `worker`, `init: true`, `shm_size: "2gb"`, `restart: unless-stopped`, reservasi GPU di `compose.gpu.yaml`, `depends_on: api: service_started`, `healthcheck` dimatikan seperti `worker`.

- [ ] **Step 1 (baca saja): ambil `~/splat/Dockerfile` dari PC lab** (Dockerfile terbukti `eutopos-splat:local`: PyTorch 2.4.0 CUDA 12.1 devel, gsplat 1.5.3, `examples/requirements` dengan fork pycolmap, JIT CUDA dipanggang dengan `MAX_JOBS=4` dan arsitektur 8.6, `TORCH_EXTENSIONS_DIR=/opt/torch_extensions`) dan bobot yang diunduh LPIPS (AlexNet) saat pelatihan. Tulis `deploy/Dockerfile.splat` dari itu, menambah: kode `server/` dan `spike/`, Python deps layanan, Node 22 dengan `@playcanvas/splat-transform` 3.10.3 dipin, dan bobot LPIPS sudah ada di image (jangan mengunduh saat berjalan; `TORCH_HOME` menunjuk ke sana).
- [ ] **Step 2 (baca saja, di image): `splat-transform --help` dan jalur skrip CLI-nya**; isi `SPLAT_TRANSFORM_CLI` dan bentuk `convert_command` di Task 4 dengan bukti itu, dan tes yang sesuai.
- [ ] **Step 3 (baca saja): daftar isi `~/splat/runs/lorong-lama-30000`** untuk memastikan nama folder dan berkas PLY; koreksi `ply_path` bila berbeda.
- [ ] **Step 4 (izin): bangun image** `docker compose -f compose.yaml -f compose.gpu.yaml build splat-worker`. Catat durasi dan ukuran. Build pertama `eutopos-splat` pernah gagal (galat containerd) dan berhasil pada percobaan ulang; penyebabnya belum terbukti.
- [ ] **Step 5 (izin): uji ujung ke ujung pada data lorong lama** (`lorong-lama`, 401 frame): satu `splat_job` nyata lewat layanan. Ukur: durasi per tahap, **VRAM puncak total** (`nvidia-smi` tiap 30 detik; berhenti bila > 7,5 GB), RAM terendah. Hasilnya menetapkan (a) ambang VRAM bebas sebelum melatih dan (b) perlu tidaknya batas memori proses. Tulis angkanya apa adanya di `docs/splat-prune.md` atau berkas baru, bukan dari ingatan.
- [ ] **Step 6 (izin): bukti hasil.** `scene.sog` yang dihasilkan dibandingkan dengan `scene-asli.sog` buatan tangan (jumlah Gaussian setelah pangkas, ukuran, dan `splat_check_frame` lulus), lalu dibuka di viewer (Claude memverifikasi di browser).
- [ ] **Step 7: Commit** (atas perintah Bagus): `feat(deploy): splat-worker service and image`.

### Task 9: Pemicu setelah peta jadi (terakhir, setelah layanan terbukti di PC lab)

**Files:**
- Modify: `server/worker.py` (`process`), `tests/test_worker.py`

**Interfaces:**
- Consumes: `splat_jobs.enqueue(session, version.id)`.

- [ ] **Step 1: Tes merah.** `test_finishing_a_map_job_enqueues_a_splat_job_for_the_new_version`; `test_enqueue_failure_does_not_fail_the_map_job` (monkeypatch `enqueue` melempar; `job.status` tetap `done`, `map_version` ada); `test_failed_map_job_enqueues_nothing`.
- [ ] **Step 2: Implementasi** di `worker.process` tepat setelah `jobs.finish`: bungkus `try/except Exception` yang mencatat ke log dan tidak melempar ulang.
- [ ] **Step 3: Run `pytest tests/test_worker.py -q`.** Expected: lulus.
- [ ] **Step 4: Commit** (atas perintah Bagus): `feat(worker): enqueue a splat job after a map is registered`.

### Task 10: Dokumentasi dan penutup

**Files:**
- Modify: `CLAUDE.md` (bagian arsitektur singkat dan aturan), `docs/specs/2026-11-09-splat-pipeline-design.md` (status menjadi "diimplementasikan", angka terukur Task 8), `docs/plans/2026-11-01-gaussian-splat-lantai-10.md` (catatan bahwa Task 1 sampai 3 kini otomatis)

- [ ] **Step 1: Perbarui dokumen** dengan angka terukur Task 8 dan batas yang masih berlaku (gedung besar, pita SH, pose di luar jalur latih).
- [ ] **Step 2: Suite penuh, `ruff`, `tsc`, `npm run build`, dan cek tanpa em dash.**
- [ ] **Step 3: Ulasan cabang penuh** oleh pengulas segar sebelum PR; PR lewat alur repo (CI hijau, rebase merge). Commit dan push hanya atas perintah Bagus.
