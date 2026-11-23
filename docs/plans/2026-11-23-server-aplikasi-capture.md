# Server untuk aplikasi capture (S1, S3, S4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplikasi capture bisa membuat pekerjaan dan mengunggah dengan token aplikasinya sendiri, pekerjaannya tidak pernah
terbit otomatis, dan perekam bisa menguji lokalisasi terhadap versi kandidat tanpa mengganti peta yang dilayani.

**Architecture:** Modul baru `server/app_tokens.py` memegang token aplikasi (hash di tabel `app_token`) dan satu dependency
`CaptureUser` yang menerima email Access atau token aplikasi; dependency itu hanya dipasang di rute capture, jadi rute lain
tidak pernah menerima token aplikasi. Modul baru `server/candidate_map.py` memuat paling banyak satu `Localizer` kandidat di
samping peta yang dilayani; rute `POST /versions/{version_id}/localize` memakai ulang jalur `/localize` yang ada. Pekerja
tidak menandai `ready` untuk pekerjaan beridentitas aplikasi.

**Tech Stack:** Python 3, FastAPI, SQLModel, Alembic, pytest; dashboard Next.js (static export) di `web/`.

**Spec:** `D:/wt/capture-design/docs/specs/2026-11-23-aplikasi-capture-matang-design.md` (repo eutopos-mobile, cabang
`docs/aplikasi-capture-matang`), bagian 6 (S1, S3, S4) dan bagian 4 (keputusan Bagus). S2 (titik peta) bukan bagian rencana
ini.

## Global Constraints

- **Jangan commit, push, PR, atau merge.** Bagus yang memutuskan commit. Langkah "Commit" di rencana ini diganti dengan
  mencatat berkas yang berubah di laporan.
- Baca `CLAUDE.md` repo (aturan 1 sampai 10). TDD: tes gagal dulu, lalu implementasi.
- Tanpa dependensi baru (Python maupun npm). Token memakai `secrets` dan `hashlib` dari stdlib.
- Jangan mengubah kontrak `/localize` (`LocalizeResponse`, `CONTRACT_VERSION`). Rute kandidat memakai model respons yang
  sama persis.
- Jangan menyentuh PC lab, production, Cloudflare, atau rahasia. Tugas 6 adalah langkah manual Bagus.
- Pesan galat API dalam bahasa Inggris, seperti yang ada. Komentar dan docstring bahasa Indonesia, istilah teknis Inggris,
  tanpa em dash.
- Identitas aplikasi ditulis persis `app:<nama>`; nama token mengikuti pola `^[a-z0-9][a-z0-9-]{0,39}$`.
- Token aplikasi dikirim sebagai header `Authorization: Bearer <token>`. Server hanya menyimpan SHA-256 hex dari token.
- Pekerjaan dari token aplikasi **tidak pernah** membuat versi berstatus `ready`; penerbitan manual dari dashboard tidak
  berubah.
- Peta yang dilayani (`app.state.localizer`) tidak pernah diganti atau dimuat ulang oleh rute kandidat.

## Review Focus

1. Token aplikasi dikirim ke rute admin atau rute yang tidak terdaftar (`GET /api/jobs`, `DELETE /api/jobs/{id}`,
   `/api/me`, rute area) harus ditolak, bukan diterima sebagai pengguna; terutama saat `EUTOPOS_DEV_NO_AUTH=1`. Dikunci di
   Tugas 3.
2. Token yang dicabut atau salah tetap ditolak walau permintaan juga membawa JWT Access yang sah tanpa email (token
   layanan Cloudflare di tepi). Dikunci di Tugas 2.
3. Dua permintaan uji kandidat bersamaan untuk versi berbeda tidak boleh memuat dua kandidat sekaligus atau mengembalikan
   pose dari peta yang salah. Dikunci di Tugas 5.
