# Area walkable, panah AR, dan penanda POI: Rencana Implementasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Staf mengecat area yang boleh dilewati di dashboard dengan kuas; rute dihitung langsung di atas area itu dan digambar di aplikasi sebagai panah chevron di lantai, dengan pin POI melayang di tujuan.

**Architecture:** Modul Python murni `server/walkable.py` menyusun grid (jalur scan + goresan kuas, dierosi) dan merencanakan rute (A* bilangan bulat + peluruskan). Server menerbitkan grid siap pakai di `/navgraph` (bersama `graph` lama selama masa transisi). Aplikasi punya port C# `WalkableGrid` yang diuji dengan kasus uji bersama yang sama, lalu `RouteView` dan `PoiPin` baru menggambar hasilnya.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Alembic, numpy, pytest; Next.js 16 static export, React 19, TypeScript 5.9, Tailwind v4; Unity 6000.3 EditMode, C# (Eutopos.Core, tanpa dependensi Unity).

**Spec:** `docs/specs/2026-10-21-area-walkable-panah-poi-design.md` (repo `eutopos-vps`; belum di-commit, ikut commit pertama cabang `feat/area-walkable`).

## Global Constraints

- Kerangka G, 2D (x, y). Skala belum dikalibrasi: UI menulis "Scale not calibrated" di samping angka jarak. Semua angka dalam satuan G.
- Grid: `cell_m` 0,10; indeks `i = row * width + col`, `col = floor((x - ox) / cell_m)`, `row = floor((y - oy) / cell_m)`; baris naik searah y. Luas = kotak pembatas peta 2D (`/plan` meta) + margin 3; di atas 400.000 sel `cell_m` jadi 0,20; di atas 1.000.000 sel ditolak (409). `bits`: base64 dari sel row-major, bit `k` byte `b` = sel `8b + k`, LSB dulu, sisa bit nol.
- Seed: sel yang pusatnya ≤ 0,5 dari ruas jalur scan. Radius agen (erosi): 0,2. Goresan: radius API 0,1 sampai 3, UI 0,3 sampai 1,5; titik 1 sampai 2000; angka harus hingga (`allow_inf_nan=False`).
- Perencana: A* delapan arah, biaya lurus 10 dan diagonal 14 (bilangan bulat), diagonal hanya bila kedua sel orthogonal walkable, heuristik oktil `10 * max(dx, dy) + 4 * min(dx, dy)`, prioritas `f`, lalu `h`, lalu indeks terkecil, tetangga berurutan `(dx, dy)` = (-1,-1), (0,-1), (1,-1), (-1,0), (1,0), (-1,1), (0,1), (1,1) dengan baris = y, parent hanya diganti bila biaya **lebih kecil** (`<`). Titik awal dan tujuan diikat ke sel sendiri bila walkable, selain itu ke sel walkable terdekat (kuadrat jarak ke pusat sel, seri: indeks terkecil).
- Panah: jarak 0,9; panjang 0,5; lebar 0,55; tinggi 0,03; hanya 8 satuan di depan pengguna (min 0,5), alfa memudar di 2 satuan terakhir; fase naik 0,6 per detik; kolam 12 objek. Pin: tinggi 1,5, warna #E07A2E, hanya target terpilih, hanya saat `HasAlignment` dan tidak `needsRelocalize`.
- `/navgraph` menambah `walkable` dan `revision` dan **tidak mengubah `graph`** (APK lama tetap jalan). `graph` dipensiunkan di pekerjaan terpisah, setelah APK baru terverifikasi.
- Menulis dan menerbitkan hanya admin (`auth.is_admin`) dengan `Content-Type: application/json`; selain itu 403 atau 415. Tanpa dependensi baru (tanpa shapely, tanpa three.js di rencana ini), tanpa aset 3D.
- Data lapangan (koordinat gedung, foto, log HP, awan titik) tidak pernah masuk repo atau fixture; tes memakai data sintetis. Log HP hanya di scratchpad.
- Teks UI dashboard berbahasa Inggris; teks lain tanpa em dash. Aplikasi mengikuti gaya yang ada (komentar Indonesia, pesan UI Indonesia).
- Tes server: `python -m pytest -q` dengan `.venv` utama (`D:/Dev/Projects/eutopos-vps/.venv/Scripts`) di PATH, lalu `ruff check` dan `ruff format --check`. Web: `npx next build --webpack` di `web/` memakai junction sementara `node_modules` (`cmd //c 'mklink /J ...'`, hapus dengan `cmd //c 'rmdir ...'`, jangan `rm -r`). Unity: `Start-Process -Wait` dengan `-batchmode -runTests -testPlatform EditMode -testResults ... -logFile ...`.
- Commit dan push hanya atas perintah Bagus; langkah Commit = titik commit yang diusulkan. Tanpa atribusi AI. Jangan merge saat uji lapangan, unggahan, atau pembangunan peta berjalan. Perintah yang menulis di PC Lab, build APK, dan merge butuh izin Bagus pada saat itu.

## Review Focus

1. Erosi atau penghapusan membuat area kosong atau terpecah: Publish ditolak (409) bila tidak ada sel walkable, dan ruangan yang terputus dari komponen terbesar diperingatkan. Dipatok di Task 1 dan Task 3.
2. Pengguna berdiri di luar area atau di dalam tembok yang dihapus (bahkan di luar grid): rute tetap berangkat dari posisinya lewat sel jangkar, tanpa crash. Dipatok di Task 2 (kasus `snap` dan `outside`).
3. Goresan jahat atau rusak (NaN, radius ekstrem, 2001 titik, non-admin, bukan JSON): ditolak, tidak ada yang tersimpan. Dipatok di Task 3.
4. Dua staf menyunting: goresan urut `id`, Undo menghapus goresan dengan `id` terbesar; Reset meminta konfirmasi di halaman. Dipatok di Task 3 dan Task 4.
5. Python dan C# melenceng (urutan bit, urutan baris, tie-break): kasus uji bersama memuat kasus bit dan kasus rute, dijalankan di kedua sisi. Dipatok di Task 2 dan Task 5.

