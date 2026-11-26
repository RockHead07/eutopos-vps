# Laporan scan per pekerjaan peta

Tanggal: 2026-11-25. Status: draf, menunggu persetujuan Bagus. Dasar kode: origin/main `14085e0`.

## 1. Maksud

Arahan Bu Evi (bimbingan 25 Nov): untuk tiap scan, tampilkan luas area, lama merekam, waktu proses di
komputer, dan kecepatan jaringan di web eutopos. Kalau mau gampang, taruh semua data yang dipakai di
dashboard. Bagus menambahkan: data lain yang bisa kita dapat juga ikut ditampilkan. Angka ini akan
dipakai di draf jurnal IMAVIS, jadi harus bisa diulang dan tidak boleh berubah diam-diam.

Bentuknya bukan log kejadian, tapi **kartu laporan** per pekerjaan (pola experiment tracking): satu
catatan terstruktur berisi masukan, parameter, hasil, dan lingkungan, dihitung sekali lalu dibekukan.

## 2. Tujuan, bukan tujuan, anti-tujuan

Tujuan:
- Kartu laporan untuk setiap job `done` dan job yang ditolak gerbang (`failed` dengan stage `gate`).
- Panel "Laporan scan" di halaman job, tabel pembanding di halaman daftar job, unduh CSV.
- Statistik pemakaian peta (lokalisasi) per versi, dihitung saat dibuka.
- Isi ulang kartu untuk job lama sejauh datanya masih ada.

Bukan tujuan (sekarang):
- Puncak VRAM/CPU per job (butuh sampling terus-menerus).
- Model HP untuk job video atau capture versi lama (hanya ada bila `meta.json` dikirim, lihat 4.1).
- Uji beban multiuser Pak Dhoto (tugas terpisah; statistik pemakaian di sini hanya bahan awal).
- Kartu untuk job yang gagal sebelum gerbang.
- Identitas pengguna di kartu atau statistik.

Anti-tujuan (gagal walau jalan):
- Angka di kartu berubah tanpa jejak karena rumus diganti.
- Nilai tidak diketahui tampil sebagai `0` atau tebakan.
- Statistik pemakaian (berubah terus) dicampur ke kartu yang dibekukan.
- Menggagalkan pembangunan peta karena perhitungan laporan error.

## 3. Pendekatan

Dipertimbangkan:
- **A. Dihitung worker sekali saat job selesai, disimpan di `MapJob.summary["report"]`** (DIPILIH Bagus).
  Cepat ditampilkan, angka stabil, versi rumus tercatat. Biaya: dua jenis angka (tetap dan hidup) harus
  diberi label jelas.
- B. Semua dihitung saat halaman dibuka. Ditolak: tiap buka memuat model SfM dan `frames.jsonl`, dan
  angka jurnal bisa berubah saat rumus diubah.
- C. Tabel database metrik terpisah. Ditolak: migrasi dan skema baru untuk data yang muat di JSON
  `summary`; dashboard dan CSV tidak butuh SQL.

## 4. Struktur kartu (`summary["report"]`)

```json
{
  "version": 1,
  "computed_at": "ISO UTC",
  "recording": {...},
  "network": {...},
  "processing": {...},
  "quality": {...}
}
```

Aturan umum:
- Nilai tidak diketahui = `null`, disertai `"<nama>_reason"` bila alasannya berguna
  (`"not_recorded"`, `"no_arcore"`, `"cli_job"`, `"video_deleted"`).
- Setiap metrik turunan menyimpan parameter rumusnya di kartu (`method`, `radius_m`, `cell_m`).
- `version` dinaikkan setiap rumus berubah. Kartu lama tidak diubah kecuali dihitung ulang eksplisit.
- Seluruh perhitungan dibungkus: error apa pun menghasilkan `{"version": 1, "error": "..."}` dan
  job tetap selesai normal.

### 4.1 Rekaman (`recording`), arahan Bu Evi

