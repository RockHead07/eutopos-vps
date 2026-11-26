# Laporan Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Setiap job peta `done` atau ditolak gerbang punya kartu laporan beku di `summary["report"]`, tampil di dashboard bersama statistik pemakaian peta yang hidup, dan bisa diunduh sebagai CSV.

**Architecture:** Fungsi murni di `server/scan_report.py` menyusun kartu dari data yang sudah dibaca. Worker mengukur waktu tahap dan memanggil penyusun kartu tepat sebelum `jobs.finish`/`jobs.reject`. CLI `manage report` mengisi job lama. Endpoint `/api/jobs/{id}/usage` menghitung statistik `localize_request`. Web hanya menampilkan.

**Tech Stack:** Python 3, FastAPI, SQLModel, numpy, pycolmap (sudah terpasang); Next.js + TypeScript; pytest; `node --test` untuk `web/lib/*.test.ts`.

**Spec:** `docs/specs/2026-11-25-laporan-scan-design.md`

## Global Constraints

- Kartu: `{"version": 1, "computed_at": ISO UTC, "recording", "network", "processing", "quality"}`; `REPORT_VERSION = 1`.
- Tidak diketahui = `null` plus `"<kunci>_reason"`; reason yang dipakai: `"not_recorded"`, `"no_arcore"`, `"cli_job"`, `"video_deleted"`, `"no_meta"`. Jangan pernah `0` untuk tidak diketahui.
- Luas: `{"method": "trajectory_buffer", "radius_m": 1.0, "cell_m": 0.25, "frame": "aligned_sfm" | "arcore_per_segment"}`.
- Peringatan multi-lantai bila `height_range_m > 2.5`.
- Error apa pun saat menyusun kartu: `{"version": 1, "error": "<teks>"}`, job tetap selesai normal.
- Tanpa dependensi baru (server maupun web). Tanpa migrasi database.
- Pemakaian dipisah `served` (`candidate = false`) dan `candidate`; hanya untuk staf (`uploads.User`), tidak untuk token aplikasi.
- Pemakaian tidak masuk CSV.
- Teks UI lewat `web/lib/i18n/en.ts` dan `id.ts`; tanpa em dash di teks Indonesia.
- Commit hanya bila Bagus memerintahkan; pesan commit tanpa atribusi AI. Langkah "Commit" di bawah berarti: siapkan commit, jalankan setelah izin.

## Review Focus

1. Job lama tanpa `summary.report` (atau `summary` null): halaman job dan daftar job tetap tampil, panel menulis "belum ada laporan". Uji: Task 8 `reportCsv` menerima job tanpa report.
2. Kartu berisi `error`: panel menampilkan pesannya, bukan crash atau kosong. Uji: Task 8 `reportCsv` mengisi kolom `report.error`.
3. `frames.jsonl` rusak (baris bukan JSON, BOM): `recording` jadi null dengan reason, kartu lain tetap terisi. Uji: Task 4 `test_corrupt_frames_only_nulls_recording`.
4. Foto tunggal atau durasi nol: `mean_speed_m_s` null, bukan pembagian nol. Uji: Task 3 `test_single_photo`.
5. Hook unggah dipanggil untuk job yang sudah tidak `uploading`: tidak menulis waktu. Uji: Task 2 `test_upload_times_ignore_non_uploading_job`.

---

### Task 1: Durasi video dari `mvhd`

**Files:**
- Modify: `server/video_meta.py`, `server/worker.py` (`stamp_recorded`)
- Modify: `tests/mp4_builder.py`, `tests/test_video_meta.py`, `tests/test_worker.py`

**Interfaces:**
- Produces: `video_meta.duration_s(path: Path) -> float | None`; entri video setelah `stamp_recorded` berisi `"duration_s": float | None`.

- [ ] **Step 1: Perluas builder dan tulis tes**

`mvhd(when, version=0, timescale=0, duration=0)`: setelah creation dan modification, tulis `timescale` (>I) lalu `duration` (>I untuk versi 0, >Q untuk versi 1), sisa padding sampai 80 byte. Default 0 menjaga tes lama.