---

## Ruling yang dibawa rencana ini (menyimpang dari teks spesifikasi)

- Spesifikasi 5A langkah 1 menolak lewat `components` bila awal dan tujuan beda komponen. Perencana cukup menjalankan A*: bila daftar terbuka habis, hasilnya `None`. Hasilnya identik; `components` hanya dipakai untuk peringatan Publish. Tidak perlu diport ke C#.
- Spesifikasi 5A langkah 4 ("pusat sel hasil peluruskan tanpa duplikat") dipertajam: pusat sel pertama dibuang bila titik awal berada di sel walkable, pusat sel terakhir dibuang bila tujuan berada di sel walkable (kalau tidak, rute berbelok ke pusat sel yang tidak perlu). Spesifikasi diperbarui di Task 2.
- Spesifikasi 5C mengukur huruf label dengan tebal garis rute; tebal garis itu dalam meter dan hasilnya terlalu besar. Label diukur terhadap lebar peta (1,8%) dengan halo putih. Spesifikasi diperbarui di Task 4.
- Spesifikasi 5B menulis `strokes: [...]` di `GET /walkable`. Yang dikirim hanya `{id, mode, radius, points_count}` (dashboard hanya butuh jumlah dan id untuk Undo).
- `NavGraph.cs`, `NavGraphTests.cs`, `RouteCasesTests.cs`, dan `route_cases.json` dihapus dari aplikasi di Task 5 (tidak ada lagi yang memakainya). `tests/fixtures/route_cases.json` dan perencana graf di server tetap sampai `graph` dipensiunkan. `Route` pindah ke berkas sendiri tanpa `NodeIds`.
- Titik acuan panel uji ground truth (`CyclePoint`, `MarkGroundTruth`) memakai daftar target (ruangan), bukan simpul graf. Biaya: acuan lebih sedikit, tetapi bernama dan bisa diukur dengan meteran.
- Kunci heap C# `(f << 42) | (h << 22) | idx` dalam `long`, dengan syarat `idx < 2^22`, `h < 2^20`, `f < 2^21`; batas 1.000.000 sel menjamin syarat itu.

## Persiapan (sekali, sebelum Task 1)

- [ ] **Step 1: Worktree server.** `git -C D:/Dev/Projects/eutopos-vps fetch origin && git -C D:/Dev/Projects/eutopos-vps worktree add D:/wt/area-walkable -b feat/area-walkable origin/main`, lalu salin `docs/specs/2026-10-21-area-walkable-panah-poi-design.md` dan berkas rencana ini dari checkout utama ke worktree (keduanya belum di-commit). Catat BASE = `git rev-parse HEAD`.
- [ ] **Step 2: Workspace ledger.** Jalankan `sdd-workspace` untuk berkas rencana ini dan buat ledger dengan baris pertama sesuai format skill executing-plans (menyebut `docs/plans/2026-10-21-area-walkable-panah-poi.md`).

---

### Task 1: Grid walkable (seed, goresan, erosi, jangkar, bits)

**Files:**
- Create: `server/walkable.py`
- Test: `tests/test_walkable.py`

**Interfaces:**
- Produces (semua di `server/walkable.py`):
  - konstanta `CELL_M = 0.10`, `MARGIN_M = 3.0`, `SEED_RADIUS_M = 0.5`, `AGENT_RADIUS_M = 0.2`, `SOFT_CELLS = 400_000`, `MAX_CELLS = 1_000_000`, `ROOM_FAR_M = 1.5`
  - `@dataclass(frozen=True) class Grid: origin: tuple[float, float]; cell_m: float; width: int; height: int; cells: np.ndarray` (bool, bentuk `(height, width)`)
  - `make_grid(bounds: tuple[float, float, float, float], cell_m: float = CELL_M, margin: float = MARGIN_M) -> Grid` (`bounds = (minx, miny, maxx, maxy)`; ValueError bila melebihi `MAX_CELLS`)
  - `grid_from_rows(rows: list[str], cell_m: float = 1.0, origin=(0.0, 0.0)) -> Grid` (`#` tembok, `.` walkable; baris pertama = y tertinggi)
  - `seed(grid, sequences: list[list[tuple[float, float]]], radius: float = SEED_RADIUS_M) -> Grid`
  - `apply_strokes(grid, strokes: list[dict]) -> Grid` (`{"mode": "paint"|"erase", "radius": float, "points": [[x, y], ...]}`, urut daftar)
  - `erode(grid, radius: float = AGENT_RADIUS_M) -> Grid`
  - `planning_grid(bounds, sequences, strokes) -> Grid` (`make_grid` lalu `seed`, `apply_strokes`, `erode`)
  - `components(grid) -> np.ndarray` (int32 `(height, width)`, 0 = bukan walkable, label 1, 2, ... menurut indeks sel pertama; delapan arah tanpa memotong sudut)
  - `anchor(grid, point: tuple[float, float]) -> tuple[int, float] | None` (sel sendiri bila walkable; selain itu sel walkable terdekat; `None` bila tidak ada sel walkable)
  - `encode(grid) -> dict` (`cell_m, origin, width, height, bits`) dan `decode(d: dict) -> Grid`
  - `room_warnings(grid, rooms: list[dict]) -> list[str]` (`rooms` = `{"name", "x", "y"}`; dua jenis peringatan, lihat Step 7)