Sumber dipilih per job: `"arcore"` bila `maps/<area>/job-<id>/capture/frames.jsonl` ada (aplikasi
capture, peran peta), `"video"` bila peran peta berupa video, `null` bila keduanya tidak ada.

| Kunci | Arti dan rumus |
|---|---|
| `source` | `"arcore"`, `"video"`, atau `null` |
| `map_photos` | jumlah foto peran peta (baris `frames.jsonl`, atau `run.map_images` untuk video) |
| `query_photos` | jumlah foto uji (`run.queries` bila ada) |
| `segments` | jumlah nilai `segment` unik (`segment` hilang = 0, sesuai `CaptureRecords.cs`) |
| `duration_s` | ARCore: jumlah per segmen dari `(max t_ns - min t_ns) / 1e9`; jeda antarsegmen tidak dihitung. Video: jumlah durasi video peta dari kotak `mvhd` |
| `path_length_m` | ARCore saja: urutkan per segmen menurut `t_ns`, jumlah jarak horizontal (sumbu X dan Z, Y ke atas di ARCore) antarfoto berurutan |
| `footprint_m2` | ARCore saja: luas jejak lintasan, lihat di bawah |
| `footprint` | `{"method": "trajectory_buffer", "radius_m": 1.0, "cell_m": 0.25}` |
| `mean_speed_m_s` | `path_length_m / duration_s` |
| `tracking_losses` | dari `capture/meta.json` (`tracking_losses`) bila ada, selain itu `null` reason `"no_meta"` |
| `device_model` | dari `capture/meta.json` (`device_model`) bila ada, selain itu `null` reason `"no_meta"` |
| `height_range_m` | `max Y - min Y` dalam kerangka yang sama dengan `footprint_m2` (lihat di bawah); bila > 2,5 m tampilkan peringatan "mungkin lebih dari satu lantai" |

