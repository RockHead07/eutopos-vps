# Viewer 3D: pandangan awal dari kamera latihan (Fase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Viewer `/splat/` dibuka langsung dari pose salah satu foto latihan (bukan titik tetap sembarang), bisa melompat antar pandangan latihan, model tanpa penyelarasan berdiri tegak, dan panel Properties versi menampilkan ringkasan hasil 3D.

**Architecture:** Model splat dilatih dengan `--no-normalize-world-space`, jadi kerangkanya sama dengan model SfM (`<versi>/kp1024-r1024/sfm`). Server membaca pose kamera SfM dan mengirimkannya dalam kerangka model lewat endpoint baru; viewer mengubahnya ke dunia PlayCanvas dengan matriks dunia entitas splat, sehingga berlaku sama untuk versi yang selaras maupun tidak. Ringkasan 3D diturunkan dari `SplatJob.summary` yang sudah tersimpan, bukan dari berkas baru.

**Tech Stack:** FastAPI + SQLModel + pycolmap 4.2.1 + numpy (server), Next.js 16 + PlayCanvas 2.23.3 + TypeScript 5.9 (web), pytest, `node --test` (type stripping bawaan Node 24).

**Spec:** `docs/plans/2026-11-17-roadmap-lanjutan.md` bagian "Fase 1: Polesan viewer". Konteks pipeline: `docs/specs/2026-11-09-splat-pipeline-design.md`.

## Untuk agent pelaksana (baca dulu)

- **Worktree sudah disiapkan Claude:** `D:\wt\viewer-start`, cabang `feat/viewer-start-view` dari `origin/main` (`412b429`). Kerjakan hanya di sana. Jangan `git fetch`, jangan membuat cabang atau worktree lain.
- **Dependensi sudah terpasang, tidak perlu jaringan:** `web/node_modules` sudah ada (`npm ci`). Paket berat (numpy, pycolmap, h5py) tidak ada di `uv.lock`, jadi semua perintah Python memakai venv checkout utama tanpa sinkronisasi. Di PowerShell, jalankan sekali per sesi terminal:
  `$env:UV_PROJECT_ENVIRONMENT='D:\Dev\Projects\eutopos-vps\.venv'`
  lalu ganti setiap `uv run` di rencana ini dengan `uv run --no-sync` (contoh: `uv run --no-sync pytest tests/test_splat_views.py -v`). Garis dasar sebelum perubahan: `uv run --no-sync pytest tests/test_maps_api.py tests/test_splat_placement.py tests/test_area_api.py -q` memberi `87 passed`.
- **Jangan commit, push, atau membuat PR.** Langkah "Commit" di bawah diganti: berhenti, tampilkan `git status` dan `git diff --stat`. Bagus yang memerintahkan commit setelah Claude memverifikasi.
- Jangan menyentuh production, PC lab, SSH, atau Docker. Semua uji lokal.
- Jangan menambah dependensi baru (npm maupun Python).
- Laporan akhir wajib memuat keluaran mentah setiap perintah uji, bukan ringkasan. Hasil yang tidak dijalankan ditulis "tidak dijalankan".

## Global Constraints

- Istilah teknis tetap bahasa Inggris (frame, pose, view, Gaussian, PSNR); teks UI lewat `web/lib/i18n/en.ts` dan `web/lib/i18n/id.ts`, tidak ada string UI tertanam.
- Endpoint baru wajib memakai pola keamanan jalur yang ada: jalur hasil `resolve()` harus `is_relative_to(MAPS_ROOT.resolve())`.
- `cam=` di URL selalu menang atas pandangan awal otomatis.
- Versi yang **selaras** tetap memakai `placement` server apa adanya; rotasi tegak hanya untuk versi **tidak selaras**.
- Kegagalan endpoint pandangan latihan tidak boleh menggagalkan viewer: viewer kembali ke perilaku sekarang.
- Sebelum selesai: `uv run ruff check .`, `uv run ruff format --check .`, dan `npm run build` di `web/` lulus.