4. Uji kandidat terhadap versi yang sedang dilayani memakai localizer yang dilayani, bukan memuat salinan kedua. Dikunci
   di Tugas 5.
5. Permintaan uji kandidat tercatat di log lokalisasi dengan `candidate = true`, sehingga tidak tercampur dengan lalu
   lintas pengguna. Dikunci di Tugas 5.

---

## File Structure

- Create `server/migrations/versions/0009_app_token.py`: tabel `app_token`, kolom `localize_request.candidate`.
- Modify `server/db.py`: model `AppToken`.
- Modify `server/localize_log.py`: kolom `candidate` di model `LocalizeRequest`.
- Create `server/app_tokens.py`: buat, cabut, cari token; identitas capture; router admin `/api/app-tokens`.
- Modify `server/uploads.py`: `POST /api/jobs`, `GET /api/jobs/{job_id}`, hook pre-create memakai identitas capture.
- Modify `server/worker.py:293-294`: pengecualian `ready` untuk identitas aplikasi.
- Create `server/candidate_map.py`: `CandidateCache`.
- Modify `server/app.py`: pecah `_localize` jadi pembacaan foto dan perhitungan pose; rute kandidat; sapu kandidat di
  `lifespan`; daftarkan router `app_tokens`.
- Create `web/app/tokens/page.tsx`; modify `web/lib/api.ts`, `web/lib/i18n/en.ts`, `web/lib/i18n/id.ts`, `web/app/nav.tsx`.
- Tests: `tests/test_app_tokens.py` (baru), `tests/test_uploads.py`, `tests/test_worker.py`, `tests/test_candidate_map.py`
  (baru), `tests/test_server.py`, `tests/test_db.py` (sudah memeriksa migrasi cocok dengan model; harus tetap lulus).

---

### Task 1: Tabel token aplikasi dan penanda kandidat di log

**Files:**
- Create: `server/migrations/versions/0009_app_token.py` (revision `"0009"`, down_revision `"0008"`)
- Modify: `server/db.py`, `server/localize_log.py`
- Test: `tests/test_db.py` (tes migrasi yang ada), `tests/test_localize_log.py`

**Interfaces:**
- Produces: `class AppToken(SQLModel, table=True)` di `server/db.py`, `__tablename__ = "app_token"`, kolom:
  `id: int | None` (PK), `name: str` (unik, index), `token_hash: str` (unik, index), `created_by: str`,
  `created_at: datetime` (timezone, default sekarang UTC), `last_used_at: datetime | None`, `revoked_at: datetime | None`.
- Produces: `LocalizeRequest.candidate: bool = False` (kolom `candidate`, `nullable=False`, `server_default` false).

- [ ] **Step 1: Tes gagal.** Di `tests/test_localize_log.py`: `test_record_keeps_candidate_flag` mencatat
  `record({... minimal entry yang ada di tes lain ..., "candidate": True})` lalu membaca baris dan
  `assert row.candidate is True`; dan baris tanpa kunci itu `assert row.candidate is False`.
- [ ] **Step 2:** `uv run pytest tests/test_localize_log.py tests/test_db.py -q`. Expected: tes baru FAIL (kolom tidak ada).
- [ ] **Step 3:** Tambah model dan migrasi 0009 (`op.create_table("app_token", ...)` dengan index unik `name` dan
  `token_hash`; `op.add_column("localize_request", sa.Column("candidate", sa.Boolean(), nullable=False,
  server_default=sa.false()))`; downgrade kebalikannya).
- [ ] **Step 4:** `uv run pytest tests/test_localize_log.py tests/test_db.py -q`. Expected: PASS, termasuk tes kecocokan
  migrasi dan model yang sudah ada.
- [ ] **Step 5:** Catat berkas di laporan (tanpa commit).

### Task 2: Modul token aplikasi dan router admin

**Files:**
- Create: `server/app_tokens.py`
- Modify: `server/app.py` (`app.include_router(app_tokens.router)`), `server/db.py`, `server/uploads.py`
- Test: `tests/test_app_tokens.py`