```python
@pytest.mark.parametrize("version", [0, 1])
def test_duration_from_mvhd(write, version):
    assert (
        video_meta.duration_s(write(mp4(NOW, version=version, timescale=600, duration=600 * 95)))
        == 95.0
    )


def test_zero_timescale_or_duration_is_unknown(write):
    assert video_meta.duration_s(write(mp4(NOW, timescale=0, duration=10))) is None
    assert video_meta.duration_s(write(mp4(NOW, timescale=600, duration=0))) is None


def test_duration_garbage_never_raises(write):
    assert video_meta.duration_s(write(b"\x00" * 50)) is None
```

Plus di `test_worker.py`: `test_stamp_recorded_adds_duration` (video mp4 dengan durasi 95 s menghasilkan `duration_s == 95.0`; entri `kind == "frames"` menghasilkan `None`).

- [ ] **Step 2: Jalankan, harus gagal**

Run: `pytest tests/test_video_meta.py tests/test_worker.py -k "duration" -v`
Expected: FAIL (`duration_s` belum ada / argumen builder tidak dikenal)

- [ ] **Step 3: Implementasi**

`duration_s` memakai `_find` yang sudah ada untuk `moov`/`mvhd`; baca versi, lewati creation+modification (8 atau 16 byte), baca timescale dan duration. `None` bila salah satunya 0 atau error baca. `stamp_recorded` menambah `duration_s` di samping `recorded_at` (hanya bila bukan `frames` dan berkas ada).

- [ ] **Step 4: Jalankan semua tes berkas itu**

Run: `pytest tests/test_video_meta.py tests/test_worker.py -v`
Expected: PASS

- [ ] **Step 5: Commit** `feat(report): baca durasi video dari mvhd sebelum video dihapus`

### Task 2: Waktu unggah di entri video

**Files:**
- Modify: `server/uploads.py` (`_pre_create`, `_pre_finish`)
- Test: `tests/test_uploads.py`

**Interfaces:**
- Produces: entri video berisi `"upload_started_at": ISO str` (ditulis pre-create, ditimpa bila klien mulai dari nol) dan `"uploaded_at": ISO str` (ditulis pre-finish). Pakai `_utc_now()` yang sudah ada supaya bisa di-monkeypatch.

- [ ] **Step 1: Tulis tes**

- `test_upload_times_recorded`: alur penuh seperti `test_full_upload_flow_queues_after_last_video`, monkeypatch `uploads._utc_now` ke T0 saat pre-create dan T1 saat pre-finish; entri video punya `upload_started_at == T0.isoformat()` dan `uploaded_at == T1.isoformat()`.
- `test_restart_from_zero_resets_start`: dua pre-create untuk video yang sama (T0 lalu T2); `upload_started_at == T2`.
- `test_upload_times_ignore_non_uploading_job`: job sudah `queued`; hook tidak mengubah `videos`.

- [ ] **Step 2: Jalankan, harus gagal**

Run: `pytest tests/test_uploads.py -k "upload_times or restart_from_zero" -v`
Expected: FAIL (kunci tidak ada)

- [ ] **Step 3: Implementasi** (dua baris tambahan di dict entri video pada kedua hook; tidak ada perilaku lain berubah)

- [ ] **Step 4: Jalankan**

Run: `pytest tests/test_uploads.py -v`
Expected: PASS

- [ ] **Step 5: Commit** `feat(report): catat waktu mulai dan selesai unggah per video`

### Task 3: Penyusun kartu (fungsi murni)

**Files:**
- Create: `server/scan_report.py`
- Test: `tests/test_scan_report.py`

**Interfaces:**
- Produces:
  - `REPORT_VERSION = 1`, `FOOTPRINT = {"method": "trajectory_buffer", "radius_m": 1.0, "cell_m": 0.25}`, `MULTI_FLOOR_M = 2.5`
  - `footprint_m2(polylines: list[np.ndarray], radius_m: float, cell_m: float) -> float` (tiap array Nx2, satu per segmen; dihitung bersama dalam satu grid)
  - `recording(frames: list[dict] | None, meta: dict | None, aligned: dict[str, np.ndarray] | None, video_seconds: float | None, run: dict) -> dict` (`aligned`: nama foto ke pusat kamera di kerangka bangunan meter, Z ke atas; `None` bila penyelarasan tidak `applied`)
  - `network(videos: list[dict]) -> dict` (kunci `uploads`, `total_bytes`, `seconds`, `mbps`)
  - `processing(job: MapJob, now: datetime, live: dict, run: dict) -> dict` (`live = {"stage_seconds": dict, "gpu_wait_s": float | None}`)
  - `quality(summary: dict, model_stats: dict | None) -> dict`
  - `build(*, recording, network, processing, quality, now: datetime) -> dict`