## Review Focus

1. Versi yang folder `sfm`-nya hilang (dihapus atau versi lama): endpoint 404 `no_sfm`, viewer tetap tampil dengan perilaku lama. Diuji di Task 2.
2. URL dengan `cam=` sah: pandangan dari `cam=` dipakai, bukan pandangan latihan. Diuji manual di Task 3 langkah verifikasi.
3. Peta dengan lebih dari 300 foto: pandangan dicuplik merata, `start` tetap indeks yang sah. Diuji di Task 1.
4. Arah atas model berlawanan dengan +Y (kamera COLMAP terbalik): rotasi tegak tetap kuaternion satuan yang sah, bukan NaN. Diuji di Task 1.
5. `SplatJob` gagal, masih antre, atau `summary` lama tanpa kunci `metrics`: `splat_summary` bernilai `null` atau berisi `null` per kolom, halaman Maps tidak error. Diuji di Task 4.

## Bukan tujuan

- **Membatasi orbit di dekat lintasan.** `CameraControls` PlayCanvas tidak punya batas posisi; memaksanya berarti menulis ulang kontrol. Tombol lompat antar pandangan latihan (Task 3) memberi jalan pulang ke pandangan bersih dengan biaya jauh lebih kecil. Ditinjau ulang bila pengguna tetap tersesat.
- Mengubah pipeline latihan, menghapus floaters, atau menyimpan berkas baru di folder `splat/`.

---

### Task 1: Pandangan latihan dari model SfM (server, fungsi murni)

**Files:**
- Create: `server/splat_views.py`
- Test: `tests/test_splat_views.py`

**Interfaces:**
- Consumes: objek gambar pycolmap (atau tiruan `SimpleNamespace`) dengan `name: str`, `projection_center() -> ndarray(3)`, `cam_from_world().rotation.matrix() -> ndarray(3,3)`. Pola tiruan sama dengan `tests/test_area_api.py::fake_image`.
- Produces:
  - `MAX_VIEWS: int = 300`
  - `training_views(images: Iterable, max_views: int = MAX_VIEWS) -> dict` dengan bentuk
    `{"start": int, "level_rotation_xyzw": [x, y, z, w], "views": [{"name": str, "center": [3 float], "forward": [3 float]}]}`.
    `views` diurutkan menurut `name` (urutan rekaman), dicuplik merata bila lebih dari `max_views`.
    `forward` = baris ketiga `cam_from_world().rotation.matrix()` (sumbu z kamera di dunia), dinormalkan.
    `start` = indeks (di dalam `views` hasil cuplikan) pandangan yang pusatnya paling dekat ke rata-rata semua pusat; seri dipecah ke indeks terkecil.
    `level_rotation_xyzw` = `level_rotation(up)` dengan `up` = rata-rata ternormalisasi dari `-R[1, :]` (arah atas kamera COLMAP di dunia) semua gambar.
    Raise `ValueError("no registered images")` bila kosong.
  - `level_rotation(up: np.ndarray) -> list[float]`: kuaternion satuan xyzw yang memutar `up` ke `(0, 1, 0)`. Bila `up` hampir searah (`dot > 0.9999`), kembalikan identitas `[0, 0, 0, 1]`; bila hampir berlawanan (`dot < -0.9999`), kembalikan rotasi 180 derajat di sumbu X `[1, 0, 0, 0]`.
  - `load_views(sfm: Path) -> dict`: baca `pycolmap.Reconstruction(str(sfm))`, kembalikan `training_views(rec.images.values())`; di-cache dengan `functools.lru_cache(maxsize=8)` pada fungsi bantu berkunci `(str(sfm), mtime_ns dari sfm/images.bin)`. `FileNotFoundError` bila `sfm/images.bin` tidak ada. Beri komentar `# ponytail:` bahwa Reconstruction ikut memuat points3D (lambat sekali per versi, lalu cache).

