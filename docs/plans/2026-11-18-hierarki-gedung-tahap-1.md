# Hierarki gedung, tahap 1: rencana implementasi

> **STATUS (19 Nov 2026): Task 1 sampai 5 SUDAH dikerjakan di PR `feat/building-hierarchy`; Task 6 (gladi migrasi) sudah dijalankan pada salinan dump produksi dan lulus. Jangan dieksekusi ulang.** Yang tersisa hanya Step 3 dan 4 Task 6: merge oleh Bagus, lalu pemeriksaan pasca-deploy. Rencana ini disimpan sebagai acuan keputusan dan pola untuk tahap berikutnya (anggota dan peran, kunci akses per organisasi, kuota, RLS, gedung bersarang), yang butuh rencana baru. Dua perbedaan dari rencana: slug gedung dan batas nama dikunci (`^[a-z0-9][a-z0-9-]{0,39}$`, nama maks 100), dan `create_building` memakai dependency untuk cek 415/admin.

> **Untuk agen pelaksana:** WAJIB memakai superpowers:subagent-driven-development atau superpowers:executing-plans, tugas demi tugas. Langkah memakai kotak centang (`- [ ]`).

**Tujuan:** setiap denah (Area) punya parent gedung (Building) di bawah satu organisasi, dashboard mengelompokkan peta per gedung, dan versi peta membedakan "terbit" dari "siap navigasi".

**Arsitektur:** dua tabel baru (`organization`, `building`) dan satu kolom wajib `area.building_id`. Pemilik sebuah area diturunkan lewat gedungnya, tanpa salinan `org_id`. Status "siap navigasi" diturunkan dari data yang sudah ada (versi terbit, alignment, graf rute), tidak disimpan. `area.id` tetap pengenal area, jadi aplikasi HP, jalur `/maps/<area>/job-N`, dan `/localize` tidak berubah.

**Tech stack:** FastAPI, SQLModel, Alembic, PostgreSQL (tes: SQLite), Next.js 16 static export.

**Dasar keputusan:** percakapan Bagus dan Claude 18 Nov 2026 (arahan Pak Dhoto: tiap denah punya parent gedung). Ringkasannya ada di bagian "Keputusan" di bawah, karena belum ada dokumen spesifikasi tersendiri. Desain multi-organisasi yang lebih luas ada di `docs/specs/2026-11-05-capture-publish-otomatis-multi-org-design.md` (belum di-commit, hanya di checkout utama); tahap 1 ini tidak mengerjakan isinya selain lapisan organisasi minimal.

## Keputusan

1. Hierarki: Organization > Building > Area > MapVersion. "Projek" sama dengan organisasi, bukan tingkat sendiri (Bagus, 18 Nov).
2. Data lama: semua area (`floor10`, `lab10`, `hcm-lantai-10`, dan lainnya di database) masuk gedung **HCM** milik satu organisasi bawaan (Bagus, 18 Nov).
3. `org_id` hanya di `building`. Area, versi, job, ruangan menurunkan pemiliknya lewat gedung.
4. Status versi dua tingkat (Bagus menyetujui pilihan pertama, 18 Nov): **terbit** (boleh dipakai `/localize`) dan **siap navigasi** (terbit, punya alignment, dan punya graf rute). Siap navigasi adalah nilai turunan, bukan kolom.
5. Ditunda, tidak dikerjakan di tahap ini: anggota dan peran, kunci akses, kuota, isolasi lintas organisasi, gedung bersarang, lokalisasi multi-denah, hapus dan ganti nama gedung, perubahan aplikasi HP.
6. **Koreksi dari usulan sebelumnya (perlu persetujuan Bagus):** `area.id` TIDAK diganti menjadi kunci angka. Lihat "Catatan untuk Bagus" di akhir.

## Global Constraints

