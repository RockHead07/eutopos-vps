# Rute otomatis, ruangan, dan uji rute di dashboard: Rencana Implementasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Staf membuat rute dari jalur scan secara otomatis, menaruh ruangan dan menguji rute di dashboard web, lalu menerbitkannya ke aplikasi ponsel yang sudah ada tanpa CSV, tanpa Unity, dan tanpa build ulang APK.

**Architecture:** Modul Python murni `server/routegraph.py` membangun graf dasar dari pusat kamera, menerapkan editan dan ruangan, menyusun `navgraph.json`, dan menghitung rute dengan aturan yang sama dengan `NavGraph` C#. `server/floorplan.py` merender peta 2D, menulis .glb, dan memegang konversi ke kerangka G. `server/area_api.py` melayani semuanya di bawah `/api/areas/{area_id}/...` dari model peta yang sudah dimuat `api` (versi terbit); ruangan, editan, dan graf terbit disimpan di PostgreSQL, dan `/navgraph` membaca graf terbit dari sana. Worker membuat foto kecil frame scan ke folder peta. Dashboard menambah halaman `/area?id=`.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Alembic, numpy, Pillow, pycolmap 4.2.1 (container), pytest; Next.js 16 static export, React 19, TypeScript 5.9, Tailwind v4; Unity 6000.3 EditMode (satu tes di `eutopos-mobile`).

**Spec:** `docs/specs/2026-10-21-dashboard-rute-otomatis-design.md` (repo ini).

## Global Constraints

- Kerangka G: meter menurut `align.json`, tangan kanan, z ke atas, lantai z = 0. Skala masih dari koordinat asumsi: UI menulis "Scale not calibrated" di samping setiap angka jarak.
- Format terbit sama dengan `navgraph.json` sekarang (`frame: "building"`, `units: "m"`, `nodes[{id,x,y}]`, `edges[[a,b]]`, `targets[{node,name}]`) dan lolos `server.navgraph.validate`.
- Aturan rute = `NavGraph` C# di `eutopos-mobile` c93cd08: proyeksi posisi ke sisi terdekat (`TryProject`), A* dengan heuristik jarak Euclid ke simpul target, titik rute `[from, proyeksi, simpul...]`, Sampai bila jarak < 1,0.
- Semua endpoint baru di bawah `/api` (Cloudflare Access + JWT). Menulis dan menerbitkan hanya admin (`server.auth.is_admin`, `EUTOPOS_ADMINS`), selain itu 403.
- `api` membaca `/maps` saja (tidak menulis) dan tidak memasang `/data/jobs`. Tulisan ke `/maps` hanya oleh worker atau `manage`.
- Data area nyata (foto, awan titik, koordinat, graf) tidak pernah masuk repo atau fixture; tes memakai data sintetis.
- Teks UI dashboard berbahasa Inggris, seperti halaman lain. Teks tanpa em dash.
- Skema database lewat migrasi Alembic baru `0003`; tes memakai `SQLModel.metadata.create_all` pada sqlite seperti tes yang ada.
- Lint: `uv run ruff check .` dan `uv run ruff format --check .` (atau ruff dari `.venv` utama). Tes: `python -m pytest -q` dengan `.venv` utama di PATH. Web: `npm run build` di `web/`.
- Commit dan push hanya atas perintah Bagus; langkah Commit = titik commit yang diusulkan. Tanpa atribusi AI. Jangan merge saat uji lapangan, unggahan, atau pembangunan peta berjalan.
- Menjalankan perintah yang menulis di PC Lab (backfill foto, deploy) butuh izin Bagus pada saat itu.

## Review Focus