- [ ] **Step 1: Tulis tes (`tests/test_walkable.py`) yang gagal.** Helper tes `at(g, x, y) -> bool` = `g.cells[int((y - oy) // c), int((x - ox) // c)]`. Tes dan nilainya:
  - `test_make_grid_extent`: `make_grid((0, 0, 2, 0), margin=1.0)` → `origin == (-1.0, -1.0)`, `width == 40`, `height == 20`, semua `False`. Lebar dihitung `ceil(round(extent / cell_m, 6))` supaya tidak terjebak galat float.
  - `test_make_grid_coarsens_then_refuses`: `make_grid((0, 0, 100, 100), margin=0).cell_m == 0.2`; `make_grid((0, 0, 300, 300), margin=0)` melempar `ValueError`.
  - `test_seed_stamps_a_band_with_round_caps`: `seed(make_grid((0, 0, 2, 0), margin=1.0), [[(0, 0), (2, 0)]])` → `at(1.0, 0.0)`, `at(1.0, 0.4)`, `at(-0.4, 0.0)` True; `at(1.0, 0.7)`, `at(-0.7, 0.0)` False.
  - `test_strokes_apply_in_order`: dari grid hasil seed di atas, `paint` radius 0,3 di (1,1) → `at(1.0, 1.0)` True; `erase` radius 0,3 di (1,0) → `at(1.0, 0.0)` False tetapi `at(1.0, 0.4)` tetap True; paint di (1,0) setelah erase memulihkannya.
  - `test_erode_drops_spurs_and_shrinks_edges`: `Grid(origin=(0, 0), cell_m=0.1, width=40, height=40, cells=...)` dengan `cells[10:30, 10:30] = True` (blok 2,0 x 2,0) dan `cells[19:21, 30:40] = True` (ekor 2 sel). Setelah `erode(radius=0.2)` (jari-jari 2 sel): `cells[20, 20]` True, `cells[20, 12]` True, `cells[20, 11]` False (1 sel dari tepi), `cells[15, 28]` False (dekat ekor), `cells[20, 35]` False (ekor hilang).
  - `test_components_separate_blobs_and_diagonals`: `grid_from_rows(["..#..", "..#.."])` → `labels[0, 0] == 1`, `labels[0, 3] == 2`, `labels[0, 2] == 0`; `grid_from_rows([".#", "#."])` (dua sel bersilang diagonal, kedua sel orthogonal tembok) → `labels[0, 1] == 1` dan `labels[1, 0] == 2` (tidak digabung).
  - `test_anchor`: pada `grid_from_rows(["#.#"])`: `anchor((1.5, 0.5)) == (1, 0.0)`; `anchor((0.5, 0.5)) == (1, 1.0)` (titik di tembok → sel walkable terdekat); pada `grid_from_rows([".#."])`: `anchor((1.5, 0.5)) == (0, 1.0)` (seri → indeks terkecil); pada `grid_from_rows(["..."])`: `anchor((-10.5, 0.5)) == (0, 11.0)` (titik di luar grid tetap dapat jangkar); grid tanpa sel walkable → `None`.
  - `test_encode_bit_order_and_roundtrip`: `encode(grid_from_rows([".#######"]))["bits"] == "AQ=="`, `[ "#######." ]` → `"gA=="`, `["#.", ".#"]` → `"CQ=="` (mengunci urutan baris: baris pertama teks = y tertinggi = indeks 2 dan 3); `decode(encode(g))` memberi `cells` sama untuk grid acak 37 x 23.
  - `test_room_warnings`: `grid_from_rows(["...", "###", "###", "###", "..."])` (dua blob sama besar; komponen utama = jumlah sel terbanyak, seri: label terkecil, yaitu blob bawah). Ruangan X di (1.5, 0.5) tanpa peringatan; Y di (1.5, 4.5) → `"Room Y is not connected to the main walkable area"`; Z di (1.5, 2.5) (di tembok, 2,0 dari kedua blob, terikat ke indeks terkecil = blob bawah) → `"Room Z is 2.0 from the walkable area (more than 1.5)"` dan tidak diperingatkan soal koneksi.
  - `test_planning_grid_composes`: `planning_grid` dari satu urutan dan satu goresan erase memberi hasil sama dengan memanggil keempat fungsi manual.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `python -m pytest tests/test_walkable.py -q` → Expected: gagal (`ModuleNotFoundError: server.walkable`).
- [ ] **Step 3: Implementasi** semua fungsi di atas dengan numpy. `seed` dan `apply_strokes` memakai jarak titik ke ruas (vektor, per kotak pembatas ruas). Erosi: sel tetap hidup hanya bila semua sel dengan `hypot(dx, dy) * cell_m <= radius` (offset bulat) hidup, di luar grid dianggap mati.
- [ ] **Step 4: Jalankan tes.** Run: `python -m pytest tests/test_walkable.py -q` → Expected: semua lolos. Lalu `ruff check server tests && ruff format --check server tests`.
- [ ] **Step 5: Commit** `feat(walkable): grid from scan path and brush strokes, with anchor and bit encoding` (usulan, tunggu perintah).

### Task 2: Perencana rute dan kasus uji bersama

**Files:**
- Modify: `server/walkable.py`, `docs/specs/2026-10-21-area-walkable-panah-poi-design.md` (5A langkah 1 dan 4 sesuai ruling)
- Create: `tests/fixtures/walkable_cases.json`
- Test: `tests/test_walkable.py` (tambahan)

**Interfaces:**
- Consumes: `Grid`, `anchor`, `grid_from_rows`, `encode` dari Task 1.
- Produces: `plan_route(grid: Grid, start: tuple[float, float], goal: tuple[float, float]) -> dict | None` → `{"points": [[x, y], ...], "length_m": float}`; `None` bila tidak ada sel walkable atau tidak terjangkau.
- Berkas `tests/fixtures/walkable_cases.json` (disalin ke repo mobile di Task 5): `{"cases": [{"name", "cell_m", "origin", "rows", "from", "to", "expect"}], "bits": [{"rows", "cell_m", "origin", "b64"}]}`; `expect` = `{"unreachable": true}` atau `{"points": [...], "length_m": n}`.