- [x] **Step 1: Tulis tes yang gagal** di `tests/test_splat_views.py`:

```python
def test_views_sorted_by_name_with_unit_forward():
    imgs = [fake(n, c) for n, c in [("b.jpg", [1, 0, 0]), ("a.jpg", [0, 0, 0])]]
    out = training_views(imgs)
    assert [v["name"] for v in out["views"]] == ["a.jpg", "b.jpg"]
    assert all(abs(np.linalg.norm(v["forward"]) - 1) < 1e-9 for v in out["views"])


def test_start_is_view_nearest_centroid():
    # pusat 0..4 di sumbu x, rata-rata 2 -> indeks 2
    out = training_views([fake(f"{i}.jpg", [i, 0, 0]) for i in range(5)])
    assert out["start"] == 2


def test_subsamples_above_max_views_and_keeps_valid_start():
    out = training_views([fake(f"{i:04d}.jpg", [i, 0, 0]) for i in range(1000)], max_views=300)
    assert len(out["views"]) == 300
    assert out["views"][0]["name"] == "0000.jpg" and out["views"][-1]["name"] == "0999.jpg"
    assert 0 <= out["start"] < 300


def test_level_rotation_maps_up_to_plus_y():
    for up in ([0, -1, 0.2], [0.3, 0.1, 0.9], [0, 1, 0]):
        q = level_rotation(np.array(up, float) / np.linalg.norm(up))
        assert abs(np.linalg.norm(q) - 1) < 1e-9
        assert np.allclose(
            pycolmap.Rotation3d(q) * (np.array(up) / np.linalg.norm(up)), [0, 1, 0], atol=1e-9
        )


def test_level_rotation_opposite_up_is_valid():
    q = level_rotation(np.array([0.0, -1.0, 0.0]))
    assert not np.any(np.isnan(q))
    assert np.allclose(pycolmap.Rotation3d(q) * np.array([0.0, -1.0, 0.0]), [0, 1, 0], atol=1e-9)


def test_empty_raises():
    with pytest.raises(ValueError):
        training_views([])
```

`fake(name, center)` memakai matriks rotasi identitas (`forward` = `[0, 0, 1]`, atas = `[0, -1, 0]`).

- [x] **Step 2: Jalankan, pastikan gagal**
Run: `uv run pytest tests/test_splat_views.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'server.splat_views'`.

- [x] **Step 3: Implementasikan `server/splat_views.py`** sesuai blok Interfaces. Cuplikan merata: `np.linspace(0, n - 1, max_views).round().astype(int)` lalu `np.unique`. Rotasi: sumbu `cross(up, Y)`, sudut `arccos(clip(dot, -1, 1))`, lalu `pycolmap.Rotation3d` dari matriks Rodrigues atau kuaternion langsung.

- [x] **Step 4: Jalankan, pastikan lulus**
Run: `uv run pytest tests/test_splat_views.py -v`
Expected: 6 passed.

- [x] **Step 5: Berhenti dan tampilkan** `git status --short` dan `git diff --stat` (tanpa commit).

### Task 2: Endpoint `GET /api/versions/{version_id}/splat/views`

**Files:**
- Modify: `server/maps_api.py` (di bawah `splat_placement`)
- Test: `tests/test_maps_api.py`

**Interfaces:**
- Consumes: `splat_views.load_views(sfm: Path) -> dict` (Task 1), `splat_pipeline.sfm_dir(map_dir: Path) -> Path`.
- Produces: `GET /api/versions/{version_id}/splat/views` mengembalikan dict Task 1 apa adanya. Galat:
  404 `"version not found"` bila versi tidak ada; 404 `detail={"code": "no_sfm", "message": "map version has no SfM model"}` bila jalur sfm keluar dari `MAPS_ROOT`, `FileNotFoundError`, atau `ValueError`.

