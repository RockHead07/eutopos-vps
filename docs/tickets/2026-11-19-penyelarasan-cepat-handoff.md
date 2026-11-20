# Brief serah terima: penyelarasan cepat tanpa titik meteran (server dan CLI)

Ditulis 2026-11-19 untuk agen pelaksana. Kerangka CO-STAR. Spesifikasi:
`D:/Dev/Projects/eutopos-vps/docs/specs/2026-11-19-skala-known-distance-design.md` (bagian 4, 4b, 5, 8). Spesifikasi
dan brief ini **belum ter-commit**: baca dari checkout utama dengan path absolut, hanya baca.

---

## C. Context (konteks)

eutopos-vps adalah VPS lokal untuk navigasi indoor (FastAPI, SQLModel, pycolmap, hloc). Peta baru hanya bisa dipakai
navigasi bila punya penyelarasan model ke meter (`align.json` di `<versi>/kp*-r*/`, atau baris `alignment` applied di
database). Satu-satunya cara sekarang adalah kalibrasi titik: `server/calibration.py` (`fit_alignment`, minimal 4
titik acuan, konvensi kerangka gedung meter, Z ke atas, kamera setinggi `height_m = 1.3`) dan
`alignment.validate_align` mewajibkan `reference_points >= 4`. Penaksir Sim3 satu-satunya ada di `server/sim3.py`
(`fit(src, tgt, ransac_m)`). Perintah `python -m server.manage align --version N --align <berkas>` memasang
`align.json` lewat `alignment.install`.

Pemilik repo (Bagus) ingin developer cukup merekam, tanpa mengukur 4 titik. Tiket ini menambah dua metode
penyelarasan tanpa titik meteran:
- `arcore_pose`: dari pose ARCore per foto (`frames.jsonl` keluaran aplikasi capture). Spike 2026-11-19 (job 23)
  menunjukkan pose ARCore cocok dengan SfM sampai median sekitar 10 cm.
- `known_distance`: dari satu atau dua jarak yang diketahui antara dua frame, untuk peta dari video biasa.

Format `frames.jsonl` (satu baris per foto): `file` (mis. `000001.jpg`), `t_ns`, `position` [3] dan `rotation_xyzw`
[4] dalam kerangka dunia Unity (kidal, Y ke atas, meter), `tracking`, `K`. Nama gambar di model SfM berbentuk
`mapping/000001.jpg`; cocokkan lewat nama dasar berkas.

## O. Objective (tujuan)

### 1. Modul murni `server/quick_align.py`

Tanpa FastAPI dan tanpa database. Antarmuka (nama dan tipe wajib persis):

- `unity_to_building(p: np.ndarray) -> np.ndarray`: `(x_b, y_b, z_b) = (x_u, z_u, y_u)` untuk larik `(N, 3)`. Ini
  pertukaran sumbu (pantulan), mengubah kidal ke tangan kanan dengan Z ke atas.
- `load_model(sfm_dir: Path) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]`: dari `pycolmap.Reconstruction`,
  kembalikan `centers[nama_dasar]` (pusat kamera dunia) dan `ups[nama_dasar]` (arah "atas gambar" di dunia, yaitu
  sumbu -y kamera COLMAP dibawa ke dunia) untuk semua gambar terdaftar. Nama dasar kembar: `ValueError`.
- `read_frames(path: Path) -> list[dict]`: baca `frames.jsonl`, periksa tiap baris (`file` ada, `position` 3 angka
  berhingga); baris rusak menghasilkan `ValueError` yang menyebut nomor baris.
- `from_arcore(centers, frames, height_m=1.3, ransac_m=0.5) -> dict`:
  - pasangkan lewat nama dasar; kurang dari `MIN_ARCORE_FRAMES = 10` pasangan: `ValueError`;
  - target = `unity_to_building(posisi ARCore)`, lalu geser z supaya median z target = `height_m`;
  - `sim3.fit(src=pusat SfM, tgt=target, ransac_m)`; `None`: `ValueError`; skala tidak positif atau tidak berhingga:
    `ValueError`;
  - kembalikan `align` dengan `method: "arcore_pose"`, `meter_from_model` (bentuk sama dengan `calibration`),
    `phone_height_m`, `matched_frames`, `residual_median_m`, `residual_max_m` (residu 3D dalam meter, dibulatkan 3
    angka seperti `calibration`).