Aturan yang tidak ditentukan signature:
- ARCore Y ke atas: bidang lantai = (X, Z), tinggi = Y. Kerangka `aligned`: lantai = (X, Y), tinggi = Z.
- `frame = "aligned_sfm"` bila `aligned` berisi >= 2 foto yang juga ada di `frames`; polyline dibentuk dari foto berurutan `t_ns` per segmen memakai posisi `aligned`. Selain itu `"arcore_per_segment"`: luas tiap segmen dihitung sendiri lalu dijumlah, dan tambahkan `"footprint_upper_bound": true` bila segmen > 1.
- `footprint_m2`: grid mencakup bbox semua titik + `radius_m`; sel dihitung bila jarak titik tengah ke ruas terdekat <= `radius_m` (jarak titik ke ruas, vektorisasi numpy per ruas).
- `network`: semua `size` null (job CLI) = keempat kunci null dengan `uploads_reason: "cli_job"`; ada video tanpa `upload_started_at` atau `uploaded_at` = keempat kunci null dengan `uploads_reason: "not_recorded"`.
- `processing.queue_s`: `started_at - max(uploaded_at)`; job tanpa `size` memakai `created_at`; job dengan `size` tapi tanpa `uploaded_at` = null reason `not_recorded`. `total_s = now - started_at`.

- [ ] **Step 1: Tulis tes**

```python
def test_straight_line_footprint():
    line = np.array([[0.0, 0.0], [10.0, 0.0]])
    area = scan_report.footprint_m2([line], 1.0, 0.25)
    assert abs(area - (20 + math.pi)) <= 2 * 10.5 * 0.25  # toleransi satu lapis sel di keliling

def test_back_and_forth_does_not_double():
    there = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 0.0]])
    assert scan_report.footprint_m2([there], 1.0, 0.25) == scan_report.footprint_m2([there[:2]], 1.0, 0.25)

def test_duration_and_path_per_segment():
    # segmen 0: dua foto 1 s, 3 m di X; segmen 1 mulai 100 s kemudian: dua foto 2 s, 4 m di Z, Y naik 5 m
    r = scan_report.recording(FRAMES_TWO_SEGMENTS, None, None, None, RUN)
    assert r["duration_s"] == 3.0 and r["path_length_m"] == 7.0 and r["segments"] == 2

def test_per_segment_footprint_is_flagged_upper_bound(): ...
    # dua segmen terpisah 50 m: frame == "arcore_per_segment", footprint_upper_bound is True,
    # footprint_m2 == jumlah luas tiap segmen

def test_aligned_frame_used_when_available(): ...
    # aligned untuk semua foto: frame == "aligned_sfm", height_range_m dari Z

def test_meta_fields_and_missing_meta():
    # meta {"tracking_losses": 2, "device_model": "TECNO KL7"} terbaca; meta None -> null + "no_meta"

def test_single_photo():
    # satu foto: duration_s == 0.0, path_length_m == 0.0, mean_speed_m_s is None, footprint == luas lingkaran (+-toleransi)

def test_video_job_recording():
    # frames None, video_seconds 95.0: source "video", duration_s 95.0,
    # path_length_m None dengan path_length_m_reason "no_arcore"; video_seconds None -> reason "video_deleted"

def test_multi_floor_warning():
    # height_range_m 3.0 -> "warnings" berisi "multi_floor"

def test_network_mbps():
    # satu video 100_000_000 byte, 80 s -> mbps == 10.0; CLI -> uploads_reason "cli_job"; tanpa waktu -> "not_recorded"

def test_queue_and_total():
    # started 10 s setelah uploaded_at terakhir -> queue_s == 10.0; now - started == total_s

def test_quality_copies_summary():
    # dari summary run/inspect/align/gate + model_stats: registered, images, points3d, parts == len(inspect.parts),
    # params berisi features/matcher/max_keypoints/resize_max/sequential_pairs; model_stats None -> tiga metrik null
```