- `area.id` tetap kunci utama area dan tidak berubah nilainya. Tidak ada rename area.
- Tidak ada dependensi baru (Python maupun npm).
- Semua teks antarmuka baru punya kunci di `web/lib/i18n/en.ts` dan `web/lib/i18n/id.ts`. Tanpa em dash di teks antarmuka.
- Konstanta data bawaan: organisasi `slug="default"`, `name="Organisasi bawaan"`; gedung `slug="hcm"`, `name="HCM"`.
- Pola slug gedung sama dengan pola area di `server/uploads.py`: `^[a-z0-9][a-z0-9-]{0,39}$`.
- Endpoint tulis memakai pemeriksaan `Content-Type: application/json` seperti `publish_version` di `server/maps_api.py` (penangkal CSRF), dan hanya admin (`auth.is_admin`).
- Commit hanya setelah Bagus memberi izin untuk eksekusi rencana ini. Pesan commit tanpa atribusi AI apa pun.

## Review Focus

1. Unggahan ke area yang sudah ada dengan `building_id` berbeda: harus ditolak 422, bukan diam-diam memindahkan area (tes di Task 2).
2. Klien web lama (cache) mengirim `POST /api/jobs` tanpa `building_id` untuk area yang sudah ada: tetap berhasil; untuk area baru: 422 dengan pesan jelas (tes di Task 3).
3. Migrasi di PostgreSQL produksi, bukan hanya SQLite: kolom NOT NULL setelah isi ulang. Dijalankan pada salinan dump produksi sebelum merge (Task 6).
4. Versi terbit yang alignment-nya ada di DB (tabel `alignment`) dan yang ada di berkas `kp*-r*/align.json`: keduanya harus terbaca siap navigasi (tes di Task 3).
5. Gedung dengan slug sama di organisasi yang sama: 409; di organisasi berbeda: diizinkan oleh skema (tes di Task 1).

---

### Task 1: Model dan migrasi 0008