- [ ] **Step 1: Tulis `walkable_cases.json` dan tes pelahap-nya (`test_shared_route_cases`, `test_shared_bit_cases`).** Semua nilai di bawah sudah dihitung tangan dari aturan Global Constraints (cell 1,0 dan origin (0,0) kecuali disebut):
  - `open`: `["...", "...", "..."]`, dari (0.5,0.5) ke (2.5,2.5) → `[[0.5,0.5],[2.5,2.5]]`, 2.8284.
  - `detour`: `[".#.", ".#.", "..."]`, dari (0.5,2.5) ke (2.5,2.5) → `[[0.5,2.5],[0.5,0.5],[2.5,0.5],[2.5,2.5]]`, 6.0.
  - `snap`: `["#.."]`, dari (0.5,0.5) ke (2.5,0.5) → `[[0.5,0.5],[1.5,0.5],[2.5,0.5]]`, 2.0.
  - `walled`: `[".#."]`, dari (0.5,0.5) ke (2.5,0.5) → `unreachable`.
  - `no-corner-cut`: `[".#", "#."]`, dari (0.5,1.5) ke (1.5,0.5) → `unreachable`.
  - `scaled`: cell 0.5, origin (10,20), `["...", "...", "..."]`, dari (10.25,20.25) ke (11.25,21.25) → `[[10.25,20.25],[11.25,21.25]]`, 1.4142.
  - `same-cell`: `["..."]`, dari (0.5,0.5) ke (0.9,0.5) → `[[0.5,0.5],[0.9,0.5]]`, 0.4.
  - `outside`: `["..."]`, dari (-5.5,0.5) ke (2.5,0.5) → `[[-5.5,0.5],[0.5,0.5],[2.5,0.5]]`, 8.0.
  - `pillar` (mengunci tie-break): `["...", ".#.", "..."]`, dari (0.5,0.5) ke (2.5,2.5). Dua jalur sama panjang (lewat pojok kanan bawah atau kiri atas, biaya 40); aturan `f`, lalu `h`, lalu indeks memilih pojok kanan bawah (dihitung tangan: indeks 2 dipop sebelum indeks 6) → `[[0.5,0.5],[2.5,0.5],[2.5,2.5]]`, 4.0.
  - bit: `[".#######"]` → `AQ==`; `["#######."]` → `gA==`; `["#.", ".#"]` → `CQ==`.
  Perbandingan: `points` dan `length_m` dengan toleransi 1e-3. Tes tambahan `test_plan_route_empty_grid_is_none` (grid tanpa sel walkable → `None`).
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `python -m pytest tests/test_walkable.py -q -k "shared or plan_route"` → Expected: gagal (`plan_route` belum ada).
- [ ] **Step 3: Implementasi `plan_route`.** Rangka yang tidak ditentukan oleh tanda tangan:

```python
# A*: heap berisi (f, h, idx). g disimpan di dict/array int. Pop yang sudah closed atau g-nya basi dilewati.
# Peluruskan: dari sel i, tes sel terjauh j (mulai dari akhir jalur) yang lolos los(i, j); ambil j; ulangi.
def _los(cells, a, b):  # Bresenham bilangan bulat (semua oktan); True bila semua sel yang dikunjungi walkable
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        if not cells[y0, x0]: return False
        if (x0, y0) == (x1, y1): return True
        e2 = 2 * err
        if e2 >= dy: err += dy; x0 += sx
        if e2 <= dx: err += dx; y0 += sy

# titik rute: R = sel hasil peluruskan (R[0] sel awal, R[-1] sel tujuan, mungkin sama).
mid = list(R)
if len(mid) == 1:
    if start_ok and goal_ok: mid = []
else:
    if goal_ok: mid.pop()
    if start_ok: mid.pop(0)
# start_ok / goal_ok = sel sendiri walkable. points = [start] + pusat(mid) + [goal]
```
  Panjang = jumlah jarak Euclid antar `points`. Perbarui spesifikasi 5A (langkah 1 dan 4) sesuai ruling.
- [ ] **Step 4: Jalankan tes.** Run: `python -m pytest tests/test_walkable.py -q` → Expected: semua lolos; lalu ruff.
- [ ] **Step 5: Commit** `feat(walkable): grid route planner and shared route cases` (usulan).

### Task 3: Database, API goresan, rute, Publish, dan `/navgraph`

**Files:**
- Modify: `server/db.py`, `server/area_api.py`, `server/navgraph.py`, `tests/test_area_api.py`, `tests/test_navgraph.py`
- Create: `server/migrations/versions/0004_area_walkable.py`

**Interfaces:**
- Consumes: `walkable.planning_grid`, `plan_route`, `anchor`, `encode`, `decode`, `room_warnings`, `MAX_CELLS` (Task 1 dan 2); `_scene(area_id, loc)["meta"]` dan `_draft` yang ada di `area_api.py`.
- Produces:
  - Model `WalkableStroke` (tabel `walkable_stroke`: `id`, `area_id`, `mode`, `radius`, `points` JSON, `created_by`, `created_at`); kolom `PublishedGraph.walkable: dict | None` (JSON); migrasi `0004` dari `0003`.
  - `GET /api/areas/{id}/walkable` → `{cell_m, origin, width, height, bits, walkable_cells, strokes: [{id, mode, radius, points_count}], warnings}`
  - `POST /api/areas/{id}/strokes` (201) body `{mode, radius, points}`; `DELETE /api/areas/{id}/strokes/{sid}` (204); `DELETE /api/areas/{id}/strokes` (204)
  - `POST /api/areas/{id}/route` → `{"status": "ok", "points": [[x, y], ...], "length_m": n}` atau `{"status": "unreachable"}` (kunci `nodes` dihapus)
  - `POST /api/areas/{id}/publish-graph` menerbitkan `graph` (seperti sekarang) dan `walkable` (hasil `encode` + `targets: [{id: "R<id>", name, x, y}]`); `{published_at, warnings}`; 409 bila tidak ada sel walkable (`"no walkable area"`), tidak ada ruangan (`"add a room first"`), atau grid melebihi `MAX_CELLS`
  - `GET /navgraph` menambah `revision` (= `published_at` ISO) dan `walkable` bila ada; `graph` tidak berubah

