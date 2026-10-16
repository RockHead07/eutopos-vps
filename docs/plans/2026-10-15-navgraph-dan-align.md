# GET /navgraph dan manage align: Rencana Implementasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Layanan eutopos menyajikan graf navigasi per area (`GET /navgraph`) dan punya perintah resmi untuk memasang `align.json` dan `navgraph.json` dengan validasi, supaya klien `eutopos-mobile` bisa menerima posisi dalam meter dan menghitung rute.

**Architecture:** Modul baru `server/navgraph.py` (validasi graf + router `GET /navgraph`) dan `server/alignment.py` (validasi `align.json` + pemasangan atomik kedua berkas). `server/manage.py` mendapat subperintah `align`. Graf disimpan per area di `<maps>/<area_id>/navgraph.json`; `align.json` per versi peta di `<folder versi>/kp<max_kp>-r<resize>/align.json`.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, pytest, ruff (semua sudah dipakai repo ini; tidak ada dependensi baru).

**Spec:** `D:\Dev\Projects\eutopos-mobile\docs\specs\2026-10-15-mvp-navigasi-design.md` bagian 7 dan 8 (repo `RockHead07/eutopos-mobile`).

## Global Constraints

- Tidak ada dependensi baru; ikuti `pyproject.toml` (Python >= 3.12, < 3.13; ruff line-length 100).
- Kerangka graf: `"frame": "building"`, `"units": "m"`, kerangka G (tangan kanan, x sepanjang lorong, y di kiri saat menghadap +x, z ke atas).
- `/navgraph` tanpa identitas pengguna, sama seperti `/localize`.
- `navgraph.json` per area (`<maps>/<area_id>/navgraph.json`), bukan per versi peta.
- `align.json` per versi peta (`<folder versi>/kp<EUTOPOS_MAX_KP>-r<EUTOPOS_RESIZE>/align.json`, bawaan `kp1024-r1024`).
- Pemeriksaan `align.json`: skala > 0, kuaternion berpanjang 1 (toleransi 1e-3), `reference_points` >= 4, `residual_median_m` ada.
- Berkas rusak ditolak sebelum ada yang disalin; tidak ada penyalinan sebagian.
- Koordinat gedung dan data lapangan tidak pernah di-commit (repo publik).
- Commit dan push hanya atas perintah eksplisit Bagus; langkah "Commit" di rencana ini adalah titik commit yang diusulkan. Tanpa atribusi AI di pesan commit atau PR.
- Teks untuk manusia tanpa em dash.

## Review Focus

1. `navgraph.json` di disk rusak setelah dipasang (disunting tangan): `/navgraph` harus menjawab 500 dengan pesan yang menyebut kesalahannya, bukan melayani graf rusak. Uji di Task 2.
2. `area_id` yang mengandung pemisah folder (`../x`): `graph_path` harus menolak, bukan membaca di luar folder peta. Uji di Task 1.
3. Layanan berjalan tanpa database (`EUTOPOS_MAP_DIR`, `area_id` None): `/navgraph` menjawab 503, bukan 500. Uji di Task 2.
4. `manage align` dengan `align.json` sah tetapi `navgraph.json` rusak: `align.json` juga tidak boleh tersalin. Uji di Task 3.
5. Angka JSON berupa boolean (`"x": true`) atau NaN lolos pemeriksaan `isinstance(..., float)`: harus ditolak. Uji di Task 1 dan Task 3.

---

### Task 1: Validasi graf navigasi

**Files:**
- Create: `server/navgraph.py`
- Test: `tests/test_navgraph.py`

**Interfaces:**
- Produces: `server.navgraph.validate(data: object) -> dict` (ValueError bila tidak sah), `server.navgraph.disconnected_nodes(data: dict) -> list[str]`, `server.navgraph.graph_path(root: Path, area_id: str) -> Path` (ValueError bila `area_id` tidak sah), `server.navgraph.maps_root() -> Path` (env `EUTOPOS_MAPS_ROOT`, bawaan `/maps`), konstanta `FILE_NAME = "navgraph.json"`.