**Files:**
- Modify: `server/db.py` (kelas baru di atas `Area`, kolom baru di `Area`)
- Create: `server/migrations/versions/0008_building.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `Organization(id: int | None, slug: str, name: str)`, tabel `organization`, `slug` unik.
- Produces: `Building(id: int | None, org_id: int, slug: str, name: str)`, tabel `building`, `UniqueConstraint("org_id", "slug")`, FK `organization.id`.
- Produces: `Area.building_id: int` (FK `building.id`, `nullable=False`, index).
- Produces: konstanta `DEFAULT_ORG_SLUG = "default"`, `DEFAULT_BUILDING_SLUG = "hcm"` di `server/db.py`.

- [ ] **Step 1: Tulis tes yang gagal** di `tests/test_db.py`:
  - `test_migration_0008_puts_existing_areas_in_hcm`: upgrade ke `0007`, sisipkan area `floor10` dan `hcm-lantai-10` lewat SQL mentah, upgrade ke `head`. Assert: satu baris `organization` slug `default`; satu baris `building` slug `hcm`, `org_id` sama dengan organisasi itu; kedua area `building_id` sama dengan id gedung HCM.
  - `test_migration_0008_up_down_up`: pola sama dengan `test_migration_0006_up_down_up` di `tests/test_calibration_db.py`. Setelah downgrade ke `0007`, tabel `organization` dan `building` hilang dan kolom `area.building_id` hilang; upgrade lagi berhasil.
  - `test_area_without_building_is_rejected`: menyimpan `Area(id="x", name="X")` tanpa `building_id` memunculkan `IntegrityError`.
  - `test_building_slug_unique_per_org`: dua `Building` slug `hcm` di org yang sama memunculkan `IntegrityError`; slug `hcm` di org lain berhasil.
  - Tes `test_migration_matches_models` yang sudah ada harus tetap lulus.
- [ ] **Step 2: Jalankan dan pastikan gagal.** Run: `uv run --no-sync pytest tests/test_db.py -q`. Expected: tes baru FAIL (revisi `0008` atau kelas `Building` tidak ada).
- [ ] **Step 3: Implementasi** kelas di `server/db.py` dan migrasi `0008` (`down_revision = "0007"`). Urutan upgrade: buat `organization`, buat `building`, sisipkan organisasi bawaan dan gedung HCM, tambah `area.building_id` nullable, isi semua baris dengan id gedung HCM, lalu jadikan NOT NULL dengan FK dan index. Pakai `op.batch_alter_table("area")` supaya jalan di SQLite dan PostgreSQL. Downgrade membalik urutannya.
- [ ] **Step 4: Jalankan tes.** Run: `uv run --no-sync pytest tests/test_db.py tests/test_calibration_db.py -q`. Expected: semua PASS.
- [ ] **Step 5: Seluruh suite.** Run: `uv run --no-sync pytest -q`. Expected: tidak ada kegagalan baru. Fixture lain yang membuat `Area(...)` langsung akan gagal karena `building_id` wajib; perbaiki fixture itu dengan membuat organisasi dan gedung lebih dulu lewat satu helper tes `make_building(session) -> Building` di `tests/conftest.py` (buat berkasnya bila belum ada).
- [ ] **Step 6: Commit** (izin Bagus): `feat(db): organization and building as parents of every area`.

### Task 2: Satu pintu pembuatan area

**Files:**
- Modify: `server/db.py` (`register`), `server/jobs.py` (`create_job`)
- Test: `tests/test_db.py`, `tests/test_jobs.py`

**Interfaces:**
- Consumes: `Building`, `Area.building_id` dari Task 1.
- Produces: `ensure_area(session: Session, area_id: str, name: str, building_id: int | None) -> Area` di `server/db.py`.
  - Area sudah ada dan `building_id` None atau sama: kembalikan area apa adanya (nama tidak diubah).
  - Area sudah ada dan `building_id` berbeda: `ValueError("area <id> belongs to another building")`.
  - Area baru dan `building_id` None: `ValueError("building_id is required for a new area")`.
  - Area baru dan gedung tidak ada: `ValueError("building <id> not found")`.
- Produces: `register(session, area_id, name, path, building_id: int | None = None)` dan `create_job(..., building_id: int | None = None)`; keduanya memanggil `ensure_area`, tidak lagi `session.add(Area(...))` sendiri.

- [ ] **Step 1: Tulis tes yang gagal:** `test_ensure_area_returns_existing`, `test_ensure_area_rejects_other_building`, `test_ensure_area_new_requires_building`, `test_ensure_area_unknown_building`, `test_create_job_new_area_in_building` (area baru dibuat dengan `building_id` yang diberikan). Pesan galat di assert persis seperti di blok Interfaces.
- [ ] **Step 2: Jalankan dan pastikan gagal.** Run: `uv run --no-sync pytest tests/test_db.py tests/test_jobs.py -q`. Expected: FAIL (`ensure_area` tidak ada).
- [ ] **Step 3: Implementasi** `ensure_area` dan ganti dua tempat pembuatan area. `grep -n "Area(id=" server` setelahnya hanya boleh menemukan `ensure_area`.
- [ ] **Step 4: Jalankan tes dan seluruh suite.** Run: `uv run --no-sync pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** (izin Bagus): `refactor(db): create areas through one function that requires a building`.

### Task 3: API gedung, unggahan, dan status siap navigasi

**Files:**
- Create: `server/buildings_api.py`
- Modify: `server/app.py` (daftarkan router), `server/uploads.py` (`JobIn`, `create`), `server/maps_api.py` (`VersionOut`, `_out`), `server/navgraph.py` (helper graf)
- Test: `tests/test_buildings_api.py` (baru), `tests/test_maps_api.py`, `tests/test_uploads.py`