1. Perekam bolak-balik di lorong yang sama: graf harus satu jalur, bukan dua jalur sejajar yang membuat rute zig-zag. Dipatok di Task 1.
2. Ruangan ditaruh jauh dari jalur mana pun (misalnya 3 m di dalam blok meja): tetap tersambung, tetapi dashboard memperingatkan bila lebih dari 1,5 m dari rute. Dipatok di Task 2.
3. Menerbitkan saat graf dasar kosong atau area belum diselaraskan: ditolak dengan alasan, graf terbit lama tetap dipakai. Dipatok di Task 3.
4. Pengguna bukan admin mencoba menambah ruangan, mengedit, atau menerbitkan: 403, tidak ada yang berubah. Dipatok di Task 3.
5. Dua ruangan bernama sama di satu area: daftar target di aplikasi membingungkan, jadi ditolak dengan 409. Dipatok di Task 3.

---

## Ruling yang dibawa rencana ini (menyimpang dari teks spesifikasi)

- Spesifikasi 5f menulis graf terbit ke `<maps>/<area_id>/navgraph.json`. `api` tidak bisa menulis `/maps`, jadi graf terbit disimpan di tabel `published_graph` dan `/navgraph` membacanya lebih dulu, lalu jatuh ke berkas bila tidak ada. Satu pemilik: database.
- Spesifikasi 5d mengambil foto dari `/data/jobs/<id>/dataset/mapping`. `api` tidak memasang folder itu, jadi worker menulis foto kecil ke `<map_dir>/thumbs/` saat build, ditambah `manage thumbs` untuk peta lama.
- Logika `to_building` dari `server/mapcloud.py` (worktree `D:/wt/navcontent`, belum commit) dipindah ke `server/floorplan.py`. Endpoint `/mapcloud` tidak dipakai, karena spesifikasi 7 mensyaratkan semuanya lewat `/api`.

### Task 1: Graf dasar dari jalur kamera

**Files:**
- Create: `server/routegraph.py`
- Test: `tests/test_routegraph.py`

**Interfaces:**
- Produces:
  - `Graph = dict` berbentuk navgraph tanpa `targets`: `{"nodes": {id: (x, y)}, "edges": set[frozenset[str]]}`; tipe alias di modul.
  - `split_sequences(centers: list[tuple[float, float]], split_m: float = 1.5) -> list[list[tuple[float, float]]]` (pusat kamera berurutan menurut nama frame; dipotong bila dua frame berurutan berjarak > `split_m`).
  - `build_base_graph(sequences: list[list[tuple[float, float]]]) -> Graph`
  - Konstanta: `SMOOTH_WINDOW = 5`, `RESAMPLE_M = 0.5`, `MERGE_M = 0.6`, `SIMPLIFY_M = 0.15`.

- [ ] **Step 1: Tulis tes yang gagal**

Buat jalur sintetis dengan derau acak berseed (`numpy.random.default_rng(0)`, simpangan 0,05 m).

```python
def l_path():  # 0..6 di x lalu naik 0..4 di y, titik tiap 0,1 m
def test_noisy_l_path_becomes_a_smooth_l():
    g = build_base_graph([l_path()])
    assert 3 <= len(g["nodes"]) <= 8            # sudut tetap, ruas lurus dirangkum
    assert is_connected(g)
def test_walking_the_same_corridor_twice_gives_one_corridor():
    there = straight(0, 0, 8, 0); back = [(x, y + 0.2) for x, y in reversed(there)]
    g = build_base_graph([there + back])
    assert max(abs(y) for _, y in g["nodes"].values()) < 0.4   # tidak ada jalur sejajar kedua
    assert all(degree(g, n) <= 2 for n in g["nodes"])
def test_a_loop_closes_into_a_junction():   # persegi 4 x 4 yang kembali ke awal: graf siklik, tiap simpul derajat 2
def test_no_edge_crosses_area_the_camera_never_walked():
    g = build_base_graph([l_path()])
    for a, b in edges(g):  # titik tengah setiap sisi dekat dengan jalur asli
        assert min_dist(midpoint(g, a, b), l_path()) < MERGE_M
def test_sequences_are_split_at_jumps():
    assert len(split_sequences([(0, 0), (0.1, 0), (5, 0), (5.1, 0)])) == 2
```

Helper `is_connected`, `degree`, `edges`, `midpoint`, `min_dist` ditulis di berkas tes.