- [x] **Step 1: Tulis tes yang gagal** di `tests/test_maps_api.py` (pakai fixture `client` dan `make_version` yang ada; `monkeypatch` `splat_views.load_views`; tambah impor `from server import splat_views` dan `from server.db import SplatJob` bila belum ada):

```python
def test_splat_views_returns_loader_output(client, monkeypatch):
    v = make_version(client)
    want = {
        "start": 0,
        "level_rotation_xyzw": [0, 0, 0, 1],
        "views": [{"name": "a.jpg", "center": [0, 0, 0], "forward": [0, 0, 1]}],
    }
    seen = []
    monkeypatch.setattr(splat_views, "load_views", lambda sfm: seen.append(sfm) or want)
    r = client.get(f"/api/versions/{v.id}/splat/views")
    assert r.status_code == 200 and r.json() == want
    assert seen[0] == Path(v.path) / "kp1024-r1024" / "sfm"


def test_splat_views_without_sfm_is_404_no_sfm(client):
    v = make_version(client)  # tanpa folder sfm, load_views asli
    r = client.get(f"/api/versions/{v.id}/splat/views")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_sfm"


def test_splat_views_unknown_version_is_404(client):
    assert client.get("/api/versions/999/splat/views").status_code == 404
```

- [x] **Step 2: Jalankan, pastikan gagal**
Run: `uv run pytest tests/test_maps_api.py -k splat_views -v`
Expected: 3 FAIL (404 route tidak ada atau atribut `splat_views` tidak ada).

- [x] **Step 3: Tambahkan endpoint** `def splat_views_endpoint(version_id: int, user: uploads.User, s: uploads.DB) -> dict` dengan pola `splat_placement`.

- [x] **Step 4: Jalankan, pastikan lulus**
Run: `uv run pytest tests/test_maps_api.py tests/test_splat_views.py -v`
Expected: semua passed, termasuk tes lama `test_maps_api.py`.

- [x] **Step 5: Berhenti dan tampilkan** `git status --short` dan `git diff --stat`.

### Task 3: Viewer memakai pandangan latihan

**Files:**
- Create: `web/lib/splatViews.ts`
- Test: `web/lib/splatViews.test.ts`
- Modify: `web/lib/api.ts` (tipe dan `api.splatViews`), `web/components/SplatViewer.tsx`, `web/lib/i18n/en.ts`, `web/lib/i18n/id.ts`

**Interfaces:**
- Consumes: endpoint Task 2.
- Produces:
  - Di `web/lib/api.ts`: `export type SplatView = { name: string; center: [number, number, number]; forward: [number, number, number] };`, `export type SplatViews = { start: number; level_rotation_xyzw: [number, number, number, number]; views: SplatView[] };`, dan `splatViews: (versionId: number) => call<SplatViews>(\`/api/versions/${versionId}/splat/views\`)`.
  - Di `web/lib/splatViews.ts`: `export function viewPose(view: SplatView, world: ArrayLike<number>): { position: [number, number, number]; target: [number, number, number] }`. `world` adalah `pc.Mat4.data` (16 angka, column-major). `position` = `world` diterapkan ke `center` sebagai titik; `target` = `position` + arah (`world` diterapkan ke `forward` sebagai vektor, tanpa translasi, lalu dinormalkan). File ini tidak mengimpor `playcanvas`.

- [x] **Step 1: Tulis tes yang gagal** `web/lib/splatViews.test.ts` dengan `node:test` dan `node:assert/strict`:
  - `identity matrix`: `viewPose({center:[1,2,3], forward:[0,0,1]}, I)` memberi `position [1,2,3]`, `target [1,2,4]`.
  - `translation`: matriks dengan translasi `(10, 0, -5)` di `data[12..14]` menggeser `position` dan `target` sama besar.
  - `scale 2 keeps unit look direction`: matriks skala 2 memberi `target - position` panjang 1.
  - `rotation 180 about X`: `forward [0,0,1]` menjadi arah `[0,0,-1]`.