Isi `...` sebagai assert konkret sesuai komentar.

- [ ] **Step 2: Jalankan, harus gagal**

Run: `pytest tests/test_scan_report.py -v`
Expected: FAIL (modul belum ada)

- [ ] **Step 3: Implementasi `server/scan_report.py`** sesuai Interfaces dan aturan di atas.

- [ ] **Step 4: Jalankan**

Run: `pytest tests/test_scan_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit** `feat(report): penyusun kartu laporan scan`

### Task 4: Worker menyusun kartu

**Files:**
- Modify: `server/scan_report.py` (tambah pembaca disk), `server/worker.py` (`process`)
- Test: `tests/test_worker.py`, `tests/test_scan_report.py`

**Interfaces:**
- Consumes: Task 1 `duration_s` di entri video; Task 3 seluruh fungsi.
- Produces:
  - `scan_report.model_stats(sfm_dir: Path) -> dict | None` (`mean_reprojection_error_px`, `mean_track_length`, `mean_observations_per_image` dari `pycolmap.Reconstruction`; verifikasi nama metode terhadap pycolmap terpasang, None bila gagal)
  - `scan_report.aligned_centers(map_dir: Path, summary: dict) -> dict[str, np.ndarray] | None` (bila `summary["align"]["status"] == "applied"`: `quick_align.load_model(run/sfm)` lalu `sim3.from_align(json(run/align.json)["meter_from_model"])` diterapkan ke tiap pusat)
  - `scan_report.from_disk(job: MapJob, map_dir: Path, summary: dict, live: dict, now: datetime) -> dict` (baca `capture/frames.jsonl` via `quick_align.read_frames`, `capture/meta.json`, jumlah `duration_s` video peran peta; setiap bagian dibungkus sendiri: error di satu bagian = bagian itu `{"error": ...}`; error di luar itu = `{"version": 1, "error": ...}`)

- [ ] **Step 1: Tulis tes**

- `test_process_success_registers_candidate_and_spares_cli_files`: ubah assertion `job.summary == {...}` menjadi `{k: v for k, v in job.summary.items() if k != "report"} == {...}` dan tambahkan `assert job.summary["report"]["version"] == 1`.
- `test_report_on_gate_reject`: job yang ditolak gerbang punya `summary["report"]`.
- `test_report_error_does_not_fail_job`: monkeypatch `scan_report.from_disk` agar raise; job tetap `done` dan `summary["report"] == {"version": 1, "error": ...}`.
- `test_stage_seconds_recorded`: `report["processing"]["stage_seconds"]` berisi kunci `gpu_wait, extract, build, inspect, register, align, gate`.
- `test_corrupt_frames_only_nulls_recording` (di `test_scan_report.py`): `frames.jsonl` berisi baris rusak; `from_disk` menghasilkan `recording` dengan `error`, `quality` tetap terisi.

- [ ] **Step 2: Jalankan, harus gagal**

Run: `pytest tests/test_worker.py tests/test_scan_report.py -v`
Expected: FAIL pada tes baru

- [ ] **Step 3: Implementasi**

Di `process()`: helper lokal `stage(name)` yang memanggil `jobs.set_stage` dan mencatat `time.monotonic()`; lama tahap = selisih ke tahap berikutnya. `gpu_wait_s` = lama tahap `gpu_wait`. Tepat sebelum `jobs.reject(...)` dan `jobs.finish(...)`, tutup tahap terakhir lalu `summary["report"] = safe_report(...)`, di mana pemanggilan `from_disk` dibungkus try/except di worker juga (lapis kedua). Ruling bila ragu: `total_s` dihitung dari `now` saat kartu disusun, bukan `finished_at`.

- [ ] **Step 4: Jalankan seluruh suite server**

Run: `pytest -q`
Expected: semua PASS kecuali kegagalan lama yang sudah ada sebelum Task 1 (catat garis dasar sebelum mulai).

- [ ] **Step 5: Commit** `feat(report): worker menyimpan kartu laporan saat job selesai`

### Task 5: CLI `manage report`

**Files:**
- Modify: `server/worker.py` (fungsi isi ulang), `server/manage.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Produces: `worker.backfill_reports(session: Session, maps: Path, job_id: int | None = None, force: bool = False) -> tuple[int, int]` (dibuat, dilewati); subperintah `report [--job N] [--force]` mencetak `"{made} laporan dibuat, {skipped} dilewati"`.