**Interfaces:**
- Consumes: `ensure_area` (Task 2), `Building`, `Organization` (Task 1).
- Produces: `GET /api/buildings` -> `list[BuildingOut]`, `BuildingOut(id: int, slug: str, name: str, area_ids: list[str])`, urut nama.
- Produces: `POST /api/buildings` (admin, JSON) body `{slug, name}` -> 201 `BuildingOut`; gedung masuk organisasi bawaan; slug kembar di organisasi yang sama -> 409 `{"code": "building_exists"}`; bukan admin -> 403; bukan JSON -> 415.
- Produces: `JobIn.building_id: int | None = None`; `ValueError` dari `ensure_area` -> 422 dengan pesan apa adanya.
- Produces: `graph_exists(session: Session, area_id: str) -> bool` di `server/navgraph.py`, memakai sumber yang sama dengan `get_navgraph`: baris `published_graph` untuk area itu, lalu berkas `graph_path(maps_root(), area_id)`. Helper ini memakai `session` yang diberikan, bukan membuka engine sendiri seperti `_published`.
- Produces: `VersionOut.building_id: int`, `VersionOut.building_name: str`, `VersionOut.navigation_ready: bool`, dengan `navigation_ready = v.status == "published" and _align(s, v) is not None and graph_exists(s, v.area_id)`.

- [ ] **Step 1: Tulis tes yang gagal:**
  - `tests/test_buildings_api.py`: daftar berisi HCM dengan `area_ids` area-areanya; admin membuat gedung `pens` -> 201; kedua kalinya -> 409 `building_exists`; non-admin -> 403; tanpa JSON -> 415; slug `PENS!` -> 422.
  - Unggahan: area baru dengan `building_id` -> 201; area baru tanpa `building_id` -> 422; area lama tanpa `building_id` -> 201 (Review Focus 2); area lama dengan gedung lain -> 422 (Review Focus 1).
  - `tests/test_maps_api.py`: versi kandidat -> `navigation_ready` false; terbit tanpa alignment (kasus `floor10`) -> false; terbit dengan `align.json` di folder run dan graf -> true; terbit dengan alignment di DB dan graf -> true (Review Focus 4); terbit dan selaras tanpa graf -> false. `building_name` = `"HCM"`.
- [ ] **Step 2: Jalankan dan pastikan gagal.** Run: `uv run --no-sync pytest tests/test_buildings_api.py tests/test_maps_api.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementasi** sesuai blok Interfaces. Hindari N+1 pada `GET /api/versions`: ambil peta `area_id -> (building_id, building_name)` sekali per permintaan.
- [ ] **Step 4: Jalankan tes, seluruh suite, dan lint.** Run: `uv run --no-sync pytest -q`, lalu `uv run --no-sync ruff check . && uv run --no-sync ruff format --check .`. Expected: PASS dan bersih.
- [ ] **Step 5: Commit** (izin Bagus): `feat(api): buildings, building on new uploads, navigation-ready versions`.

### Task 4: CLI

**Files:**
- Modify: `server/manage.py`
- Test: tes CLI yang sudah ada untuk `manage` (cari `server.manage` di `tests/`), atau `tests/test_manage_building.py` bila belum ada

**Interfaces:**
- Consumes: `ensure_area` (Task 2), `Building` (Task 1).
- Produces: subperintah `building list` (cetak `slug  name  jumlah-area`) dan `building add <slug> <name>` (organisasi bawaan).
- Produces: opsi `--building <slug>` (bawaan `hcm`) pada `register` dan `job`; slug tidak dikenal -> keluar dengan kode bukan nol dan pesan `building <slug> not found`.

- [ ] **Step 1: Tulis tes yang gagal** untuk `building add`, `building list`, dan `register --building pens` membuat area baru di gedung `pens`.
- [ ] **Step 2: Jalankan dan pastikan gagal.**
- [ ] **Step 3: Implementasi.**
- [ ] **Step 4: Jalankan seluruh suite.** Expected: PASS.
- [ ] **Step 5: Commit** (izin Bagus): `feat(cli): manage buildings and choose one when registering`.

### Task 5: Dashboard

**Files:**
- Modify: `web/lib/api.ts`, `web/app/maps/page.tsx`, `web/app/new/page.tsx`, `web/lib/i18n/en.ts`, `web/lib/i18n/id.ts`
- Create: `web/lib/buildings.ts` + `web/lib/buildings.test.ts` (logika murni, pola `formatNumber.test.ts`)

**Interfaces:**
- Consumes: `GET/POST /api/buildings`, `VersionOut.building_id/building_name/navigation_ready`, `JobIn.building_id` (Task 3).
- Produces: tipe `Building { id: number; slug: string; name: string; area_ids: string[] }`, `api.buildings()`, `api.createBuilding({slug, name})`.
- Produces: `buildingOfArea(buildings: Building[], areaId: string): Building | undefined` di `web/lib/buildings.ts`.

- [ ] **Step 1: Tulis tes yang gagal** `web/lib/buildings.test.ts`: area yang ada di `area_ids` gedung mengembalikan gedung itu; area tak dikenal -> `undefined`.
- [ ] **Step 2: Jalankan dan pastikan gagal.** Run (dari `web/`): `node --test lib/buildings.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implementasi:**
  - Halaman peta: penyaring gedung di samping penyaring area yang sudah ada; kolom area menampilkan `Gedung / area`; lencana status versi terbit: "Siap navigasi" bila `navigation_ready`, selain itu "Terbit, belum siap navigasi". Panel Properties menampilkan nama gedung.
  - Halaman unggah baru: pilihan gedung wajib, bawaan gedung pertama; dikirim sebagai `building_id`. Admin melihat tombol "Tambah gedung" (form slug dan nama) yang memanggil `api.createBuilding`.
  - Kunci i18n baru di kedua bahasa.