- [ ] **Step 1: Tulis tes yang gagal** (fixture `client` yang ada: jalur L x 0..6 lalu y 0..4, area `floor10`; helper `at(grid, x, y)` diimpor dari `tests/test_walkable.py`). Tes baru:
  - `test_walkable_is_seeded_from_the_scan_path`: GET → 200, `cell_m == 0.1`, `walkable_cells > 0`; setelah `walkable.decode`, `at(3.0, 0.0)` True dan `at(3.0, 3.0)` False.
  - `test_stroke_paint_erase_undo_reset`: paint r=0,5 di (3,3) → 201 dan `at(3,3)` True; `DELETE` goresan itu → kembali False; erase r=0,5 di (3,0) → `at(3,0)` False; `DELETE /strokes` → 204 dan semua kembali ke seed.
  - `test_undo_removes_the_highest_id_only`: dua goresan; hapus `strokes[-1]` menyisakan goresan pertama.
  - `test_stroke_validation`: radius 0,05 dan 4 → 422; titik kosong → 422; 2001 titik → 422; body mentah `{"mode":"paint","radius":1,"points":[[NaN,0]]}` dengan `content-type: application/json` → 422; `mode` selain paint/erase → 422; tamu → 403; tanpa JSON → 415 atau 422 (form dan text/plain tidak menulis apa pun, seperti `test_cross_site_form_writes_nothing`); tidak ada goresan tersimpan setelah semuanya.
  - `test_route_is_straight_when_the_line_is_clear`: ruangan di (3.0, 0.1), mulai (0.5, 0.0) → `ok`, `points == [[0.5, 0.0], [3.0, 0.1]]`, `length_m ≈ hypot(2.5, 0.1)`.
  - `test_route_unreachable_after_cutting_the_corridor`: ruangan di (6.0, 3.0), erase r=1 di (3,0) → mulai (0.5, 0.0) memberi `{"status": "unreachable"}`.
  - `test_publish_requires_walkable_area_and_a_room`: tanpa ruangan 409 `add a room first`; erase r=3 menyusuri jalur (titik (0,0), (3,0), (6,0), (6,2), (6,4)) lalu ruangan → 409 `no walkable area`.
  - `test_publish_sends_walkable_and_revision`: tambah ruangan "Lab", publish → 200; `GET /navgraph` memuat `graph` (bentuk lama), `walkable.targets[0] == {"id": "R1", "name": "Lab", "x": ..., "y": ...}`, `revision == published_at`, dan `walkable.decode(...)` sama dengan grid rencana.
  - `test_walkable_too_large_is_refused`: `monkeypatch.setattr(walkable, "MAX_CELLS", 10)` → GET `/walkable` 409 `area too large`.
  - Perbarui tes route lama yang menegaskan `nodes` (`test_route_*`, simulasi) ke bentuk `points` + `length_m`. Di `tests/test_navgraph.py`: `revision` ada saat graf terbit dari database dan tidak ada saat dari berkas.
- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `python -m pytest tests/test_area_api.py tests/test_navgraph.py -q` → Expected: gagal pada tes baru.
- [ ] **Step 3: Implementasi.**
  - Model dan migrasi `0004` (tabel baru dan kolom `walkable` nullable, seperti pola `0003`).
  - `_grid(s, area_id, loc)` di `area_api.py`: ambil `meta` dari `_scene`, `bounds = (origin_x, origin_y, origin_x + width * res_m, origin_y + height * res_m)`, `sequences` dari `routegraph.split_sequences` yang sama dengan graf dasar (jadikan satu helper bersama), `strokes` dari tabel urut `id`; cache di `_cache` dengan kunci `("grid", area_id, align json, jumlah image, id goresan terakhir)`; `ValueError` dari `make_grid` → 409 `area too large for a walkable grid`.
  - Endpoint sesuai Interfaces. Body pydantic `StrokeIn(mode: Literal[...], radius: float = Field(ge=0.1, le=3, allow_inf_nan=False), points: list[XYFinite] = Field(min_length=1, max_length=2000))`. Penulisan lewat `_write` yang ada.
  - `_published(area_id)` di `navgraph.py` mengembalikan `{"graph", "walkable", "revision"}`; `get_navgraph` menyalin `walkable` dan `revision` ke jawaban bila ada.
- [ ] **Step 4: Jalankan seluruh suite.** Run: `python -m pytest -q` → Expected: semua lolos (333 lama + tambahan), ruff bersih. Jalankan juga `alembic upgrade head` terhadap sqlite kosong lewat tes migrasi yang sudah ada (tes alembic butuh `.venv` utama di PATH).
- [ ] **Step 5: Commit** `feat(area): walkable strokes, grid route, and walkable payload in /navgraph` (usulan).

### Task 4: Dashboard (mode Walkable)

**Files:**
- Modify: `web/lib/api.ts`, `web/components/AreaMap.tsx`, `web/app/area/page.tsx`, `docs/specs/2026-10-21-area-walkable-panah-poi-design.md` (5C label)
- Create: `web/lib/walkable.ts`

**Interfaces:**
- Consumes: endpoint Task 3.
- Produces: tipe `WalkableData` (`cell_m, origin, width, height, bits, walkable_cells, strokes, warnings`), `areaApi.walkable(id)`, `areaApi.addStroke(id, {mode, radius, points})`, `areaApi.deleteStroke(id, sid)`, `areaApi.resetStrokes(id)`; `RouteResult` ok berisi `points` dan `length_m` (tanpa `nodes`); `web/lib/walkable.ts`: `decodeBits(b64: string): Uint8Array`, `countCells(bits: Uint8Array, n: number): number`, `overlayImage(w: WalkableData): string` (data URL; baris 0 = y terendah = dasar gambar).