- [x] **Step 2: Jalankan, pastikan gagal**
Run (di `web/`): `node --test lib/splatViews.test.ts`
Expected: FAIL, modul `./splatViews.ts` tidak ditemukan. (Butuh Node 22.18 atau lebih baru; catat versi `node -v` di laporan.)

- [x] **Step 3: Implementasikan `viewPose`.** Lalu ubah `SplatViewer.tsx`:
  1. Setelah `placement` diambil, panggil `api.splatViews(currentVersion.id)` dalam `try/catch`; gagal berarti `views = null`, tanpa pesan galat ke pengguna.
  2. Versi tidak selaras dan `views` ada: `splatEntity.setLocalRotation(new pc.Quat(...views.level_rotation_xyzw))`, menggantikan `UNALIGNED_FALLBACK_ROTATION`. Tanpa `views`: perilaku lama.
  3. Pose awal: `parsedCam` tetap prioritas pertama; bila tidak ada `cam=` dan `views` ada, pakai `viewPose(views.views[views.start], splatEntity.getWorldTransform().data)`, dan `initialFocus` = posisi + arah depan dikali `DEFAULT_FOCUS_DISTANCE_M` (sama seperti cabang `cam=`). Tanpa `views`: perilaku lama.
  4. Simpan `views` di ref dan indeks pandangan aktif di state. Dua tombol baru di `controls` `PageHead`, sebelum Reset Camera: "pandangan sebelumnya" dan "pandangan berikutnya" (berputar di ujung), memanggil `controlsRef.current.reset(focus, position)` dengan pose `viewPose` indeks baru. Label penghitung `t("splat.viewCounter", { i, n })`. Tombol tidak tampil bila `views` null.
  5. Reset Camera tetap kembali ke `initialCamPose` dan mengembalikan indeks ke `start`.
  6. Kunci i18n baru di `en.ts` dan `id.ts`: `splat.prevView` ("Previous view" / "View sebelumnya"), `splat.nextView` ("Next view" / "View berikutnya"), `splat.viewCounter` ("Training view {i} of {n}" / "Training view {i} dari {n}").

- [x] **Step 4: Jalankan, pastikan lulus**
Run (di `web/`): `node --test lib/splatViews.test.ts` lalu `npm run build`
Expected: 4 tes passed; build selesai tanpa galat TypeScript.

- [ ] **Step 5: Verifikasi di browser dengan data asli.** **Tidak dijalankan:** aset scene.sog dan SfM yang diminta tidak tersedia lokal; verifikasi visual diserahkan ke Claude. Salin `scene.sog` dan folder `kp1024-r1024/sfm` versi `floor10` v2 dan `hcm-lantai-10` v1 hanya bila Bagus menyediakannya secara lokal; bila tidak tersedia, tulis "tidak dijalankan" dan serahkan verifikasi visual ke Claude. Yang diperiksa: (a) tanpa `cam=`, viewer langsung menampilkan pemandangan yang mirip satu foto latihan, (b) tombol berikut/sebelum berpindah pandangan, (c) `?cam=` sah tetap menang, (d) versi tanpa `sfm` tetap terbuka dengan perilaku lama.

- [x] **Step 6: Berhenti dan tampilkan** `git status --short` dan `git diff --stat`.

### Task 4: Ringkasan 3D di panel Properties versi

**Files:**
- Modify: `server/maps_api.py` (`VersionOut`, `_out`), `web/lib/api.ts` (`Version`), `web/app/maps/page.tsx` (blok `<dl>` Properties sekitar `selectedVersion.has_report`), `web/lib/i18n/en.ts`, `web/lib/i18n/id.ts`
- Test: `tests/test_maps_api.py`