Impor melingkar: Tugas 3 membuat `uploads` mengimpor `app_tokens`, jadi `app_tokens` tidak boleh mengimpor `uploads`.
Pindahkan `_engine`, `get_session`, dan `DB` dari `server/uploads.py` ke `server/db.py`, lalu `uploads` mengimpornya
kembali (`from server.db import DB, get_session`) sehingga rujukan `uploads.DB`, `uploads.get_session`, dan
`dependency_overrides[uploads.get_session]` di modul dan tes lain tetap bekerja tanpa diubah.

**Interfaces:**
- Consumes: `AppToken` (Task 1), `auth.current_user`, `auth.is_admin`, `auth.email_from_token`, `auth.AuthError`,
  `auth.HEADER`, `db.DB`, `db.get_session`.
- Produces:
  - `PREFIX = "app:"`, `TOKEN_PREFIX = "eut_"`
  - `def hash_token(raw: str) -> str` (SHA-256 hex)
  - `def is_app_identity(identity: str) -> bool` (awalan `app:`)
  - `def create_token(s: Session, name: str, created_by: str) -> str`: mengembalikan token mentah
    `TOKEN_PREFIX + secrets.token_urlsafe(32)`; `ValueError` bila nama tidak sah atau sudah dipakai (termasuk yang dicabut).
  - `def revoke_token(s: Session, name: str) -> bool`: set `revoked_at`; `False` bila tidak ada.
  - `def identity_from_bearer(s: Session, authorization: str | None) -> str | None`: `None` bila header tidak ada atau
    bukan `Bearer`; `"app:<name>"` bila token aktif (dan memperbarui `last_used_at`); `auth.AuthError(401, ...)` bila token
    tidak dikenal; `auth.AuthError(403, ...)` bila dicabut.
  - `def capture_identity(s: Session, headers: Mapping[str, str]) -> str`: token aplikasi bila ada header `Authorization`
    (selalu divalidasi, juga saat `EUTOPOS_DEV_NO_AUTH=1`), selain itu `auth.email_from_token(headers.get(auth.HEADER))`.
    Pencarian header tidak peka huruf.
  - `def capture_user(request: Request, s: DB) -> str` dan `CaptureUser = Annotated[str, Depends(capture_user)]`;
    `AuthError` diubah jadi `HTTPException` dengan status yang sama.
  - Router: `GET /api/app-tokens` -> daftar `{name, created_by, created_at, last_used_at, revoked_at}` (tanpa hash);
    `POST /api/app-tokens` body `{name}` -> 201 `{name, token}`; `DELETE /api/app-tokens/{name}` -> 200
    `{name, revoked: true}` atau 404. Ketiganya `User` (email Access) dan 403 bila bukan admin.

- [ ] **Step 1: Tes gagal** di `tests/test_app_tokens.py` (pola fixture `client` seperti `tests/test_area_api.py`):
  - `test_create_returns_raw_token_once_and_stores_hash`: `POST` sebagai admin -> 201, `token` diawali `eut_`;
    `GET` tidak memuat `token` maupun `token_hash`; baris DB `token_hash == hash_token(token)`.
  - `test_non_admin_cannot_manage_tokens`: `POST`, `GET`, `DELETE` -> 403.
  - `test_duplicate_or_invalid_name_rejected`: nama sama dua kali -> 422; `"Bad Name"` -> 422.
  - `test_identity_from_bearer`: token aktif -> `"app:rekam-1"` dan `last_used_at` terisi; token acak -> `AuthError`
    401; token dicabut -> `AuthError` 403; header `"Basic x"` -> `None`.
  - `test_capture_identity_validates_bearer_even_in_dev_mode`: `EUTOPOS_DEV_NO_AUTH=1`, header `Authorization` berisi
    token acak -> 401, bukan `dev@local`.
  - `test_revoked_token_rejected_even_with_access_jwt`: header `Cf-Access-Jwt-Assertion` diisi dan
    `auth.email_from_token` di-monkeypatch mengembalikan email; token dicabut di `Authorization` -> 403.