- [ ] **Step 2: Jalankan, pastikan gagal.** Run: `python -m pytest tests/test_routegraph.py -q`. Expected: `ImportError: cannot import name 'build_base_graph'`.
- [ ] **Step 3: Implementasi.** Per urutan: rata-rata bergerak `SMOOTH_WINDOW`, sampel ulang tiap `RESAMPLE_M` sepanjang jalur, gabung titik ke simpul yang sudah ada bila dalam `MERGE_M` (greedy, urutan jalur), sisi antara simpul titik-titik berurutan (tanpa sisi ke diri sendiri), lalu hapus simpul berderajat 2 yang menyimpang kurang dari `SIMPLIFY_M` dari garis kedua tetangganya. Id simpul `"N<n>"` berurutan.
- [ ] **Step 4: Jalankan, pastikan lolos.** Expected: semua PASS.
- [ ] **Step 5: Commit (titik commit yang diusulkan)**

```bash
git add server/routegraph.py tests/test_routegraph.py
git commit -m "feat(server): build a walkable route graph from the scan camera path"
```

### Task 2: Ruangan, editan, navgraph, dan aturan rute bersama

**Files:**
- Modify: `server/routegraph.py`
- Create: `tests/fixtures/route_cases.json`
- Test: `tests/test_routegraph.py`

**Interfaces:**
- Consumes: `Graph`, `build_base_graph` (Task 1).
- Produces:
  - `Edit = dict`: `{"id": int, "kind": "add_edge" | "remove_edge" | "move_node", "a": [x, y], "b": [x, y]}` (`move_node`: `a` = dari, `b` = ke).
  - `apply_edits(base: Graph, edits: list[Edit], match_m: float = 0.5) -> tuple[Graph, list[int]]` (graf baru + id editan yang tidak cocok).
  - `Room = dict`: `{"id": int, "name": str, "x": float, "y": float}`.
  - `compose_navgraph(graph: Graph, rooms: list[Room]) -> tuple[dict, list[str]]` (navgraph valid + peringatan). Simpul ruangan `"R<id>"`, disambung ke proyeksinya pada sisi terdekat (sisi dipecah di titik proyeksi). Peringatan bila ruangan > 1,5 m dari rute atau tak terjangkau dari ruangan lain.
  - `plan_route(navgraph: dict, start: tuple[float, float], target: str) -> dict | None` → `{"points": [[x, y], ...], "nodes": [...], "length_m": float}`; `arrived(user, target, radius_m: float = 1.0) -> bool`.
  - Berkas `tests/fixtures/route_cases.json`: `{"routes": [{"name", "graph": <navgraph>, "from": [x, y], "target": id, "expect": {"nodes": [...], "length_m": float} | {"unreachable": true}}], "arrivals": [{"user": [x, y], "target": [x, y], "expect": bool}]}`. Kasus dipilih dengan jalur terpendek tunggal (tanpa seri) supaya tidak bergantung urutan pemecah seri.

- [ ] **Step 1: Tulis tes yang gagal**

```python
def test_remove_edit_matches_by_coordinates_after_regeneration():
    base = build_base_graph([l_path()]); shifted = build_base_graph([shift(l_path(), 0.1)])
    corner_leg = [[6, 0], [6, 4]]
    g, unmatched = apply_edits(shifted, [{"id": 1, "kind": "remove_edge", "a": corner_leg[0], "b": corner_leg[1]}])
    assert unmatched == [] and not reachable(g, near(g, 0, 0), near(g, 6, 4))
def test_edit_that_no_longer_matches_is_reported():   # remove_edge di (20,20)-(21,20) -> unmatched == [1]
def test_room_is_attached_to_the_nearest_edge():
    nav, warn = compose_navgraph(build_base_graph([l_path()]), [{"id": 7, "name": "Lab", "x": 3, "y": 0.4}])
    assert {"node": "R7", "name": "Lab"} in nav["targets"] and navgraph.validate(nav) and warn == []
def test_far_room_is_connected_but_warned():           # ruangan 3 m dari jalur -> warn memuat "Lab" dan "1.5"
def test_route_cases_match_the_shared_file():
    cases = json.loads(Path("tests/fixtures/route_cases.json").read_text(encoding="utf-8"))
    for c in cases["routes"]:
        r = plan_route(c["graph"], tuple(c["from"]), c["target"])
        if c["expect"].get("unreachable"): assert r is None, c["name"]
        else: assert r["nodes"] == c["expect"]["nodes"] and abs(r["length_m"] - c["expect"]["length_m"]) < 1e-3, c["name"]
    for a in cases["arrivals"]:
        assert arrived(tuple(a["user"]), tuple(a["target"])) == a["expect"]
```