- [ ] **Step 1: Tulis dulu cek verifikasinya** (web tidak punya test runner; buktinya build dan pratinjau). Tentukan hasil yang diharapkan: `countCells(decodeBits(bits), width * height) === walkable_cells` untuk data dari server; garis oranye Test route lurus mengikuti `points`; setelah Publish panel hasil tetap tampil.
- [ ] **Step 2: Implementasi.**
  - `MapMode` = `view | walkable | rooms | test` (Routes disembunyikan; lapisan simpul dan sisi graf lama dihapus dari `AreaMap`; jalur scan tetap tampil samar).
  - `AreaMap`: overlay hijau transparan dari `overlayImage` diletakkan di piksel peta (`x = (grid.ox - plan.ox) / res`, lebar = `W * cell / res`; tepi atas dihitung dari `y` atas grid), `image-rendering: pixelated`. Di mode `walkable` (admin saja): pointer-down mulai goresan, pointer-move menambah titik bila jarak ≥ 0,05 dari titik terakhir, polyline tebal `2r / res` dengan ujung bulat sebagai pratinjau, lingkaran kursor berjari-jari kuas, pointer-up mengirim satu goresan lewat `onStroke(mode, radius, points)`. Label ruangan: huruf 1,8% dari lebar peta, halo putih (`paintOrder: "stroke"`).
  - `page.tsx`: bilah mode, panel Walkable (Paint/Erase, ukuran kuas 0,3 sampai 1,5, Undo = hapus goresan `id` terbesar, Reset to scan path lewat panel konfirmasi di halaman, jumlah goresan, peringatan), Test route memakai `points`, panel hasil Publish tetap tampil ("Published at HH:MM. The app loads it on the next Localize (builds older than 21 Oct evening need a restart).") sampai ditutup atau ada editan baru, panel "Route edits" dihapus.
  - Perbarui spesifikasi 5C (ukuran label) sesuai ruling.
- [ ] **Step 3: Build.** Run: `npx next build --webpack` di `web/` (junction sementara) → Expected: lolos, `/area` tergenerate, TypeScript bersih.
- [ ] **Step 4: Pratinjau lokal dengan data hcm-lantai-10** (scratchpad `area-local/serve_area.py`; hapus `area.db` lama dulu karena skema berubah; data tidak masuk repo): mode Walkable menampilkan overlay yang menyelimuti jalur; cat ruang baru, hapus, Undo, Reset berjalan; `countCells(...) === walkable_cells` di konsol; Test route menggambar garis lurus (bukan mengikuti graf); Publish memunculkan panel dan `/navgraph` memuat `walkable` dengan `targets`. Ambil tangkapan layar untuk dilaporkan. Hapus junction setelahnya.
- [ ] **Step 5: Commit** `feat(web): walkable brush, straight route test, persistent publish result` (usulan).

### Task 5: Aplikasi, perencana C#, pengambilan ulang, dan peta kecil

**Files (repo `eutopos-mobile`):**
- Create: `Assets/Eutopos/Scripts/Core/WalkableGrid.cs`, `Assets/Eutopos/Scripts/Core/Route.cs`, `Assets/Eutopos/Scripts/Core/NavRefresh.cs`, `Assets/Eutopos/Tests/EditMode/WalkableCasesTests.cs`, `Assets/Eutopos/Tests/EditMode/walkable_cases.json` (salinan dari server), `Assets/Eutopos/Tests/EditMode/NavRefreshTests.cs`
- Modify: `Scripts/Core/VpsResponses.cs`, `Scripts/App/AppController.cs`, `Scripts/App/AppController.Navigation.cs`, `Scripts/App/MiniMap.cs`, `Tests/EditMode/VpsResponsesTests.cs`
- Delete: `Scripts/Core/NavGraph.cs`, `Tests/EditMode/NavGraphTests.cs`, `Tests/EditMode/RouteCasesTests.cs`, `Tests/EditMode/route_cases.json` (beserta `.meta`)

**Interfaces:**
- Consumes: bentuk `walkable` dari `/navgraph` (Task 3), `walkable_cases.json` (Task 2).
- Produces:
  - `Route(List<Vector2> points)` dengan `Points` dan `LengthM` (tanpa `NodeIds`), di `Core/Route.cs`
  - `WalkTarget(string Id, string Name, Vector2 Position)`
  - `WalkableGrid`: `static WalkableGrid Parse(string walkableJson)` (membaca juga `targets`), `static WalkableGrid FromRows(string[] rows, double cellM, Vector2 origin)` (baris pertama = y tertinggi, untuk tes), `IReadOnlyList<WalkTarget> Targets`, `Vector2 BoundsMin/BoundsMax`, `bool IsWalkable(int col, int row)`, `Route Plan(Vector2 from, Vector2 to)` (null bila tidak terjangkau), `static bool Arrived(Vector2 user, Vector2 target, float radiusM = 1f)`
  - `NavRefresh.ShouldReplace(string current, string incoming, bool navigating) -> bool` (`!navigating && incoming != null && incoming != current`)
  - `NavGraphResult.Nav` (WalkableGrid) dan `NavGraphResult.Revision` menggantikan `Graph`