- `from_known_distance(centers, ups, pairs, height_m=1.3) -> dict`, dengan `pairs` daftar 1 atau 2 tuple
  `(frame_a, frame_b, distance_m)`:
  - gravitasi: rata-rata `ups` semua gambar terdaftar, dinormalkan; `gravity_spread_deg` = median sudut tiap `ups`
    terhadap rata-rata;
  - jarak model tiap pasangan diukur pada bidang tegak lurus gravitasi; `distance_m <= 0`, frame tidak terdaftar,
    atau jarak model mendekati nol: `ValueError`;
  - skala = rata-rata `distance_m / jarak_model`; bila dua pasangan, `scale_spread_percent` = selisih relatif skala;
  - rotasi: gravitasi ke +Z, sumbu x mengikuti komponen utama posisi kamera di bidang lantai; asal di proyeksi lantai
    gambar terdaftar pertama (urut nama); z digeser supaya median tinggi kamera = `height_m`;
  - kembalikan `align` dengan `method: "known_distance"`, `meter_from_model`, `phone_height_m`, `known_distances`
    (tiap entri `frame_a`, `frame_b`, `distance_m`, `model_distance`), `gravity_spread_deg`, dan
    `scale_spread_percent` bila dua pasangan.
- `warnings(align: dict) -> list[str]` (teks bahasa Indonesia): `known_distance` dengan satu pasangan saja, jarak di
  bawah 10 m, `gravity_spread_deg` di atas 10, atau `scale_spread_percent` di atas 5; `arcore_pose` dengan
  `residual_median_m` di atas 0,25. Ambang ini titik awal (tebakan), tulis sebagai konstanta bernama di atas modul.

Semua keluaran harus lolos `alignment.validate_align` (panggil di akhir kedua fungsi, seperti `calibration`).

### 2. Validasi per metode di `server/alignment.py`

`validate_align` membaca `method` (tidak ada berarti `"survey"`):
- `survey`: aturan sekarang, tidak berubah.
- `arcore_pose`: wajib `matched_frames` bilangan bulat (bukan bool) minimal 10, `residual_median_m` dan
  `residual_max_m` berupa angka.
- `known_distance`: wajib `known_distances` daftar 1 atau 2 entri dengan `distance_m` dan `model_distance` positif,
  dan `gravity_spread_deg` angka.
- Metode lain: `ValueError`.
Pemeriksaan `meter_from_model` berlaku untuk semua metode. Jangan mengubah `AlignFile`, `DbAlign`, atau `Localizer`.

### 3. Perintah CLI `python -m server.manage quick-align`

```
quick-align --version N --method arcore --frames <frames.jsonl> [--out FILE] [--install] [--replace-survey]
quick-align --version N --method distance --pair FRAME_A FRAME_B METER [--pair ...] [--out FILE] [--install] [--replace-survey]
```

- Model dibaca dari `run_dir(Path(v.path)) / "sfm"` (pakai `server.pipeline.run_dir`, sama dengan pemilik jalur yang
  ada). Nama frame boleh `000157.jpg` atau nama penuh; cocokkan lewat nama dasar.
- Cetak ringkasan (metode, skala, kualitas) dan semua `warnings`. `--out` menulis JSON. Tanpa `--install`, tidak ada
  yang dipasang.
- `--install` memasang lewat `alignment.install` yang sudah ada (jangan menulis berkas dengan cara lain). Sebelum
  memasang: bila versi sudah punya penyelarasan `survey` (baris `alignment` applied di database, atau `align.json`
  yang ada tanpa `method` atau dengan `method: "survey"`), tolak dengan pesan jelas kecuali `--replace-survey`.
  Bila baris dashboard applied ada, tampilkan peringatan yang sama dengan perintah `align` (dashboard didahulukan).

## S. Style (gaya kerja)

TDD: tes gagal dulu, lalu implementasi. Baca `CLAUDE.md` repo (aturan 1 sampai 10: tanpa data karangan, verifikasi
sebelum klaim, tanpa dependensi baru, kerjakan tepat yang diminta, aturan worktree). Pakai ulang `sim3.fit` dan
`run_dir`; jangan menulis penaksir Sim3 kedua. Perubahan minimal.