Catatan sumber: `meta.json` ditulis aplikasi capture versi cabang `docs/aplikasi-capture-matang`
(PR eutopos-mobile#7, belum di main) dan sudah ikut diekstrak `frame_package` ke `capture/`. Proporsi
baris `tracking != "Tracking"` sengaja tidak dipakai: aplikasi hanya memotret saat tracking, jadi
angkanya selalu mendekati nol dan tidak bermakna.

Kerangka koordinat (keputusan Claude): segmen baru dibuat aplikasi saat tracking hilang atau pose
melompat (`PoseContinuity.cs`), jadi posisi ARCore antarsegmen belum tentu satu kerangka.
- `path_length_m` dan `duration_s` dijumlah per segmen dari pose ARCore mentah (aman, tidak lintas segmen).
- `footprint_m2` dan `height_range_m`: bila `summary.align.status == "applied"`, pakai pusat kamera SfM
  terdaftar yang sudah ditransformasi ke meter (satu kerangka konsisten), ruas disambung menurut urutan
  `t_ns` per segmen; `footprint.frame = "aligned_sfm"`. Selain itu hitung per segmen di kerangka ARCore
  lalu dijumlah, `footprint.frame = "arcore_per_segment"`, dan tampilkan "batas atas: tumpang tindih
  antarsegmen terhitung ganda" bila `segments > 1`.

Luas jejak lintasan: proyeksikan posisi ke bidang lantai (X-Z), sambungkan foto berurutan dalam segmen
yang sama menjadi ruas garis, lalu hitung sel grid `cell_m` yang titik tengahnya berjarak <= `radius_m`
dari ruas mana pun. Luas = jumlah sel x `cell_m`². Foto tunggal dalam segmen menjadi lingkaran. Pakai
numpy (sudah terpasang), tanpa pustaka geometri baru. `radius_m` adalah pilihan kita, bukan hasil ukur,
dan harus disebut di tampilan dan jurnal. `path_length_m` dilaporkan di sampingnya karena bebas parameter.

Video: `path_length_m`, `footprint_m2`, `tracking_losses`, `device_model`, `height_range_m` = `null`
dengan reason `"no_arcore"`.

Durasi video dibaca saat `stamp_recorded`, sebelum video dihapus: perluas `video_meta` agar mengembalikan
durasi (`mvhd` timescale dan duration) dan simpan sebagai `duration_s` di entri video. Job lama tidak
punya nilai ini (reason `"video_deleted"`).

### 4.2 Jaringan (`network`), arahan Bu Evi

Catat dua waktu baru di entri video (`MapJob.videos`, JSON, tanpa migrasi):
- `upload_started_at`: saat hook pre-create memberi `upload_id`. Bila klien mulai ulang dari nol
  (cabang `old` di pre-create), nilai ditimpa.
- `uploaded_at`: saat pre-finish menandai `uploaded: true`.

| Kunci | Arti |
|---|---|
| `uploads` | daftar per video: `role`, `kind`, `size_bytes`, `seconds`, `mbps` |
| `total_bytes` | jumlah ukuran |
| `seconds` | dari `upload_started_at` paling awal sampai `uploaded_at` paling akhir |
| `mbps` | `total_bytes * 8 / seconds / 1e6`, label "throughput unggah efektif" |

Makna yang harus ditulis di tampilan: termasuk jeda bila unggahan terputus lalu dilanjutkan, dan
diukur di server (sampai berkas tersimpan di PC lab, lewat Cloudflare). Job CLI (`size` null):
`network = null`, reason `"cli_job"`. Job lama: reason `"not_recorded"`.

### 4.3 Proses (`processing`), arahan Bu Evi

| Kunci | Arti |
|---|---|
| `queue_s` | `started_at - max(uploaded_at)`; job CLI: `started_at - created_at`; tanpa `uploaded_at`: `null` |
| `gpu_wait_s` | lama tahap `gpu_wait` (menunggu `gpu_lock`) |
| `total_s` | `finished_at - started_at` |
| `stage_seconds` | lama tiap tahap worker (`gpu_wait`, `extract`, `build`, `inspect`, `register`, `align`, `gate`) |
| `map_stage_seconds` | salinan `run.t_map_s` (ekstraksi fitur, pencocokan, rekonstruksi) |
| `env` | salinan `run.env` (GPU, CPU, commit, versi torch/pycolmap/hloc) |

`stage_seconds` dicatat oleh `process()` sendiri: setiap `jobs.set_stage` di fungsi itu juga menulis
waktu monoton ke dict lokal. `total_s` dihitung sesudah `jobs.finish`/`jobs.reject` (atau dari waktu
sekarang tepat sebelum keduanya; pilih satu dan uji). Job lama: `stage_seconds` dan `gpu_wait_s` null.

### 4.4 Kualitas peta (`quality`), tambahan

| Kunci | Sumber |
|---|---|
| `registered`, `images` | `run.map_registered`, `run.map_images` |
| `points3d` | `run.map_points3D` |
| `mean_reprojection_error_px` | `pycolmap.Reconstruction.compute_mean_reprojection_error()` dari `run/sfm` |
| `mean_track_length` | `compute_mean_track_length()` |
| `mean_observations_per_image` | `compute_mean_observations_per_reg_image()` |
| `parts` | jumlah `inspect.parts` (peta pecah jadi berapa bagian) |
| `align` | `status`, `residual_median_m`, `residual_max_m`, `scale` dari `summary.align` |
| `gate` | keputusan gerbang dari `summary.gate` |
| `params` | `features`, `matcher`, `max_keypoints`, `resize_max`, `sequential_pairs`, `detection_threshold` dari `run` |

Model SfM dimuat sekali; nama metode pycolmap harus diverifikasi terhadap versi terpasang
(`pycolmap.__version__` di `env`) sebelum dipakai.

## 5. Pemakaian peta (hidup, tidak dibekukan)

Endpoint baru `GET /api/jobs/{id}/usage`, hanya untuk staf (dependensi `User` seperti `GET /api/jobs`),
tidak untuk token aplikasi capture walau `GET /api/jobs/{id}` mengizinkannya. Untuk job dengan
versi peta, ambil baris `localize_request` dengan `area_id` job dan `map_version` = nomor versi.
Hasil dipisah dua kelompok menurut kolom `candidate` (keputusan Claude): `served` (`candidate = false`,
lalu lintas nyata ke `/localize` saat versi ini diterbitkan) dan `candidate` (uji versi kandidat lewat
`/versions/{id}/localize`). Tiap kelompok: `requests`, `ok_ratio` (`result == "ok"`), `wall_s_p50`,
`wall_s_p95`, `inliers_median`, `first_at`, `last_at`. Nol request = statistik null, `requests: 0`.
Angka jurnal untuk pemakaian nyata hanya dari kelompok `served`. Hitung di Python dari kolom
yang dipilih (jumlah baris dibatasi retensi log 50.000).

Tampilan memberi label "diperbarui saat halaman dibuka". Pemakaian tidak ikut CSV (keputusan Claude:
butuh satu panggilan per job atau endpoint gabungan baru; tambahkan bila jurnal memerlukannya).

## 6. Isi ulang job lama

Perintah `python -m server.manage report [--job N] [--force]`, mengikuti pola `thumbs`:
- Memproses job `done` dan job ditolak gerbang yang folder petanya masih ada.
- Lewati job yang sudah punya `report.version` sama, kecuali `--force`.
- Nilai yang datanya sudah hilang = null dengan reason, bukan perkiraan.
- Nilai yang hanya bisa dicatat saat job berjalan (`processing.stage_seconds`, `processing.gpu_wait_s`)
  disalin dari kartu lama saat menghitung ulang, tidak ditimpa null (keputusan Claude). Nilai yang
  bisa dihitung ulang dari disk atau DB dihitung ulang. Dengan begitu `--force` dan kenaikan `version`
  tidak menghapus data yang tidak bisa didapat lagi.
- Mencetak jumlah dibuat dan dilewati.
- Dijalankan di PC lab hanya dengan izin Bagus.

## 7. Web

Halaman job (`web/app/job/page.tsx`): panel "Laporan scan" dengan empat kelompok (Rekaman, Jaringan,
Proses, Kualitas peta) dan satu panel terpisah "Pemakaian peta". Setiap metrik turunan punya keterangan
cara hitung (misalnya "jejak lintasan, radius 1 m, grid 0,25 m"). `null` tampil "tidak tercatat" dengan
alasannya. Panel yang sudah ada (status eksekusi, tahap, penyelarasan) tetap; jangan menggandakan
angka yang sama dengan sumber berbeda.

Sketsa:

```
Laporan scan                                   rumus v1, dihitung 25 Nov 14.02
Rekaman     ARCore | 182 foto, 2 segmen | 6 mnt 40 dtk | lintasan 96,4 m
            jejak 212 m2 (radius 1 m, grid 0,25 m, kerangka SfM) | 0,24 m/dtk | tracking hilang 2x | TECNO KL7
Jaringan    412 MB dalam 3 mnt 05 dtk | 17,8 Mbps (efektif, diukur di server)
Proses      antre 12 dtk | tunggu GPU 0 dtk | total 18 mnt 31 dtk | RTX ..., commit 14085e0
Kualitas    180/182 terdaftar | 41.203 titik | reproyeksi 0,92 px | 1 bagian | selaras 0,11 m
Pemakaian peta (diperbarui saat dibuka)
            dilayani: 240 request | 92 % ok | p50 1,4 dtk | p95 2,9 dtk
            uji kandidat: 12 request | 75 % ok | p50 1,2 dtk | p95 1,9 dtk
```

Halaman daftar job (`web/app/jobs/page.tsx`): tombol "Unduh CSV" yang membuat berkas di browser dari
data job yang sudah dimuat (tanpa endpoint baru). `GET /api/jobs` dibatasi `limit` maksimal 200;
CSV memuat job yang tampil dan berkasnya menyebut jumlah baris, jadi jangan diklaim "semua job". Kolom tetap: id, area, status, tanggal, semua angka
skalar kartu (nama kolom = jalur kunci, misalnya `recording.duration_s`), `report.version`. Tabel
pembanding di layar memakai subset kolom utama; unit dan cara hitung di baris judul.

Teks UI lewat `web/lib/i18n/en.ts` dan `id.ts`. Format angka mengikuti locale yang sudah ada.

## 8. Pengujian

Server (pytest, berkas yang sudah ada diperluas atau berkas baru `tests/test_scan_report.py`):
- Durasi multi-segmen tidak menghitung jeda antarsegmen.
- Panjang lintasan mengabaikan sumbu Y dan tidak menyambung antarsegmen.
- Luas jejak: lintasan lurus 10 m dengan radius 1 m mendekati `10*2 + pi*1²` dalam toleransi satu
  lapis sel; lintasan bolak-balik di jalur sama tidak menggandakan luas.
- Dua segmen terpisah 50 m di kerangka ARCore: `arcore_per_segment` menjumlah luas per segmen;
  dengan pusat SfM terselaras dipakai `aligned_sfm`.
- `meta.json` ada (ambil `tracking_losses`, `device_model`) dan tidak ada (null, reason `no_meta`).
- `height_range_m`, foto tunggal, `frames.jsonl` kosong.
- Pemakaian: baris `candidate` true dan false masuk kelompok berbeda.
- CLI `--force` mempertahankan `stage_seconds` dan `gpu_wait_s` dari kartu lama.
- `video_meta`: durasi dari `mvhd` versi 0 dan 1 (pakai `tests/mp4_builder.py`).
- Hook upload: pre-create menulis `upload_started_at`, mulai ulang menimpanya, pre-finish menulis
  `uploaded_at`; throughput dan reason `cli_job`/`not_recorded`.
- Worker: kartu ada di job `done` dan job ditolak gerbang; error di perhitungan laporan tidak
  menggagalkan job; `stage_seconds` berisi tahap yang dilalui.
- Endpoint pemakaian: penyaringan area dan versi, nol request, p50/p95.
- CLI `report`: lewati versi sama, `--force` menghitung ulang, data hilang jadi null.

Web: belum ada test runner. Verifikasi dengan `npm run build`, lint, dan cek manual di browser
terhadap job nyata (satu job capture ARCore, satu job video lama).

## 9. Diputuskan oleh siapa

Diputuskan Bagus: pendekatan A; kartu laporan, bukan log; data tambahan selain arahan Bu Evi ikut
ditampilkan; tidak menambah puncak VRAM, model HP, identitas.

Usulan Claude (boleh dikoreksi): definisi luas = jejak lintasan radius 1 m grid 0,25 m; jaringan =
throughput unggah efektif dari pre-create sampai pre-finish; pemakaian peta sebagai endpoint per job;
CSV dibuat di browser tanpa kolom pemakaian; luas dan tinggi di kerangka SfM terselaras bila ada,
selain itu per segmen ARCore; tracking dan model HP dari `meta.json`; pemakaian dipisah `served` dan
`candidate`; hitung ulang mempertahankan nilai yang hanya tercatat saat job berjalan.

Terbuka ke Bu Evi: definisi luas area dan kecepatan jaringan yang dia maksud. Desain menyimpan metode
dan parameter, jadi definisi lain bisa ditambah sebagai `version` 2 tanpa membuang kartu lama.

## 10. Diserahkan ke pembangun

Letak modul (saran: `server/scan_report.py` berisi fungsi murni, dipanggil dari `worker.process`),
nama komponen web, susunan kolom tabel pembanding, dan cara mengambil persentil.
