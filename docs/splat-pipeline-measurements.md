# Pengukuran pipeline splat otomatis

Dua latihan penuh lewat pipeline (`splat-worker`, image `Dockerfile.splat`) pada PC lab, 10 dan 11 Nov 2026. Perangkat:
RTX 3070 8 GB, WSL2, RAM sekitar 16 GB, 16 CPU. Data: versi peta lantai 10 (`floor10` v1), 401 dari 402 frame
terdaftar di model SfM (24.401 titik), disalin dari data produksi dan dilatih di database dan folder sementara
(bukan data produksi). Pelatihan 30.000 langkah, `min_opacity` 0,02, `--test-every` 8 (bawaan pelatih).
Layanan produksi (`api`, `worker`, lokalisasi di GPU yang sama) tetap berjalan selama pengujian.

## Hasil

| Ukuran | Latihan 1 (10 Nov) | Latihan 2 (11 Nov) | Acuan manual (3 Nov) |
|---|---|---|---|
| Total pipeline | 942 s | 966 s | |
| Pelatihan | 874,7 s | 868,0 s | 939 s |
| Siapkan data (`prepare`) | 4,3 s | 4,0 s | |
| Tunggu kunci GPU | 0,003 s | 1,2 s | |
| Periksa posisi (`check`) | 1,6 s | 1,4 s | |
| Konversi ke SOG | 2,0 s | 2,0 s | 2,5 s |
| Pangkas L1 | 3,6 s | 3,5 s | |
| Gaussian sebelum, sesudah pangkas | 863.092 menjadi 657.978 (turun 23,8%) | 882.888 menjadi 669.199 (turun 24,2%) | 901.798 |
| Ukuran `scene.sog` sebelum, sesudah | 9.873.255 menjadi 7.698.414 B (turun 22,0%) | 10.117.053 menjadi 7.852.966 B (turun 22,4%) | 10.314.918 menjadi 8.041.393 B |
| `check_ratio` (ambang 0,02) | 0,000208 | 0,000206 | |
| PSNR, SSIM, LPIPS (frame uji) | belum tercatat | 24,614 dB, 0,8812, 0,2747 | 24,886 dB, 0,8862, 0,2750 |

## Sumber daya dan dampak ke produksi

| Ukuran | Latihan 1 | Latihan 2 |
|---|---|---|
| VRAM total puncak (`nvidia-smi`) | 3.397 MiB | 3.321 MiB |
| VRAM produksi sebelum (lokalisasi) | 1.375 MiB | 1.375 MiB |
| VRAM tambahan pelatih | 2.022 MiB | 1.946 MiB |
| Puncak alokasi torch (`peak_mem_gb`) | 1,507 GB (acuan 3 Nov) | 1,393 GB |
| VRAM bebas yang dibaca sebelum melatih | tidak dibaca (kode lama) | 7.098 MiB |
| RAM tersedia, awal dan minimum | 14.008 dan 12.033 MB | 13.951 dan 11.885 MB |
| Disk bebas | 836 menjadi 835 GB | 836 menjadi 835 GB |
| `/health` produksi | 200 pada semua 62 cuplikan (15 s) | 200 pada semua 62 cuplikan (15 s) |
| Pekerjaan peta produksi aktif | 0 | 0 |
| VRAM setelah selesai | kembali 1.375 MiB | kembali 1.375 MiB |

Ambang VRAM bebas sebelum melatih ditetapkan 4.096 MiB (dua kali selisih terukur, dan di bawah 8.192 - 1.375 MiB
yang bebas pada keadaan normal).

## Pembacaan

- Pelatihan mendominasi waktu (sekitar 90%); tahap lain total di bawah 15 detik.
- Pangkas L1 memperkecil berkas sekitar 22% dan Gaussian sekitar 24% pada kedua latihan, sama dengan acuan manual.
- Dua latihan pada data yang sama berbeda sekitar 2% jumlah Gaussian dan 0,3 dB PSNR: pelatihan tidak deterministik.
  Jangan membaca selisih sekecil itu sebagai perbedaan metode.
- Selisih `nvidia-smi` (sekitar 2 GB) lebih besar dari puncak alokasi torch (sekitar 1,4 sampai 1,5 GB) karena konteks
  CUDA dan cache alokator; ambang memakai angka `nvidia-smi`.

## Batas: yang belum terukur

- **Gedung besar.** Hanya 401 frame yang diukur. VRAM dan waktu pada ribuan frame belum diketahui; `packed` atau batas
  frame mungkin perlu.
- **Latensi `/localize` selama pelatihan.** Hanya `/health` yang dipantau (cuplikan 15 detik). Lonjakan VRAM di antara
  dua cuplikan tidak terlihat, dan dampak ke latensi lokalisasi belum diukur.
- **Pose di luar jalur latih** dan floater dekat kamera belum dinilai. Tangkapan layar menunjukkan area kabur di dekat
  kolom dan sisi lantai.
- **Kemampuan `check_ratio` menolak splat yang salah posisi** belum diuji dengan kontrol negatif nyata (ambang 0,02,
  terukur 0,0002).
- **Pita SH tidak ada** (`-H 0`), jadi pantulan tergantung sudut tidak dimodelkan.
- Hasil memakai satu perangkat dan dua latihan; bukan statistik.

## Cara mengulang

Skrip pemantau dan penghitung hash yang dipakai ada di catatan kerja (di luar repo). Intinya: salin salinan data
(`work/jobs/<id>/dataset/mapping` dan `maps/<area>/job-<id>/<run>/sfm`) ke folder sementara, buat database sementara dan
jalankan `alembic -c server/alembic.ini upgrade head`, isi satu `area`, `map_version`, dan `map_job`, antre dengan
`splat_jobs.enqueue`, jalankan kontainer `eutopos-splat-worker` dengan `--gpus all`, `--memory=8g`, dan pantau VRAM,
RAM, disk, serta `/health` selama pelatihan. Jangan memakai database produksi.