Tes wajib (data sintetis, tanpa berkas peta nyata):
- `tests/test_quick_align.py`:
  - `unity_to_building` memetakan sumbu dengan benar dan determinannya -1;
  - `from_arcore` mengembalikan Sim3 yang diketahui (skala, rotasi, translasi buatan) dengan residu mendekati nol,
    termasuk kasus pose Unity kidal; kurang dari 10 pasangan ditolak; baris `frames.jsonl` rusak menyebut nomor baris;
  - `from_known_distance` pada lintasan buatan dengan gravitasi miring, skala, dan yaw diketahui mengembalikan skala
    benar, gravitasi ke +Z, dan median tinggi kamera 1,3; dua pasangan berbeda skala melaporkan
    `scale_spread_percent` yang benar; frame tidak terdaftar ditolak;
  - `warnings` memicu tiap peringatan pada batasnya.
- `tests/test_alignment.py`: tambah tes `validate_align` per metode (berkas lama tanpa `method` tetap lolos,
  `survey` kurang dari 4 titik tetap ditolak, `known_distance` tanpa `known_distances` ditolak, metode tak dikenal
  ditolak). **Tes lama di berkas itu tidak boleh diubah.**
- Tes CLI, tambahkan di `tests/test_alignment.py` mengikuti pola tes `manage align` yang ada di sana (sekitar baris
  130 sampai 160 dan 318, `monkeypatch.setattr("sys.argv", [...])`): `--install` menolak menimpa `survey` tanpa
  `--replace-survey`, dan berhasil dengan flag itu.

## T. Tone (nada)

Laporan lugas dan jujur. Pisahkan "diuji unit" dari "dibuktikan dengan peta nyata". Bahasa Indonesia, istilah teknis
Inggris, tanpa em dash.

## A. Audience (pembaca)

Bagus yang memutuskan commit, lalu Claude yang memverifikasi ulang secara mandiri dan menjalankan perintah ini pada
peta nyata `spike-arcore` (job 23) di PC lab.

## R. Response (format keluaran)

Tulis `D:/wt/quick-align/LAPORAN-QUICK-ALIGN.md` (jangan di-commit):
1. Garis dasar tes sebelum perubahan (perintah dan output ringkas, termasuk `PYTHONPATH` yang dipakai bila perlu).
2. Berkas yang diubah, tes yang ditambah, output tes gagal lalu lulus.
3. Hasil akhir: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`.
4. Contoh keluaran `quick-align` pada model sintetis (bila kamu membuatnya untuk tes).
5. Penyimpangan dari brief dan alasannya; usulan di luar lingkup.
6. SHA-256 berkas yang berubah; draf pesan commit (belum dijalankan).
7. Daftar yang tidak terbukti (pemakaian pada peta nyata pasti termasuk).

## Batas

- **Jangan commit, push, PR, atau merge.** Worktree baru:
  `git fetch && git worktree add -b feat/quick-align D:/wt/quick-align origin/main`. Jangan berpindah cabang atau
  mengubah berkas di checkout utama.
- PR #107 (`feat/auto-publish`) mungkin belum di-merge saat kamu mulai. Jangan menyentuh `version_alignment`,
  `server/active_map.py`, atau `server/gate.py`. Bila `origin/main` sudah memuat #107, tetap jangan mengubahnya.
- **Jangan menyentuh PC lab** (ssh, docker, systemd), production, Cloudflare, atau rahasia.
- Tanpa dependensi baru, tanpa migrasi Alembic, tanpa perubahan `web/`. Antarmuka dashboard adalah tiket terpisah.
- Berkas yang boleh diubah: `server/quick_align.py` (baru), `server/alignment.py` (hanya `validate_align` dan
  fungsi bantu validasinya), `server/manage.py` (perintah `quick-align`), `tests/test_quick_align.py` (baru),
  `tests/test_alignment.py` (hanya tambahan). Perlu berkas lain?
  Berhenti dan tulis alasannya.
- Jangan melonggarkan, menghapus, atau melewati (`skip`, `xfail`) tes lama.

## Kriteria selesai

- Kedua metode menghasilkan `align` yang lolos `validate_align` dan dipakai `Localizer` tanpa perubahan kodenya.
- `survey` lama tetap berlaku persis seperti sebelumnya.
- Tes wajib ada dan lulus; seluruh suite hijau kecuali kegagalan garis dasar yang tercatat sebelum perubahan.
- `ruff` bersih; laporan lengkap sesuai bagian R.