- [ ] **Step 2:** `uv run pytest tests/test_app_tokens.py -q`. Expected: FAIL, modul tidak ada.
- [ ] **Step 3:** Implementasi sesuai Interfaces.
- [ ] **Step 4:** `uv run pytest tests/test_app_tokens.py -q`. Expected: PASS.
- [ ] **Step 5:** Catat berkas.

### Task 3: Rute capture menerima token aplikasi, rute lain tidak

**Files:**
- Modify: `server/uploads.py` (`create`, `get`, `_pre_create`)
- Test: `tests/test_uploads.py`

**Interfaces:**
- Consumes: `app_tokens.CaptureUser`, `app_tokens.capture_identity`, `app_tokens.is_app_identity`.
- Produces: `POST /api/jobs` memakai `CaptureUser` (pekerjaan `created_by = "app:<nama>"`); `GET /api/jobs/{job_id}`
  memakai `CaptureUser` dan, untuk identitas aplikasi, 404 bila `job.created_by` bukan identitas itu; `_pre_create`
  memakai `app_tokens.capture_identity(s, headers)` dengan header dari hook (nilai pertama tiap header) menggantikan
  `auth.email_from_token`. Rute lain tidak berubah.

- [ ] **Step 1: Tes gagal** di `tests/test_uploads.py`:
  - `test_app_token_creates_job_and_uploads`: buat token, `POST /api/jobs` dengan `Authorization` -> 201,
    `created_by == "app:rekam-1"`; hook pre-create dengan header `Authorization` yang sama -> diterima (alur seperti
    `test_full_upload_flow_queues_after_last_video`).
  - `test_app_token_cannot_read_other_jobs`: pekerjaan milik `a@x.id`, `GET /api/jobs/{id}` dengan token -> 404; milik
    sendiri -> 200.
  - `test_app_token_rejected_on_non_capture_routes`: dengan `CF_ACCESS_TEAM_DOMAIN` dan `CF_ACCESS_AUD` terisi dan tanpa
    JWT, hanya `Authorization` token aktif: `GET /api/jobs`, `DELETE /api/jobs/{id}`, `GET /api/me` -> 401.
  - `test_pre_create_rejects_app_token_for_email_job`: pekerjaan milik email, hook dengan token -> 403 (sama seperti
    `test_pre_create_rejects_other_user`).
- [ ] **Step 2:** `uv run pytest tests/test_uploads.py -q`. Expected: tes baru FAIL.
- [ ] **Step 3:** Implementasi sesuai Interfaces.
- [ ] **Step 4:** `uv run pytest tests/test_uploads.py tests/test_app_tokens.py -q`. Expected: PASS, tes lama tetap lulus.
- [ ] **Step 5:** Catat berkas.

### Task 4: Pekerjaan aplikasi tidak pernah `ready`

**Files:**
- Modify: `server/worker.py:293-294`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `app_tokens.is_app_identity(identity: str) -> bool`.
- Produces: versi dari pekerjaan aplikasi yang lolos gerbang tetap `candidate`; `job.summary["gate"]["decision"]` tetap
  `"publish"` (aplikasi membacanya sebagai "Siap diuji").

- [ ] **Step 1: Tes gagal** `test_gate_pass_from_app_stays_candidate`: seperti `test_gate_pass_marks_version_ready` tetapi
  pekerjaan dibuat dengan `created_by="app:rekam-1"` (tambah parameter `created_by` ke `run_gate_job` dan `queued`,
  bawaan nilai lama); `assert job.status == "done"`, status versi `"candidate"`,
  `job.summary["gate"]["decision"] == "publish"`.