- [ ] **Step 0: Worktree mobile.** Bila PR eutopos-mobile#2 sudah di-merge: `git worktree add D:/wt/walkable-app -b feat/walkable-app origin/main`; bila belum: dari `test/route-cases` (memuat fase B). Library butuh impor pertama (10 sampai 15 menit); boleh menyalin `Library` dari `D:/wt/route-cases` bila Bagus setuju.
- [ ] **Step 1: Tulis tes yang gagal.**
  - `WalkableCasesTests.RouteCasesMatchTheServer`: baca `walkable_cases.json`, bangun grid dengan `FromRows`, `Plan`, bandingkan `Points` dan `LengthM` dengan toleransi 1e-3, dan `null` untuk `unreachable`. `BitCasesMatchTheServer`: bangun dari `rows`, ubah ke bentuk `walkable` JSON dengan `bits` dari fixture (`b64`), `Parse`, lalu pastikan sel yang walkable sama dengan `rows`.
  - `NavRefreshTests`: `ShouldReplace("a", "b", false)` true; `("a", "a", false)` false; `("a", "b", true)` false; `("a", null, false)` false; `(null, "b", false)` true.
  - `VpsResponsesTests`: respons 200 dengan `walkable` → `Status.Ok`, `Nav.Targets` terbaca, `Revision` terisi; respons 200 tanpa `walkable` → `NotFound`; `walkable` rusak (bits bukan base64, `width * height` tidak cocok dengan panjang bits) → `ServerError` dengan "graf rusak".
- [ ] **Step 2: Jalankan, pastikan gagal.** Run (PowerShell): `Start-Process -Wait -FilePath <Unity.exe> -ArgumentList '-batchmode','-projectPath','D:\wt\walkable-app','-runTests','-testPlatform','EditMode','-testResults','D:\wt\walkable-app\TestResults-EditMode.xml','-logFile','D:\wt\walkable-app\Logs\editmode.log'` → Expected: galat kompilasi atau gagal (`WalkableGrid` belum ada).
- [ ] **Step 3: Implementasi `Core`.** `WalkableGrid.Plan` mengikuti Global Constraints persis: bilangan bulat untuk biaya dan indeks, `origin` dan `cellM` disimpan `double` dan dipakai `double` saat mengikat titik ke sel dan menghitung jarak jangkar (supaya seri sama dengan Python), heap biner sendiri dengan kunci `long` `(f << 42) | (h << 22) | idx` (`PriorityQueue<T>` tidak tersedia di profil .NET Unity ini), `Los` Bresenham dan aturan `mid` sama dengan Task 2. `Route` dipindah ke `Core/Route.cs`. `VpsResponses.ParseNavGraph` membaca `walkable` dan `revision`.
- [ ] **Step 4: Implementasi `App`.**
  - `AppController.Navigation.cs`: `NavGraph graph` menjadi `WalkableGrid nav` dan `string navRevision`; `EnsureNavGraph(bool refresh = false)` mengambil bila `!fetchingGraph && vps.Config != null && !navigating && (nav == null || refresh)`; `OnNavGraph` mengganti `nav` bila `nav == null` atau `NavRefresh.ShouldReplace(navRevision, r.Revision, navigating)`, mempertahankan target terpilih menurut `Id`, dan tidak menimpa `lastMessage` dengan galat bila `nav` sudah ada. Tombol Lokalisasi memanggil `EnsureNavGraph(refresh: true)` (`AppController.cs:83`). `Replan` memakai `nav.Plan(user, target.Position)`; `Arrived` memakai `target.Position`; log `route` mencatat `waypoints` dan `length_m`; log `navgraph` mencatat `revision`.
  - `CyclePoint`, `SelectedPoint`, `MarkGroundTruth`: iterasi `nav.Targets` (ruling).
  - `MiniMap.Draw(WalkableGrid nav, Route route, NumV2? userG, float yawB)`: latar dari sel walkable (sampel per piksel), target jingga, rute biru, pengguna merah seperti sekarang.
  - Hapus berkas lama (daftar di atas) dan referensinya.
- [ ] **Step 5: Jalankan tes.** Run: perintah Unity yang sama → Expected: `test-run result="Passed"` dan tidak ada tes gagal; baca XML hasilnya.
- [ ] **Step 6: Commit** `feat(app): plan routes on the walkable grid and refresh it on Localize` (usulan).

### Task 6: Panah chevron

**Files (repo `eutopos-mobile`):**
- Create: `Scripts/Core/ChevronPlacer.cs`, `Tests/EditMode/ChevronPlacerTests.cs`
- Modify: `Scripts/App/RouteView.cs` (ditulis ulang)

**Interfaces:**
- Consumes: `Route.Points` (Task 5).
- Produces: `ChevronPlacer.Place(IReadOnlyList<Vector2> points, float spacingM, float phaseM, float maxAheadM, float fadeM, float minAheadM = 0.5f) -> List<Chevron>`; `readonly struct Chevron { int Index; Vector2 Position; Vector2 Direction; float Alpha; }`; melempar `ArgumentOutOfRangeException` bila `phaseM` di luar `[0, spacingM)`. Panah `k` berada `d_k = k * spacing - phase` dari tujuan menurut panjang busur; dipakai bila `d_k >= 0` dan `s = L - d_k` ada di `[minAheadM, maxAheadM]`; `Alpha = clamp((maxAhead - s) / fade, 0, 1)`; `Direction` = singgung ruas yang memuat `s`.