- [ ] **Step 4: Verifikasi.** Run: `node --test lib/*.test.ts` lalu `npm run build`. Expected: semua lulus. Lalu buka dashboard lokal dengan data contoh: penyaring gedung bekerja, lencana status tampil benar untuk `hcm-lantai-10` (siap navigasi bila graf ada) dan `floor10` (belum siap navigasi).
- [ ] **Step 5: Commit** (izin Bagus): `feat(web): group maps by building and show navigation readiness`.

### Task 6: Gladi migrasi produksi dan rilis

**Files:** tidak ada perubahan kode.

- [ ] **Step 1:** Di PC lab, `pg_dump` database produksi ke berkas cadangan (simpan di luar repo, izin 600).
- [ ] **Step 2:** Pulihkan dump ke kontainer PostgreSQL sementara, jalankan `alembic upgrade head` dengan kode cabang ini. Expected: berhasil; semua area punya `building_id` HCM; `alembic downgrade 0007` lalu `upgrade head` berhasil.
- [ ] **Step 3:** Bagus memutuskan merge. Merge memicu auto-deploy (lihat `deploy/autodeploy.sh`); pastikan tidak ada latihan atau pengukuran yang sedang berjalan.
- [ ] **Step 4:** Setelah deploy: `/health` ok, `GET /api/buildings` menampilkan HCM dengan semua area, dashboard menampilkan lencana yang benar.

## Catatan untuk Bagus: koreksi atas usulan sebelumnya

Usul saya sebelumnya mengganti kunci utama area menjadi angka. Setelah membaca kode, `area_id` dipakai di sekitar 250 tempat: semua tabel peta, jalur penyimpanan `/maps/<area>/job-N`, URL dashboard, permintaan `/localize`, dan aplikasi HP. Menggantinya di tahap 1 berarti rombak besar yang menyentuh produksi dan aplikasi, padahal manfaatnya (slug area boleh sama di dua organisasi) baru dibutuhkan ketika ada organisasi kedua.

Yang sebenarnya dituntut praktik terbaik adalah pengenal yang **stabil dan tidak pernah dipakai ulang**, bukan harus angka. `area.id` sudah memenuhi itu selama tidak pernah di-rename (dijaga di Global Constraints). Saat organisasi kedua datang, area baru cukup diberi id yang unik global (mis. berawalan slug gedung), tanpa migrasi data lama.

Biayanya bila keputusan ini keliru: kalau kelak memang perlu slug area kembar antar organisasi tanpa awalan, migrasi kunci tetap harus dilakukan, dan saat itu lebih mahal karena data lebih banyak. Bila Bagus tetap ingin kunci angka sekarang, rencana ini perlu Task tambahan sebelum Task 1 dan perubahan di aplikasi HP.