- [ ] **Step 2:** `uv run pytest tests/test_worker.py -q -k gate`. Expected: tes baru FAIL (status `ready`).
- [ ] **Step 3:** Syarat `verdict.decision == "publish" and not app_tokens.is_app_identity(job.created_by)`.
- [ ] **Step 4:** `uv run pytest tests/test_worker.py -q`. Expected: PASS.
- [ ] **Step 5:** Catat berkas.

### Task 5: Lokalisasi terhadap versi kandidat

**Files:**
- Create: `server/candidate_map.py`
- Modify: `server/app.py`
- Test: `tests/test_candidate_map.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `active_map.load_localizer(map_dir: Path, align_source=None) -> Localizer`, `DbAlign(engine, version_id).get`,
  `app_tokens.CaptureUser`, `localize_log.record`.
- Produces di `server/candidate_map.py`:
  - `CANDIDATE_IDLE_S = 600`, `SWEEP_S = 60`, `TESTABLE = {"candidate", "ready", "published", "retired"}`
  - `class CandidateUnavailable(Exception)` dengan `status: int` (404 versi tidak ada; 409 status di luar `TESTABLE` atau
    folder peta tidak ada).
  - `class CandidateCache` dengan `__init__(self, engine, loader=active_map.load_localizer, idle_s=CANDIDATE_IDLE_S,
    clock=time.monotonic)`, `get(self, version_id: int) -> tuple[Localizer, str, int]` (localizer, `area_id`,
    `version`), `sweep(self) -> bool` (membuang kandidat yang menganggur lebih dari `idle_s`, `True` bila membuang).
    Satu kandidat sekaligus: versi lain menggantikan yang lama; satu kunci di dalam kelas sehingga dua `get` bersamaan
    tidak memuat dua kali dan tidak memuat dua versi sekaligus.
- Produces di `server/app.py`:
  - `_localize` dipecah: `_read_photo(image, fx, fy, cx, cy, entry) -> tuple[np.ndarray, bytes, list[bool]]` dan
    `_pose_response(loc, rgb, data, fx, fy, cx, cy, given, area_id, map_version, lock) -> LocalizeResponse`. Perilaku
    `/localize` tidak berubah.
  - `POST /versions/{version_id}/localize` dengan parameter form sama dengan `/localize` dan `user: CaptureUser`. Bila
    `version_id` adalah versi yang sedang dilayani (`area_id` dan `map_version` sama dengan `app.state`), pakai
    `app.state.localizer`; selain itu `app.state.candidates.get(version_id)`. `CandidateUnavailable` -> HTTPException
    dengan `status`-nya. Lokalisasi memakai `app.state.lock` yang sama dengan `/localize`. Entri log memuat
    `candidate=True`, `area_id`, dan `map_version` versi kandidat.
  - `lifespan`: bila `DATABASE_URL` ada, `st.candidates = CandidateCache(engine)` dan satu thread daemon memanggil
    `st.candidates.sweep()` tiap `SWEEP_S` detik, berhenti bersama `stop` yang ada (buat `stop` walau auto-publish mati).
    Tanpa database, rute kandidat menjawab 503.

- [ ] **Step 1: Tes gagal** di `tests/test_candidate_map.py` (loader palsu menghitung panggilan, `clock` palsu):
  - `test_loads_once_and_reuses`: dua `get(1)` -> loader dipanggil sekali.
  - `test_other_version_replaces_previous`: `get(1)` lalu `get(2)` -> loader dua kali; `get(1)` lagi -> tiga kali.
  - `test_sweep_drops_idle_candidate`: `get(1)`, maju `idle_s + 1` detik, `sweep()` -> `True`; `get(1)` memuat ulang.
  - `test_unavailable_versions`: id tidak ada -> `CandidateUnavailable` 404; status `rejected` -> 409; folder tidak ada ->
    409.
  - `test_concurrent_gets_do_not_load_two_versions`: dua thread `get(1)` dan `get(2)` dengan loader lambat yang mencatat
    jumlah pemuatan berjalan bersamaan; `assert max_concurrent == 1`.
- [ ] **Step 2:** Tes gagal di `tests/test_server.py` (pola localizer palsu yang ada):
  - `test_candidate_localize_does_not_touch_served_map`: respons kandidat memuat `area_id` dan `map_version` versi
    kandidat; `app.state.localizer` dan `/health` tetap versi lama.
  - `test_candidate_localize_uses_served_localizer_for_served_version`: loader kandidat tidak dipanggil.
  - `test_candidate_localize_logs_candidate_flag`: baris log terakhir `candidate is True`; permintaan `/localize` biasa
    `candidate is False`.
  - `test_candidate_localize_requires_identity`: tanpa JWT dan tanpa token, dengan Access dikonfigurasi -> 401.
- [ ] **Step 3:** `uv run pytest tests/test_candidate_map.py tests/test_server.py -q`. Expected: tes baru FAIL.
- [ ] **Step 4:** Implementasi sesuai Interfaces.
- [ ] **Step 5:** `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`. Expected: semua lulus, ruff
  bersih. Catat jumlah lulus dibanding garis dasar sebelum Tugas 1.
- [ ] **Step 6:** Catat berkas.

### Task 6: Halaman token di dashboard

**Files:**
- Create: `web/app/tokens/page.tsx`
- Modify: `web/lib/api.ts`, `web/lib/i18n/en.ts`, `web/lib/i18n/id.ts`, `web/app/nav.tsx`

**Interfaces:**
- Consumes: `GET/POST/DELETE /api/app-tokens` (Task 2), `api.me()` untuk `is_admin`.
- Produces: `api.appTokens()`, `api.createAppToken(name: string)`, `api.revokeAppToken(name: string)` di `web/lib/api.ts`
  mengikuti pola `call<T>` yang ada; halaman `/tokens` hanya tampil di navigasi bila `is_admin`.

Perilaku halaman: tabel nama, dibuat oleh, dibuat, terakhir dipakai, status (aktif atau dicabut); formulir nama baru;
setelah dibuat, token mentah tampil sekali dengan tombol salin dan teks bahwa token tidak akan tampil lagi; tombol cabut
dengan konfirmasi. Komponen dan gaya mengikuti halaman yang ada (`components/ui`, `PageHead`), teks lewat i18n en dan id.

- [ ] **Step 1:** Tambah fungsi API dan kunci i18n, lalu halaman.
- [ ] **Step 2:** `cd web && npx tsc --noEmit` dan `npm run build`. Expected: lulus tanpa galat.
- [ ] **Step 3:** Jalankan api lokal dengan `EUTOPOS_DEV_NO_AUTH=1` dan dashboard; buat token, lihat token tampil sekali,
  muat ulang halaman (token tidak tampil lagi), cabut. Lampirkan tangkapan layar di laporan.
- [ ] **Step 4:** Catat berkas.

### Task 7: Verifikasi di PC lab (manual, Bagus memutuskan)

Bukan untuk agen pelaksana. Dijalankan Claude setelah Bagus mengizinkan, setelah merge dan deploy otomatis.

- [ ] Ukur memori GPU dengan peta yang dilayani ditambah satu kandidat dimuat (`nvidia-smi` sebelum dan sesudah satu uji
  kandidat). Bila tidak cukup, catat dan putuskan bersama Bagus (kandidat di CPU).
- [ ] Buktikan aplikasi bisa melewati Cloudflare Access ke `POST /api/jobs`, unggahan tus, dan rute kandidat dengan token
  layanan yang sudah dipakai `VpsClient` ditambah `Authorization: Bearer`. Bila Access menolak, tanyakan Bagus sebelum
  mengubah kebijakan Access.
- [ ] Uji kandidat pada versi p1-p2 yang ada dan satu versi lain; `/health` tidak berubah.