Aturan: hanya job `done` atau (`failed` dan `stage == "gate"`) dengan folder `maps/<area>/job-<id>` ada. Lewati bila `report.version == REPORT_VERSION` dan tidak `--force`. `live` diambil dari kartu lama (`processing.stage_seconds`, `processing.gpu_wait_s`) bila ada, selain itu null dengan reason `not_recorded`. `now` untuk `total_s` diganti `finished_at` job (ruling: job lama tidak boleh memakai jam sekarang).

- [ ] **Step 1: Tulis tes**

- `test_backfill_skips_same_version_unless_forced`
- `test_backfill_force_keeps_live_fields`: kartu lama punya `stage_seconds = {"build": 5.0}`; setelah `force=True` nilainya tetap.
- `test_backfill_old_job_nulls_unrecoverable`: job tanpa `uploaded_at` dan tanpa `duration_s` menghasilkan reason `not_recorded`/`video_deleted`; `total_s == finished_at - started_at`.

- [ ] **Step 2: Jalankan, harus gagal**

Run: `pytest tests/test_worker.py -k backfill -v`
Expected: FAIL

- [ ] **Step 3: Implementasi** (`processing()` dari Task 3 menerima `now`; pass `job.finished_at` di sini)

- [ ] **Step 4: Jalankan**

Run: `pytest tests/test_worker.py -v`
Expected: PASS

- [ ] **Step 5: Commit** `feat(report): isi ulang kartu laporan job lama lewat manage report`

### Task 6: Endpoint pemakaian peta

**Files:**
- Modify: `server/uploads.py` (route baru di router yang sama dengan `GET /api/jobs/{id}`)
- Test: `tests/test_uploads.py`

**Interfaces:**
- Produces: `GET /api/jobs/{job_id}/usage` -> `{"map_version": int | null, "served": Group, "candidate": Group}`; `Group = {"requests": int, "ok_ratio", "wall_s_p50", "wall_s_p95", "inliers_median", "first_at", "last_at"}` (semua null bila `requests == 0`). Dependensi `user: User` (bukan `CaptureUser`). 404 bila job tidak ada; job tanpa versi: kedua grup kosong.

Persentil: `statistics.quantiles(values, n=100, method="inclusive")` indeks 49 dan 94; satu nilai = nilai itu sendiri. Cocokkan `LocalizeRequest.area_id == job.area_id` dan `LocalizeRequest.map_version == MapVersion.version`.

- [ ] **Step 1: Tulis tes**

- `test_usage_splits_served_and_candidate`: 3 baris served (2 ok) dan 1 baris candidate untuk versi job, 1 baris versi lain; served `requests == 3`, `ok_ratio == 2/3`; candidate `requests == 1`.
- `test_usage_empty`: tanpa baris, `requests == 0` dan statistik null.
- `test_usage_rejects_app_token`: token aplikasi capture mendapat 401/403 (ikuti pola `test_app_tokens.py`).

- [ ] **Step 2: Jalankan, harus gagal**

Run: `pytest tests/test_uploads.py -k usage -v`
Expected: FAIL (404 route)

- [ ] **Step 3: Implementasi**

- [ ] **Step 4: Jalankan**

Run: `pytest tests/test_uploads.py tests/test_app_tokens.py -v`
Expected: PASS

- [ ] **Step 5: Commit** `feat(report): endpoint pemakaian peta per job`

### Task 7: Panel laporan di halaman job