Isi `route_cases.json` minimal: graf L (P01 (0,0), P02 (4,0), P03 (4,3)) dari (0,1) ke P03 → nodes `["P01","P02","P03"]`; graf yang sama ke simpul pulau P04 (10,10) tanpa sisi → unreachable; graf persegi dengan diagonal satu sisi lebih pendek; arrivals `(0.99,0)→(0,0)` true, `(1.0,0)→(0,0)` false. Panjang yang diharapkan dihitung tangan dan ditulis di berkas (jarak dari `from` ke proyeksi ikut dihitung, sama dengan `Route` C#).

- [ ] **Step 2: Jalankan, pastikan gagal.** Expected: `ImportError` untuk `apply_edits`.
- [ ] **Step 3: Implementasi** fungsi-fungsi di Interfaces. `plan_route` adalah port langsung `NavGraph.TryProject` dan `NavGraph.Plan` (c93cd08): simpul awal semu di titik proyeksi bertetangga dengan kedua ujung sisi terproyeksi.
- [ ] **Step 4: Jalankan, pastikan lolos.** Expected: semua PASS.
- [ ] **Step 5: Commit (titik commit yang diusulkan)**

```bash
git add server/routegraph.py tests/test_routegraph.py tests/fixtures/route_cases.json
git commit -m "feat(server): rooms, coordinate-based route edits and the app's route rule"
```

### Task 3: Tabel, API area, dan `/navgraph` dari graf terbit

**Files:**
- Modify: `server/db.py` (tabel `Room`, `RouteEdit`, `PublishedGraph`)
- Create: `server/migrations/versions/0003_area_routes.py`
- Create: `server/area_api.py`, `server/floorplan.py` (baru berisi `to_building`); Modify: `server/app.py` (sertakan router)
- Modify: `server/navgraph.py` (`get_navgraph` membaca `PublishedGraph` lebih dulu bila `DATABASE_URL` ada)
- Test: `tests/test_area_api.py`, `tests/test_navgraph.py`, `tests/test_floorplan.py`

**Interfaces:**
- Consumes: `build_base_graph`, `split_sequences`, `apply_edits`, `compose_navgraph`, `plan_route` (Task 1, 2); `app.state.localizer` (`.model` pycolmap, `.align`), `app.state.area_id`.
- Produces:
  - `server/floorplan.py` dengan `to_building(xyz: np.ndarray, meter_from_model: dict) -> np.ndarray`, dipindah dari `server/mapcloud.py` worktree `D:/wt/navcontent` beserta dua tesnya (termasuk pembanding `pycolmap.Sim3d`) ke `tests/test_floorplan.py`.
  - `Room(id: int pk, area_id: str fk, name: str, x: float, y: float, created_by: str, created_at: datetime)`, unik `(area_id, name)`.
  - `RouteEdit(id: int pk, area_id, kind: str, ax, ay, bx, by: float, created_by, created_at)`.
  - `PublishedGraph(area_id: str pk fk, graph: dict JSON, published_by: str, published_at: datetime)`.
  - Endpoint (JSON): `GET /api/areas/{area_id}/graph` → `{"base": navgraph-tanpa-target, "edits": [Edit], "rooms": [Room], "draft": navgraph, "warnings": [str], "unmatched_edits": [int], "published_at": str | None}`; `POST /api/areas/{area_id}/rooms` `{name, x, y}` → Room (201); `PATCH /api/areas/{area_id}/rooms/{room_id}` `{name?, x?, y?}`; `DELETE .../rooms/{room_id}`; `POST /api/areas/{area_id}/edits` `{kind, a, b}` → Edit (201); `DELETE .../edits/{edit_id}`; `POST /api/areas/{area_id}/route` `{"from": [x, y], "room_id": int}` → hasil `plan_route` atau `{"status": "unreachable"}`; `POST /api/areas/{area_id}/publish-graph` → `{"published_at", "warnings"}`.
  - Graf dasar dihitung dari pusat kamera `localizer.model.images` (urut nama) diubah ke G, disimpan di cache memori per (area, stempel `align.json`).
  - Galat: 409 `"area not served"` bila `area_id` bukan area yang dilayani; 409 `"map version not aligned"` bila `align` None; 403 untuk tulis oleh bukan admin; 409 nama ruangan ganda; 422 `kind` tidak dikenal.

- [ ] **Step 1: Tulis tes yang gagal** (fixture meniru `tests/test_maps_api.py`: sqlite, `EUTOPOS_DEV_NO_AUTH=1`, localizer palsu `SimpleNamespace(model=..., align={"meter_from_model": identitas})` dengan `images` berisi jalur L sintetis)

```python
def test_graph_is_built_from_the_camera_path(client):      # GET graph -> base punya >= 3 simpul, draft lolos navgraph.validate
def test_room_crud_and_duplicate_name(client):             # POST Lab 201, POST Lab lagi 409, PATCH nama, DELETE 204
def test_writes_need_admin(client):                         # override current_user ke "tamu@x.id": POST rooms/edits/publish -> 403, tabel kosong
def test_route_uses_the_draft_graph(client):               # POST route ke ruangan -> points diawali "from", length_m > 0
def test_publish_then_navgraph_serves_it(client):           # publish -> GET /navgraph = draft (targets memuat ruangan)
def test_publish_without_alignment_is_refused(client):     # align None -> 409, PublishedGraph tidak berubah
def test_other_area_is_409(client):                         # GET /api/areas/lain/graph -> 409 "area not served"
```

Di `tests/test_navgraph.py`: `test_navgraph_prefers_the_published_graph` (berkas dan baris DB berbeda, jawaban = baris DB) dan `test_navgraph_falls_back_to_the_file_without_database`.

- [ ] **Step 2: Jalankan, pastikan gagal.** Expected: `ImportError: cannot import name 'area_api'`.
- [ ] **Step 3: Implementasi** tabel, migrasi `0003` (meniru `0002_map_job.py`), router, dan perubahan `get_navgraph`. Menerbitkan memakai `compose_navgraph` dan `navgraph.validate`; gagal validasi = 409 dengan alasannya.
- [ ] **Step 4: Jalankan seluruh suite.** Run: `python -m pytest -q` (dengan `.venv` di PATH). Expected: semua PASS, termasuk `test_migration_cli_runs_like_the_container`.
- [ ] **Step 5: Commit (titik commit yang diusulkan)**

```bash
git add server/db.py server/migrations/versions/0003_area_routes.py server/area_api.py server/floorplan.py server/app.py server/navgraph.py tests/test_area_api.py tests/test_navgraph.py tests/test_floorplan.py
git commit -m "feat(server): rooms, route edits, route test and graph publishing for the dashboard"
```

### Task 4: Peta 2D, foto asli, dan .glb

**Files:**
- Create: `server/thumbs.py`; Modify: `server/floorplan.py` (tambah render dan glb)
- Modify: `server/area_api.py` (endpoint peta, foto, glb), `server/worker.py` (panggil `make_thumbs` setelah `make_preview`), `server/manage.py` (subperintah `thumbs`)
- Test: `tests/test_floorplan.py`, `tests/test_thumbs.py`, `tests/test_area_api.py`

**Interfaces:**
- Produces:
  - `render_floorplan(points_g: np.ndarray, cams_g: np.ndarray, res_m: float = 0.03, z_min: float = 0.2, z_max: float = 2.2) -> tuple[bytes, dict]` → PNG dan `{"origin_x", "origin_y", "res_m", "width", "height"}`; piksel (px, py) dari (x, y): `px = (x - origin_x) / res_m`, `py = height - 1 - (y - origin_y) / res_m`.
  - `points_glb(points_g: np.ndarray, colors: np.ndarray) -> bytes` (primitif glTF mode 0 POINTS, atribut `POSITION` dan `COLOR_0`, G ke glTF: `(x, z, -y)`).
  - `make_thumbs(mapping_dir: Path, out_dir: Path, width: int = 480) -> int` (JPEG kualitas 80, tanpa EXIF, nama sama dengan frame; mengembalikan jumlah).
  - Endpoint: `GET /api/areas/{area_id}/plan` → meta + `"trajectory": [[x, y], ...]`; `GET .../plan.png`; `GET .../photo?x=&y=` → JPEG dengan header `X-Heading-Deg` (yaw kamera di G) atau 404 `"photo not available"`; `GET .../cloud.glb`.
  - `python -m server.manage thumbs [--version ID]` → membuat foto kecil untuk versi yang belum punya, dari `/data/jobs/<job_id>/dataset/mapping`.

- [ ] **Step 1: Tulis tes yang gagal**

```python
def test_floorplan_marks_occupied_cells_and_keeps_the_pixel_rule():
    png, meta = render_floorplan(np.array([[1.0, 2.0, 1.0]]), np.array([[0, 0, 1.3]]))
    img = Image.open(io.BytesIO(png)); px = round((1 - meta["origin_x"]) / meta["res_m"]); py = meta["height"] - 1 - round((2 - meta["origin_y"]) / meta["res_m"])
    assert img.convert("L").getpixel((px, py)) < 128
def test_floor_points_are_ignored():                 # titik z = 0,05 tidak menggelapkan piksel
def test_glb_header_and_point_count():               # magic b"glTF", versi 2, accessor POSITION count = jumlah titik
def test_thumbs_are_small_and_stripped(tmp_path):    # 2 JPEG 1920 px ber-EXIF -> 2 berkas lebar 480, tanpa EXIF
def test_photo_returns_the_nearest_frame(client):    # dua kamera, foto kecil di <map_dir>/thumbs -> klik dekat kamera B = berkas B, ada X-Heading-Deg
def test_photo_without_thumbs_is_404(client):
```

- [ ] **Step 2: Jalankan, pastikan gagal.** Expected: `ImportError: cannot import name 'render_floorplan'`.
- [ ] **Step 3: Implementasi.** Kerapatan per sel dengan skala log (seperti gambar uji 21 Okt), titik di luar persentil 1 sampai 99 dipotong supaya pencilan tidak membesarkan kanvas. Cache PNG dan glb di memori per (area, stempel `align.json`).
- [ ] **Step 4: Jalankan seluruh suite dan lint.** Expected: PASS, ruff bersih.
- [ ] **Step 5: Commit (titik commit yang diusulkan)**

```bash
git add server/floorplan.py server/thumbs.py server/area_api.py server/worker.py server/manage.py tests/test_floorplan.py tests/test_thumbs.py tests/test_area_api.py
git commit -m "feat(server): floor plan, scan photos and point cloud glb for the area page"
```

### Task 5: Halaman area di dashboard

**Files:**
- Modify: `web/lib/api.ts` (tipe `AreaGraph`, `Room`, `RouteEdit`, `PlanMeta`, `RouteResult`; fungsi di objek `api`)
- Create: `web/app/area/page.tsx`, `web/components/AreaMap.tsx`
- Modify: `web/app/maps/page.tsx` (tautan "Edit routes" ke `/area?id=<area_id>` untuk area yang dilayani)

**Interfaces:**
- Consumes: endpoint Task 3 dan 4; `api.me()` untuk `is_admin`.
- Produces: `AreaMap` props `{plan: PlanMeta, imageUrl: string, graph: AreaGraph, mode: "view" | "rooms" | "routes" | "test", onPick(x: number, y: number): void, route?: RouteResult}`; konversi koordinat memakai rumus piksel Task 4.

- [ ] **Step 1: Halaman dengan lima mode** sesuai spesifikasi bagian 6: View (klik = foto asli + arah hadap), Rooms (klik tambah, seret geser, panel ganti nama dan hapus), Routes (klik sisi untuk hapus, klik dua titik untuk tambah, seret simpul untuk geser, daftar editan tak cocok), Test (klik titik awal, pilih ruangan, gambar jalur, tombol Simulate yang menggerakkan penanda 1 m/s sampai jarak < 1,0, panjang rute dengan label "Scale not calibrated"), Publish (admin; ringkasan dan peringatan dari `GET graph`). Kontrol tulis disembunyikan untuk bukan admin. Lapisan digambar dengan SVG di atas `<img>` peta, tanpa pustaka peta.
- [ ] **Step 2: Build.** Run: `npm run build` di `web/`. Expected: build sukses tanpa galat TypeScript.
- [ ] **Step 3: Commit (titik commit yang diusulkan)**

```bash
git add web/lib/api.ts web/app/area/page.tsx web/components/AreaMap.tsx web/app/maps/page.tsx
git commit -m "feat(web): area page to place rooms, fix routes and test them on the floor plan"
```

### Task 6: Kasus aturan rute yang sama di aplikasi ponsel

Repo `eutopos-mobile`, cabang baru dari `c93cd08` (berisi `NavGraph` dan `Route.NodeIds`).

**Files:**
- Create: `Assets/Eutopos/Tests/EditMode/route_cases.json` (salinan `eutopos-vps/tests/fixtures/route_cases.json`, baris pertama `"_source": "copy of eutopos-vps tests/fixtures/route_cases.json"`)
- Create: `Assets/Eutopos/Tests/EditMode/RouteCasesTests.cs`

- [ ] **Step 1: Tulis tes** `RouteCasesMatchTheServer`: baca berkas lewat `Path.Combine(Application.dataPath, "Eutopos/Tests/EditMode/route_cases.json")`, untuk setiap kasus `NavGraph.Parse(graph)`, `Plan(from, target)`, bandingkan `NodeIds` dan `LengthM` (toleransi 1e-3) atau null untuk unreachable; untuk arrivals bandingkan `NavGraph.Arrived`.
- [ ] **Step 2: Jalankan.** Run: perintah tes EditMode di rencana `eutopos-mobile/docs/plans/2026-10-15-mvp-navigasi.md` Task 1 Step 6 (dengan `Start-Process -Wait`). Expected: `result="Passed"`. Bila ada kasus gagal, perbedaan aturan Python dan C# yang harus dibetulkan di Python (C# adalah aturan yang sudah teruji di lapangan).
- [ ] **Step 3: Commit (titik commit yang diusulkan)**

```bash
git add Assets/Eutopos/Tests/EditMode/route_cases.json Assets/Eutopos/Tests/EditMode/RouteCasesTests.cs
git commit -m "test: run the server's shared route cases against NavGraph"
```

### Task 7: Demo di PC Lab dan ponsel (manual)

Prasyarat: PR Task 1 sampai 5 merged atas perintah Bagus, autodeploy selesai, tidak ada uji lapangan atau pembangunan peta berjalan.

- [ ] **Step 1:** Dengan izin Bagus: `docker compose exec -T worker python -m server.manage thumbs` di PC Lab. Expected: pesan jumlah foto untuk versi hcm-lantai-10.
- [ ] **Step 2:** Buka `/area?id=hcm-lantai-10`. Expected: peta 2D tampil, klik di jalur menampilkan foto asli, graf otomatis terlihat di lorong.
- [ ] **Step 3:** Taruh minimal satu ruangan, uji rute dari titik awal ke ruangan itu, perbaiki sambungan bila perlu, Publish.
- [ ] **Step 4:** Di TECNO KL7 (APK yang sudah terpasang, tidak dibangun ulang): Lokalisasi, pilih ruangan itu, ikuti rute. Expected: rute tampil dan banner Sampai muncul. Catat hasilnya di `pa-academic/notes/` untuk sempro.