- [ ] **Step 1: Tulis tes yang gagal**

```python
"""Graf navigasi per area (spesifikasi eutopos-mobile bagian 7 dan 8)."""

import copy
import math
from pathlib import Path

import pytest

from server import navgraph

GOOD = {
    "frame": "building",
    "units": "m",
    "nodes": [{"id": "P01", "x": 0.0, "y": 0.4}, {"id": "P02", "x": 1.5, "y": 1.6}],
    "edges": [["P01", "P02"]],
    "targets": [{"node": "P02", "name": "Pintu Lab"}],
}


def broken(path, value):
    g = copy.deepcopy(GOOD)
    obj = g
    for key in path[:-1]:
        obj = obj[key]
    obj[path[-1]] = value
    return g


def test_valid_graph_is_returned_unchanged():
    assert navgraph.validate(copy.deepcopy(GOOD)) == GOOD


@pytest.mark.parametrize(
    ("graph", "words"),
    [
        (broken(["frame"], "model"), "frame"),
        (broken(["units"], "cm"), "units"),
        (broken(["nodes"], []), "nodes"),
        (broken(["nodes", 1, "id"], "P01"), "ganda"),
        (broken(["nodes", 0, "x"], "1.0"), "bukan angka"),
        (broken(["nodes", 0, "x"], True), "bukan angka"),
        (broken(["nodes", 0, "y"], math.nan), "bukan angka"),
        (broken(["edges"], [["P01", "P99"]]), "P99"),
        (broken(["edges"], [["P01", "P01"]]), "dirinya"),
        (broken(["edges"], [["P01"]]), "pasangan"),
        (broken(["targets"], [{"node": "P99", "name": "x"}]), "target"),
        (broken(["targets"], [{"node": "P02", "name": ""}]), "target"),
        ("bukan objek", "objek"),
    ],
)
def test_invalid_graph_is_rejected_with_the_reason(graph, words):
    with pytest.raises(ValueError, match=words):
        navgraph.validate(graph)


def test_disconnected_nodes_are_listed():
    g = copy.deepcopy(GOOD)
    g["nodes"].append({"id": "P03", "x": 9.0, "y": 9.0})
    assert navgraph.disconnected_nodes(g) == ["P03"]
    assert navgraph.disconnected_nodes(GOOD) == []


@pytest.mark.parametrize("area", ["../etc", "a/b", "..", "", "."])
def test_graph_path_refuses_area_ids_that_leave_the_maps_folder(area):
    with pytest.raises(ValueError):
        navgraph.graph_path(Path("/maps"), area)


def test_graph_path_is_per_area(tmp_path):
    assert navgraph.graph_path(tmp_path, "floor10") == tmp_path / "floor10" / "navgraph.json"


def test_maps_root_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("EUTOPOS_MAPS_ROOT", str(tmp_path))
    assert navgraph.maps_root() == tmp_path
    monkeypatch.delenv("EUTOPOS_MAPS_ROOT")
    assert navgraph.maps_root() == Path("/maps")
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `uv run pytest tests/test_navgraph.py -v`
Expected: FAIL, `ImportError: cannot import name 'navgraph'`.

- [ ] **Step 3: Implementasi minimal**

```python
"""Graf navigasi per area untuk klien eutopos-mobile (spesifikasi bagian 7 dan 8).

Berkas <maps>/<area_id>/navgraph.json, kerangka gedung G (meter, tangan kanan, z ke atas):
    {"frame": "building", "units": "m",
     "nodes": [{"id": "P01", "x": 0.0, "y": 0.4}, ...],
     "edges": [["P01", "P02"], ...],
     "targets": [{"node": "P02", "name": "Pintu Lab"}, ...]}
Per area, bukan per versi peta: koordinat gedung tidak berubah saat peta dibangun ulang.
"""

import math
import os
from pathlib import Path