**Files:**
- Modify: `web/lib/api.ts` (tipe `ScanReport`, `Usage`, fungsi ambil usage)
- Create: `web/components/ScanReportPanel.tsx`, `web/components/MapUsagePanel.tsx`
- Modify: `web/app/job/page.tsx`, `web/lib/i18n/en.ts`, `web/lib/i18n/id.ts`

**Interfaces:**
- Consumes: bentuk kartu (Global Constraints, spec 4.1-4.4) dan respons Task 6.
- Produces: tipe `ScanReport` di `web/lib/api.ts` dipakai Task 8.

Aturan tampilan: empat kelompok (Rekaman, Jaringan, Proses, Kualitas peta) sesuai sketsa spec bagian 7; null = teks i18n "tidak tercatat" + alasan; tampilkan cara hitung luas (radius, grid, kerangka) dan label "batas atas" bila `footprint_upper_bound`; peringatan multi-lantai; kartu `error` = pesan error; job tanpa report = "belum ada laporan". `MapUsagePanel` memuat usage saat halaman dibuka, berlabel "diperbarui saat halaman dibuka", dua baris (dilayani, uji kandidat). Format angka memakai `formatNumber` yang ada. Jangan menggandakan angka dari panel status eksekusi yang sudah ada.

- [ ] **Step 1: Implementasi komponen dan teks i18n**
- [ ] **Step 2: Verifikasi tipe dan build**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: tanpa error

- [ ] **Step 3: Verifikasi manual di browser** (dev server lokal ke backend uji, atau data contoh): job capture dengan kartu lengkap, job video lama tanpa kartu, kartu dengan `error`. Ambil screenshot ketiganya.

- [ ] **Step 4: Commit** `feat(web): panel laporan scan dan pemakaian peta di halaman job`

### Task 8: CSV dan tabel pembanding

**Files:**
- Create: `web/lib/reportCsv.ts`, `web/lib/reportCsv.test.ts`
- Modify: `web/app/jobs/page.tsx`, `web/lib/i18n/en.ts`, `web/lib/i18n/id.ts`

**Interfaces:**
- Consumes: `Job`, `ScanReport` (Task 7).
- Produces: `reportColumns(jobs: Job[]): string[]` (kolom tetap `id, area_id, status, created_at, report.version, report.error` lalu jalur kunci skalar kartu terurut, misalnya `recording.duration_s`); `reportCsv(jobs: Job[]): string` (RFC 4180: koma, kutip ganda bila perlu, `\r\n`; baris pertama komentar `# rows: N`).

- [ ] **Step 1: Tulis tes**

```ts
test("job without report still gets a row", () => {
  const csv = reportCsv([jobWithReport, jobWithoutReport]);
  assert.equal(csv.split("\r\n").filter(Boolean).length, 1 + 1 + 2); // komentar, header, 2 baris
});
test("error card fills report.error", () => { /* kolom report.error berisi teks error */ });
test("values with commas and quotes are escaped", () => { /* device_model 'A, "B"' -> "A, ""B""" */ });
test("null becomes empty cell, not 0", () => { /* recording.path_length_m null -> sel kosong */ });
```

- [ ] **Step 2: Jalankan, harus gagal**

Run: `node --test web/lib/reportCsv.test.ts`
Expected: FAIL (modul belum ada)

- [ ] **Step 3: Implementasi `reportCsv.ts`**, lalu tombol "Unduh CSV" di `jobs/page.tsx` (Blob + `URL.createObjectURL`, nama `laporan-scan-<tanggal>.csv`) dan tabel pembanding ringkas (durasi, lintasan, luas, Mbps, total proses, terdaftar/total, reproyeksi) dengan unit di judul kolom.

- [ ] **Step 4: Jalankan tes dan build**

Run: `node --test web/lib/*.test.ts && cd web && npx tsc --noEmit && npm run build`
Expected: PASS, build tanpa error

- [ ] **Step 5: Commit** `feat(web): unduh CSV dan tabel pembanding laporan scan`

---

## Setelah semua task

- Kirim ke staging/PC lab dan jalankan `manage report` hanya dengan izin Bagus.
- Uji lapangan satu job capture baru end-to-end: kartu lengkap termasuk Mbps dan `stage_seconds`.