- [ ] **Step 1: Tulis tes yang gagal** (`ChevronPlacerTests`): rute lurus (0,0)→(10,0), spacing 0,9, phase 0, maxAhead 8, fade 2 → 8 panah (`Index` 3 sampai 10), semua `Direction == (1,0)`, `Position.X` = 7,3; 6,4; ...; 1,0, alfa panah terjauh 0,35 (toleransi 1e-3) dan 1 untuk `s <= 6`; **diam di dunia**: rute (0.4,0)→(10,0) memberi `Position` yang sama untuk `Index` yang sama; rute siku (0,0)→(5,0)→(5,5): panah `Index 3` di (5, 2.3) dengan `Direction == (0,1)`; `phase = 0.45` menggeser tiap posisi 0,45 ke arah tujuan; `phase = 0.9` melempar; rute pendek (L < 0,5) dan titik tunggal → kosong.
- [ ] **Step 2: Jalankan, pastikan gagal** (perintah Unity Task 5) → Expected: gagal (`ChevronPlacer` belum ada).
- [ ] **Step 3: Implementasi `ChevronPlacer`** (murni, tanpa Unity).
- [ ] **Step 4: Tulis ulang `RouteView`:** kolam 12 objek, satu `Mesh` V (enam verteks, normal ke atas) dan satu material `Sprites/Default` yang dibagi, nuansa warna biru yang sama; alfa lewat `MaterialPropertyBlock` (`_Color`). `Show(Route)` menyimpan titik; `Update` menghitung `phase = (Time.time * 0.6f) % 0.9f`, memanggil `Place`, memasang panah `k` di slot `k % 12` pada ketinggian 0,03 dengan lerp posisi (`1 - exp(-10 * dt)`, langsung loncat bila slot tidak aktif), dan menyembunyikan slot yang tidak terpakai. `Clear()` menyembunyikan semuanya. API publik `Show` dan `Clear` tidak berubah.
- [ ] **Step 5: Jalankan tes** (perintah Unity Task 5) → Expected: semua lolos, termasuk `ChevronPlacerTests`.
- [ ] **Step 6: Commit** `feat(app): chevron arrows that stay put in the world and flow to the goal` (usulan).

### Task 7: Penanda POI melayang

**Files (repo `eutopos-mobile`):**
- Create: `Scripts/Core/PoiLabel.cs`, `Tests/EditMode/PoiLabelTests.cs`, `Scripts/App/PoiPin.cs`
- Modify: `Scripts/App/AppController.Navigation.cs`

**Interfaces:**
- Consumes: `WalkTarget` dan `WalkableGrid.Targets` (Task 5).
- Produces: `PoiLabel.Format(string name, float distanceM) -> string` (`"Kamar Tidur, 3.2 m"`, satu desimal, budaya invarian seperti banner yang ada); `PoiPin : MonoBehaviour` dengan `Show(WalkTarget target, float distanceM)` dan `Hide()`.

- [ ] **Step 1: Tulis tes yang gagal:** `PoiLabelTests`: `Format("Kamar Tidur", 3.24f) == "Kamar Tidur, 3.2 m"`, `Format("Lab", 0f) == "Lab, 0.0 m"`, `Format("Lab", 12.96f) == "Lab, 13.0 m"`, nama kosong → `"?, 3.2 m"` bukan crash.
- [ ] **Step 2: Jalankan, pastikan gagal** (perintah Unity Task 5).
- [ ] **Step 3: Implementasi `PoiLabel`.**
- [ ] **Step 4: Implementasi `PoiPin`:** bola kecil #E07A2E (primitif, material `Sprites/Default`) pada tinggi 1,5 di `BuildingRoot` (titik B = `(x, tinggi, y)`), garis tipis ke lantai (`LineRenderer`), World Space Canvas dengan `Text` (font dan gaya sama dengan `AppUi.Label`, `AppUi.cs:97`) di atas bola, menghadap kamera hanya pada yaw, skala `Mathf.Clamp(distance * k, min, max)`, bobbing kecil. `AppController.UpdateNavigation`: tiap frame, bila `nav != null`, `targetIndex >= 0`, `rootCtl.HasAlignment` dan tidak `needsRelocalize` → `pin.Show(target, jarak ke pengguna)`, selain itu `pin.Hide()`.
- [ ] **Step 5: Jalankan tes** (perintah Unity Task 5) → Expected: `PoiLabelTests` lolos, suite penuh hijau. `PoiPin` murni visual, diperiksa di Task 8.
- [ ] **Step 6: Commit** `feat(app): floating pin marking the selected POI` (usulan).

### Task 8: Merge, deploy, build, dan uji di ponsel

**Files:** tidak ada kode; hanya langkah operasional. Setiap langkah yang berefek keluar worktree menunggu izin Bagus.

- [ ] **Step 1: Review akhir.** Tanyakan Bagus apakah mau reviewer terpisah (sebelumnya ia menolak dispatch); bila tidak, self-review dan sebut terang-terangan di laporan. Kumpulkan "Rulings I made" dan "Deferred minors" dari ledger.
- [ ] **Step 2: PR dan merge atas perintah Bagus.** Server dulu (migrasi `0004` jalan otomatis saat `api` start). Sebelum merge, cek PC Lab tidak sedang ada job `queued` atau `running` dan tidak ada uji lapangan. Tunggu autodeploy 5 menit, pastikan `api` healthy dan `alembic current` = `0004 (head)`.
- [ ] **Step 3: Bagus mencat area di dashboard** hcm-lantai-10 (Walkable), menguji rute (Test route, garis harus lurus), lalu Publish. Periksa bahwa `GET /navgraph` memuat `walkable` (baca lewat ssh, tanpa mencetak token).
- [ ] **Step 4: Build APK** atas izin Bagus (PR mobile di-merge atau dibangun dari cabangnya), pasang di TECNO KL7.
- [ ] **Step 5: Uji lapangan.** Lokalisasi tanpa menutup aplikasi setelah satu Publish lagi (pastikan target baru muncul tanpa restart). Periksa: panah tidak berbalik arah di awal, rute lurus dan tidak menembus meja, pin muncul di lokasi tujuan dan hilang saat perlu Lokalisasi ulang, dan catat jarak langkah dari pintu saat banner Sampai muncul. Tarik log dengan `adb pull` dari `/sdcard/Android/data/com.rockhead07.eutopos/files/logs/` ke scratchpad (jangan masuk repo).
- [ ] **Step 6: Laporkan** hasil, dan usulkan pekerjaan berikutnya: pensiun `graph` lama, penampil 3D `.glb` (butuh izin `npm install`), dan protokol pengukuran akurasi.