**Interfaces:**
- Consumes: `SplatJob.summary` (dict JSON) yang ditulis pekerja splat, kunci yang dipakai: `gaussians_after`, `metrics.psnr`, `metrics.ssim`, `metrics.lpips`, `stage_seconds.train`, `built_at`.
- Produces:
  - `class SplatSummaryOut(BaseModel)`: `gaussians: int | None`, `psnr: float | None`, `ssim: float | None`, `lpips: float | None`, `train_seconds: float | None`, `built_at: str | None`.
  - `VersionOut.splat_summary: SplatSummaryOut | None = None`, diisi hanya bila `splat_job.status == "done"` dan `summary` bukan `None`; kunci yang hilang menjadi `None`.
  - Di `web/lib/api.ts`: `splat_summary: { gaussians: number | null; psnr: number | null; ssim: number | null; lpips: number | null; train_seconds: number | null; built_at: string | null } | null`.

- [x] **Step 1: Tulis tes yang gagal** di `tests/test_maps_api.py`:

```python
def test_version_has_splat_summary_when_done(client):
    v = make_version(client)
    client.db.add(
        SplatJob(
            map_version_id=v.id,
            status="done",
            summary={
                "gaussians_after": 1001679,
                "built_at": "2026-11-17T15:57:52+00:00",
                "stage_seconds": {"train": 1157.7},
                "metrics": {"psnr": 27.615, "ssim": 0.9128, "lpips": 0.1953},
            },
        )
    )
    client.db.commit()
    s = next(x for x in client.get("/api/versions").json() if x["id"] == v.id)["splat_summary"]
    assert s == {
        "gaussians": 1001679,
        "psnr": 27.615,
        "ssim": 0.9128,
        "lpips": 0.1953,
        "train_seconds": 1157.7,
        "built_at": "2026-11-17T15:57:52+00:00",
    }


def test_old_summary_without_metrics_gives_nulls(client):
    v = make_version(client)
    client.db.add(SplatJob(map_version_id=v.id, status="done", summary={"gaussians_after": 5}))
    client.db.commit()
    s = next(x for x in client.get("/api/versions").json() if x["id"] == v.id)["splat_summary"]
    assert s["gaussians"] == 5 and s["psnr"] is None and s["train_seconds"] is None


def test_failed_or_queued_job_has_no_summary(client):
    for status in ("failed", "queued"):
        v = make_version(client)
        client.db.add(SplatJob(map_version_id=v.id, status=status, summary={"gaussians_after": 1}))
        client.db.commit()
        assert (
            next(x for x in client.get("/api/versions").json() if x["id"] == v.id)["splat_summary"]
            is None
        )
```

- [x] **Step 2: Jalankan, pastikan gagal**
Run: `uv run pytest tests/test_maps_api.py -k summary -v`
Expected: 3 FAIL (`KeyError: 'splat_summary'`).

- [x] **Step 3: Implementasikan** `SplatSummaryOut`, isian di `_out`, tipe web, lalu baris-baris di panel Properties (tampil hanya bila `splat_summary` ada): Gaussian (format ribuan), PSNR / SSIM / LPIPS (2, 3, 3 desimal), waktu latih (menit dibulatkan), waktu build (format tanggal yang sudah dipakai halaman). Nilai `null` ditampilkan "-". Kunci i18n: `maps.splatGaussians`, `maps.splatQuality`, `maps.splatTrainTime`, `maps.splatBuiltAt` di `en.ts` dan `id.ts` (istilah teknis tetap Inggris).

- [x] **Step 4: Jalankan, pastikan lulus**
Run: `uv run pytest tests/test_maps_api.py tests/test_splat_views.py -v` lalu (di `web/`) `npm run build`
Expected: semua passed; build tanpa galat.

- [x] **Step 5: Pemeriksaan akhir seluruh cabang**
Run: `uv run ruff check .` dan `uv run ruff format --check .` dan `uv run pytest -q`
Expected: ruff bersih; pytest semua lulus kecuali `tests/test_db.py::test_migration_cli_runs_like_the_container` yang memang gagal di Windows juga di `main` (catat apa adanya).

- [x] **Step 6: Berhenti dan tampilkan** `git status --short`, `git diff --stat`, dan laporan akhir dengan keluaran mentah semua perintah. Tanpa commit.