FILE_NAME = "navgraph.json"


def maps_root() -> Path:
    return Path(os.environ.get("EUTOPOS_MAPS_ROOT", "/maps"))


def graph_path(root: Path, area_id: str) -> Path:
    if not area_id or area_id in (".", "..") or Path(area_id).name != area_id:
        raise ValueError(f"area_id tidak sah: {area_id!r}")
    return root / area_id / FILE_NAME


def _number(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


def validate(data) -> dict:
    """Periksa isi navgraph dan kembalikan apa adanya. ValueError menyebut kesalahan pertama."""
    if not isinstance(data, dict):
        raise ValueError("navgraph harus objek JSON")
    if data.get("frame") != "building":
        raise ValueError('frame harus "building"')
    if data.get("units") != "m":
        raise ValueError('units harus "m"')
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("nodes kosong")
    ids = set()
    for n in nodes:
        if not isinstance(n, dict) or not isinstance(n.get("id"), str) or not n["id"]:
            raise ValueError(f"simpul tanpa id: {n!r}")
        if n["id"] in ids:
            raise ValueError(f"id simpul ganda: {n['id']}")
        for k in ("x", "y"):
            if not _number(n.get(k)):
                raise ValueError(f"simpul {n['id']}: {k} bukan angka")
        ids.add(n["id"])
    edges = data.get("edges")
    if not isinstance(edges, list):
        raise ValueError("edges harus daftar")
    for e in edges:
        if not (isinstance(e, list) and len(e) == 2 and all(isinstance(i, str) for i in e)):
            raise ValueError(f"sisi harus pasangan id: {e!r}")
        if e[0] == e[1]:
            raise ValueError(f"sisi ke dirinya sendiri: {e[0]}")
        for i in e:
            if i not in ids:
                raise ValueError(f"sisi merujuk simpul yang tidak ada: {i}")
    targets = data.get("targets")
    if not isinstance(targets, list):
        raise ValueError("targets harus daftar")
    for t in targets:
        ok = isinstance(t, dict) and t.get("node") in ids
        if not ok or not isinstance(t.get("name"), str) or not t["name"]:
            raise ValueError(f"target tidak sah: {t!r}")
    return data


def disconnected_nodes(data: dict) -> list[str]:
    """Simpul yang tidak terhubung ke simpul pertama (peringatan, bukan galat)."""
    adj = {n["id"]: set() for n in data["nodes"]}
    for a, b in data["edges"]:
        adj[a].add(b)
        adj[b].add(a)
    start = data["nodes"][0]["id"]
    seen, todo = {start}, [start]
    while todo:
        for nxt in adj[todo.pop()] - seen:
            seen.add(nxt)
            todo.append(nxt)
    return [n["id"] for n in data["nodes"] if n["id"] not in seen]
```

- [ ] **Step 4: Jalankan tes, pastikan lolos**

Run: `uv run pytest tests/test_navgraph.py -v && uv run ruff check server tests && uv run ruff format --check server tests`
Expected: semua PASS, ruff bersih.

- [ ] **Step 5: Commit (titik commit yang diusulkan)**

```bash
git add server/navgraph.py tests/test_navgraph.py
git commit -m "feat: validate per-area navigation graphs"
```

### Task 2: Endpoint GET /navgraph

**Files:**
- Modify: `server/navgraph.py` (tambah router di akhir berkas)
- Modify: `server/app.py` (import dan `include_router`, docstring modul)
- Test: `tests/test_navgraph.py` (tambah tes endpoint)

**Interfaces:**
- Consumes: `validate`, `graph_path`, `maps_root`, `FILE_NAME` dari Task 1; `request.app.state.area_id` dan `request.app.state.map_version` (diisi `lifespan` di `server/app.py`).
- Produces: `server.navgraph.router` (`APIRouter`), `GET /navgraph` -> `{"area_id": str, "map_version": int | None, "graph": dict}`; 503 bila `area_id` None, 404 bila berkas tidak ada, 500 bila berkas rusak.

- [ ] **Step 1: Tulis tes yang gagal** (tambahkan ke `tests/test_navgraph.py`)

Import baru (`json`, `FastAPI`, `TestClient`) diletakkan di blok import paling atas berkas, bukan di tengah (ruff I001/E402).

```python
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient


def client_for(tmp_path, monkeypatch, area="floor10", version=3):
    monkeypatch.setenv("EUTOPOS_MAPS_ROOT", str(tmp_path))
    app = FastAPI()
    app.include_router(navgraph.router)
    app.state.area_id, app.state.map_version = area, version
    return TestClient(app)


def write_graph(tmp_path, area, data):
    (tmp_path / area).mkdir(parents=True, exist_ok=True)
    (tmp_path / area / "navgraph.json").write_text(json.dumps(data), encoding="utf-8")


def test_navgraph_serves_the_active_area(tmp_path, monkeypatch):
    write_graph(tmp_path, "floor10", GOOD)
    r = client_for(tmp_path, monkeypatch).get("/navgraph")
    assert r.status_code == 200
    assert r.json() == {"area_id": "floor10", "map_version": 3, "graph": GOOD}


def test_navgraph_missing_file_is_404(tmp_path, monkeypatch):
    r = client_for(tmp_path, monkeypatch).get("/navgraph")
    assert r.status_code == 404 and "floor10" in r.json()["detail"]


def test_navgraph_without_active_map_is_503(tmp_path, monkeypatch):
    r = client_for(tmp_path, monkeypatch, area=None, version=None).get("/navgraph")
    assert r.status_code == 503


def test_navgraph_broken_file_is_500_with_reason(tmp_path, monkeypatch):
    write_graph(tmp_path, "floor10", broken(["edges"], [["P01", "P99"]]))
    r = client_for(tmp_path, monkeypatch).get("/navgraph")
    assert r.status_code == 500 and "P99" in r.json()["detail"]


def test_navgraph_not_json_is_500(tmp_path, monkeypatch):
    (tmp_path / "floor10").mkdir()
    (tmp_path / "floor10" / "navgraph.json").write_text("{bukan json", encoding="utf-8")
    assert client_for(tmp_path, monkeypatch).get("/navgraph").status_code == 500
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `uv run pytest tests/test_navgraph.py -v`
Expected: FAIL, `AttributeError: module 'server.navgraph' has no attribute 'router'`.

- [ ] **Step 3: Implementasi**

Tambahkan di `server/navgraph.py` (import di atas, router di akhir berkas):

```python
import json

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/navgraph")
def get_navgraph(request: Request) -> dict:
    """Graf navigasi area aktif. Tanpa identitas pengguna, sama seperti /localize."""
    st = request.app.state
    area_id = getattr(st, "area_id", None)
    if area_id is None:
        raise HTTPException(503, "no active map")
    path = graph_path(maps_root(), area_id)
    if not path.exists():
        raise HTTPException(404, f"no navgraph for area {area_id}")
    try:
        graph = validate(json.loads(path.read_text(encoding="utf-8")))
    except ValueError as e:  # json.JSONDecodeError juga ValueError
        raise HTTPException(500, f"navgraph.json invalid: {e}") from e
    return {"area_id": area_id, "map_version": getattr(st, "map_version", None), "graph": graph}
```

Di `server/app.py`, ubah baris import dan tambahkan router setelah router lain:

```python
from server import active_map, maps_api, navgraph, uploads
```

```python
app.include_router(uploads.router)
app.include_router(maps_api.router)
app.include_router(navgraph.router)
```

Di docstring modul `server/app.py`, baris pertama menjadi:

```python
"""Layanan lokalisasi eutopos: POST /localize, GET /health, dan GET /navgraph.
```

dan tambahkan ke daftar variabel lingkungan:

```text
    EUTOPOS_MAPS_ROOT        folder akar peta untuk navgraph.json per area (bawaan /maps)
```

- [ ] **Step 4: Jalankan tes, pastikan lolos**

Run: `uv run pytest tests/test_navgraph.py tests/test_server.py -v && uv run ruff check server tests && uv run ruff format --check server tests`
Expected: PASS (tes `test_server.py` yang butuh peta tetap SKIPPED seperti sebelumnya).

- [ ] **Step 5: Commit (titik commit yang diusulkan)**

```bash
git add server/navgraph.py server/app.py tests/test_navgraph.py
git commit -m "feat: serve the active area's navigation graph at GET /navgraph"
```

### Task 3: Validasi align.json dan pemasangan atomik

**Files:**
- Create: `server/alignment.py`
- Test: `tests/test_alignment.py`

**Interfaces:**
- Consumes: `server.navgraph.validate`, `server.navgraph.disconnected_nodes`, `server.navgraph.FILE_NAME` (Task 1).
- Produces: `server.alignment.validate_align(data: object) -> dict` (ValueError), `server.alignment.install(map_dir: Path, run_name: str, area_dir: Path, align_src: Path | None, navgraph_src: Path | None) -> tuple[list[Path], list[str]]` mengembalikan (berkas yang ditulis, peringatan); ValueError bila tidak ada masukan, berkas rusak, atau folder run tidak ada.

- [ ] **Step 1: Tulis tes yang gagal**

```python
"""Pemasangan align.json dan navgraph.json (spesifikasi eutopos-mobile bagian 8b)."""

import copy
import json
import math

import pytest

from server import alignment

GOOD_GRAPH = {
    "frame": "building",
    "units": "m",
    "nodes": [{"id": "P01", "x": 0.0, "y": 0.4}, {"id": "P02", "x": 1.5, "y": 1.6}],
    "edges": [["P01", "P02"]],
    "targets": [{"node": "P02", "name": "Pintu Lab"}],
}

GOOD_ALIGN = {
    "meter_from_model": {
        "scale": 0.25,
        "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
        "translation": [1.0, 2.0, 0.5],
    },
    "phone_height_m": 1.3,
    "reference_points": 10,
    "residual_median_m": 0.12,
}


def changed(key_path, value):
    d = copy.deepcopy(GOOD_ALIGN)
    obj = d
    for k in key_path[:-1]:
        obj = obj[k]
    obj[key_path[-1]] = value
    return d


def test_valid_align_is_accepted():
    assert alignment.validate_align(copy.deepcopy(GOOD_ALIGN)) == GOOD_ALIGN


@pytest.mark.parametrize(
    "data",
    [
        changed(["meter_from_model", "scale"], 0),
        changed(["meter_from_model", "scale"], True),
        changed(["meter_from_model", "rotation_xyzw"], [0.0, 0.0, 0.0, 2.0]),
        changed(["meter_from_model", "rotation_xyzw"], [0.0, 0.0, 1.0]),
        changed(["meter_from_model", "translation"], [1.0, math.nan, 0.0]),
        changed(["reference_points"], 3),
        changed(["reference_points"], True),
        changed(["residual_median_m"], None),
        {"tanpa": "meter_from_model"},
    ],
)
def test_invalid_align_is_rejected(data):
    with pytest.raises(ValueError):
        alignment.validate_align(data)


def layout(tmp_path):
    map_dir = tmp_path / "maps" / "floor10" / "job-7"
    (map_dir / "kp1024-r1024").mkdir(parents=True)
    src = tmp_path / "src"
    src.mkdir()
    (src / "align.json").write_text(json.dumps(GOOD_ALIGN), encoding="utf-8")
    (src / "navgraph.json").write_text(json.dumps(GOOD_GRAPH), encoding="utf-8")
    return map_dir, tmp_path / "maps" / "floor10", src


def test_install_writes_both_files_where_the_service_reads_them(tmp_path):
    map_dir, area_dir, src = layout(tmp_path)
    written, warnings = alignment.install(
        map_dir, "kp1024-r1024", area_dir, src / "align.json", src / "navgraph.json"
    )
    assert written == [map_dir / "kp1024-r1024" / "align.json", area_dir / "navgraph.json"]
    assert json.loads(written[0].read_text(encoding="utf-8")) == GOOD_ALIGN
    assert json.loads(written[1].read_text(encoding="utf-8")) == GOOD_GRAPH
    assert warnings == []
    assert not list(tmp_path.rglob("*.tmp"))


def test_broken_navgraph_stops_the_align_copy_too(tmp_path):
    map_dir, area_dir, src = layout(tmp_path)
    bad = copy.deepcopy(GOOD_GRAPH)
    bad["edges"] = [["P01", "P99"]]
    (src / "navgraph.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="P99"):
        alignment.install(
            map_dir, "kp1024-r1024", area_dir, src / "align.json", src / "navgraph.json"
        )
    assert not (map_dir / "kp1024-r1024" / "align.json").exists()


def test_disconnected_graph_installs_with_a_warning(tmp_path):
    map_dir, area_dir, src = layout(tmp_path)
    g = copy.deepcopy(GOOD_GRAPH)
    g["nodes"].append({"id": "P03", "x": 9.0, "y": 9.0})
    (src / "navgraph.json").write_text(json.dumps(g), encoding="utf-8")
    _, warnings = alignment.install(map_dir, "kp1024-r1024", area_dir, None, src / "navgraph.json")
    assert any("P03" in w for w in warnings)


def test_missing_run_folder_is_an_error(tmp_path):
    map_dir, area_dir, src = layout(tmp_path)
    with pytest.raises(ValueError, match="kp2048-r1024"):
        alignment.install(map_dir, "kp2048-r1024", area_dir, src / "align.json", None)


def test_nothing_to_install_is_an_error(tmp_path):
    map_dir, area_dir, _ = layout(tmp_path)
    with pytest.raises(ValueError):
        alignment.install(map_dir, "kp1024-r1024", area_dir, None, None)
```

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `uv run pytest tests/test_alignment.py -v`
Expected: FAIL, `ImportError: cannot import name 'alignment'`.

- [ ] **Step 3: Implementasi**

```python
"""Pasang align.json (per versi peta) dan navgraph.json (per area) dengan pemeriksaan.

align.json ditulis spike/eval_meter.py di folder hasil uji, tetapi layanan membacanya dari folder
peta aktif (server/localizer.py). Semua berkas diperiksa dulu; berkas rusak berarti tidak ada yang
disalin. Penulisan lewat berkas sementara lalu os.replace, jadi layanan tidak pernah membaca setengah.
"""

import json
import math
import os
from pathlib import Path

from server import navgraph


def _number(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


def validate_align(data) -> dict:
    m = data.get("meter_from_model") if isinstance(data, dict) else None
    if not isinstance(m, dict):
        raise ValueError("meter_from_model tidak ada")
    scale, q, t = m.get("scale"), m.get("rotation_xyzw"), m.get("translation")
    if not _number(scale) or scale <= 0:
        raise ValueError("scale harus angka positif")
    if not (isinstance(q, list) and len(q) == 4 and all(_number(v) for v in q)):
        raise ValueError("rotation_xyzw harus 4 angka")
    if abs(math.hypot(*q) - 1.0) > 1e-3:
        raise ValueError("rotation_xyzw harus kuaternion satuan")
    if not (isinstance(t, list) and len(t) == 3 and all(_number(v) for v in t)):
        raise ValueError("translation harus 3 angka")
    rp = data.get("reference_points")
    if not isinstance(rp, int) or isinstance(rp, bool) or rp < 4:
        raise ValueError("reference_points harus bilangan bulat >= 4")
    if not _number(data.get("residual_median_m")):
        raise ValueError("residual_median_m tidak ada")
    return data


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{path}: {e}") from e


def _write_atomic(dst: Path, data: dict) -> None:
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, dst)


def install(
    map_dir: Path,
    run_name: str,
    area_dir: Path,
    align_src: Path | None,
    navgraph_src: Path | None,
) -> tuple[list[Path], list[str]]:
    if align_src is None and navgraph_src is None:
        raise ValueError("tidak ada yang dipasang: beri --align dan/atau --navgraph")
    run_dir = map_dir / run_name
    plan, warnings = [], []
    if align_src is not None:
        if not run_dir.is_dir():
            raise ValueError(f"folder run tidak ada: {run_dir}")
        plan.append((run_dir / "align.json", validate_align(_read(align_src))))
    if navgraph_src is not None:
        graph = navgraph.validate(_read(navgraph_src))
        if lost := navgraph.disconnected_nodes(graph):
            warnings.append(f"simpul tidak terhubung ke {graph['nodes'][0]['id']}: {', '.join(lost)}")
        plan.append((area_dir / navgraph.FILE_NAME, graph))
    area_dir.mkdir(parents=True, exist_ok=True)
    for dst, data in plan:  # baru menulis setelah semua masukan lolos pemeriksaan
        _write_atomic(dst, data)
    return [dst for dst, _ in plan], warnings
```

- [ ] **Step 4: Jalankan tes, pastikan lolos**

Run: `uv run pytest tests/test_alignment.py -v && uv run ruff check server tests && uv run ruff format --check server tests`
Expected: PASS, ruff bersih.

- [ ] **Step 5: Commit (titik commit yang diusulkan)**

```bash
git add server/alignment.py tests/test_alignment.py
git commit -m "feat: validate and atomically install align.json and navgraph.json"
```

### Task 4: Subperintah `manage align` dan dokumentasi

**Files:**
- Modify: `server/manage.py` (parser `align` dan cabang perintahnya; docstring)
- Modify: `docs/design-notes.md` bagian 6 (kontrak API)
- Modify: `deploy/README.md` (subbagian baru setelah bagian penerbitan peta)
- Test: `tests/test_alignment.py` (tes CLI)

**Interfaces:**
- Consumes: `server.alignment.install` (Task 3), `server.db.MapVersion`, `server.worker.MAPS`.
- Produces: `python -m server.manage align --version <id> [--align <path>] [--navgraph <path>]`.

- [ ] **Step 1: Tulis tes yang gagal** (tambahkan ke `tests/test_alignment.py`)

Import baru (`Session`, `SQLModel`, `create_engine`, `manage`, `register`) diletakkan di blok import paling atas berkas.

```python
from sqlmodel import Session, SQLModel, create_engine

from server import manage
from server.db import register


def test_cli_installs_for_a_registered_version(tmp_path, monkeypatch, capsys):
    map_dir, area_dir, src = layout(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        vid = register(s, "floor10", "Lantai 10", str(map_dir)).id
    monkeypatch.setattr(manage, "engine_from_env", lambda: engine)
    monkeypatch.setattr(manage, "MAPS", tmp_path / "maps")
    monkeypatch.setattr(
        "sys.argv",
        ["manage", "align", "--version", str(vid), "--align", str(src / "align.json"),
         "--navgraph", str(src / "navgraph.json")],
    )
    manage.main()
    out = capsys.readouterr().out
    assert (map_dir / "kp1024-r1024" / "align.json").exists()
    assert (area_dir / "navgraph.json").exists()
    assert "terbitkan ulang" in out


def test_cli_unknown_version_exits_with_message(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(manage, "engine_from_env", lambda: engine)
    monkeypatch.setattr("sys.argv", ["manage", "align", "--version", "99", "--align", "x.json"])
    with pytest.raises(SystemExit, match="99"):
        manage.main()
```

Catatan: sesuaikan `layout()` agar folder versi yang didaftarkan sama dengan `map_dir` (sudah demikian). Bila `register` di `server/db.py` memerlukan argumen lain, baca tanda tangannya dulu dan ikuti persis.

- [ ] **Step 2: Jalankan tes, pastikan gagal**

Run: `uv run pytest tests/test_alignment.py -v -k cli`
Expected: FAIL, `argparse` menolak pilihan `align` (`invalid choice: 'align'`).

- [ ] **Step 3: Implementasi**

Di `server/manage.py`, import:

```python
from server import alignment, jobs
```

Tambahkan parser setelah parser `previews`:

```python
    al = sub.add_parser(
        "align", help="pasang align.json (versi peta) dan/atau navgraph.json (area) yang sudah diukur"
    )
    al.add_argument("--version", type=int, required=True, help="id versi peta (lihat 'list')")
    al.add_argument("--align", type=Path, help="align.json dari spike/eval_meter.py")
    al.add_argument("--navgraph", type=Path, help="navgraph.json untuk area versi itu")
```

Tambahkan cabang sebelum `else:` terakhir:

```python
        elif a.cmd == "align":
            v = s.get(MapVersion, a.version)
            if v is None:
                raise SystemExit(f"versi peta id {a.version} tidak ada")
            run_name = (
                f"kp{int(os.environ.get('EUTOPOS_MAX_KP', 1024))}"
                f"-r{int(os.environ.get('EUTOPOS_RESIZE', 1024))}"
            )
            try:
                written, warnings = alignment.install(
                    Path(v.path), run_name, MAPS / v.area_id, a.align, a.navgraph
                )
            except ValueError as e:
                raise SystemExit(f"tidak ada yang dipasang: {e}") from e
            for w in warnings:
                print(f"PERINGATAN: {w}")
            for p in written:
                print(f"dipasang: {p}")
            if a.align:
                print(
                    f"Layanan membaca align.json saat memuat peta: terbitkan ulang versi id {v.id} "
                    "dari dashboard, atau 'docker compose restart api'."
                )
```

Tambahkan contoh ke docstring `server/manage.py`:

```text
    python -m server.manage align --version 7 --align /data/eval/align.json \
        --navgraph /data/eval/navgraph.json   # jalankan di container worker (/maps bisa ditulis)
```

Di `docs/design-notes.md` bagian 6, tambahkan setelah blok `GET /health`:

```text
GET /navgraph
  keluaran: area_id, map_version, graph (isi navgraph.json area aktif, kerangka gedung G, meter)
  404 kalau area belum punya navgraph.json, 503 kalau belum ada peta aktif,
  500 kalau berkasnya rusak (pesan menyebut kesalahannya)
```

Di `deploy/README.md`, tambahkan subbagian setelah bagian penerbitan peta:

```markdown
### Menyelaraskan peta ke meter dan memasang graf navigasi

Setelah titik acuan diukur dan `spike/eval_meter.py` menghasilkan `align.json`, serta
`navgraph.json` ditulis dari lembar lapangan, pasang keduanya dari container `worker`
(di container `api`, `/maps` hanya-baca):

    docker compose exec worker python -m server.manage align --version <id> \
        --align /data/eval/align.json --navgraph /data/eval/navgraph.json

Berkas rusak ditolak dan tidak ada yang disalin. `align.json` terikat pada versi peta itu: peta
yang dibangun ulang kembali "belum diselaraskan". Setelah memasang `align.json`, terbitkan ulang
versi itu dari dashboard supaya layanan memuatnya. `navgraph.json` dibaca langsung tiap
permintaan `GET /navgraph`. Koordinat titik acuan dan graf tidak di-commit.
```

- [ ] **Step 4: Jalankan semua tes, pastikan lolos**

Run: `uv run pytest tests -q && uv run ruff check server tests && uv run ruff format --check server tests`
Expected: PASS (di Windows, `tests/test_db.py::test_migration_cli_runs_like_the_container` sudah gagal sebelum perubahan ini; CI di Docker yang menentukan).

- [ ] **Step 5: Commit (titik commit yang diusulkan)**

```bash
git add server/manage.py tests/test_alignment.py docs/design-notes.md deploy/README.md
git commit -m "feat: manage align installs alignment and navigation graph files"
```
