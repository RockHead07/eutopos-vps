# Pengukuran pemakaian CPU dan GPU per konfigurasi feature dan matcher

Status: skrip selesai dan masuk `main` (PR #54, `spike/bench_usage.py`), **belum dijalankan di PC lab**
(2026-10-07). Bagian 7 diisi setelah pengukuran. Keputusan di bagian 3 ditetapkan **sebelum ada hasil**, supaya
tidak disetel sesudah melihat angka.

## 1. Permintaan

Pembimbing 2 (Bu Evi), 7 Oktober 2026, parafrase:

- Buat komparasi penggunaan GPU dan CPU untuk masing-masing konfigurasi yang sedang dibahas, supaya tahu pola
  pemakaian CPU dan GPU tiap metode, "sebanyak apa".
- Cek pros dan cons-nya.
- Gambar uji: sekitar 30 gambar yang bervariasi ("disampling 30an tetapi yang variance"), termasuk gambar
  ber-noise, dan noise-nya dibangkitkan dengan OpenCV.
- Laporan seterusnya lewat grup Bimbingan PA.

Tidak ada permintaan melatih model: ALIKED, LightGlue, dan MegaLoc sudah terlatih dan hanya dijalankan, sedangkan
SIFT tidak butuh pelatihan.

Konteks dari bimbingan 6 Oktober: ukuran "detail" feature matching menurut pembimbing adalah jumlah point cloud
(`docs/sift-vs-aliked.md` bagian 8), dan ia meminta uji di lorong yang minim fitur (belum ada rekamannya).

## 2. Pertanyaan yang dijawab

1. Berapa besar pemakaian CPU dan GPU tiap konfigurasi, dan apa pola per tahap (ekstraksi dan pencocokan)?
2. Seberapa jauh GPU mempercepat tiap konfigurasi, dan mana yang tidak bisa memakai GPU sama sekali?
3. Bagaimana kualitas pencocokan (keypoint, match, inlier) berubah ketika gambar ber-noise?
4. Dari angka itu, apa untung dan rugi masing-masing, termasuk untuk target server tanpa GPU.

Pertanyaan 4 hanya boleh dijawab dari angka pertanyaan 1 sampai 3 dan sumber primer, bukan dari perasaan.

## 3. Rancangan (ditetapkan sebelum pengukuran)

**Konfigurasi** (sama dengan baris pada `docs/sift-vs-aliked.md` bagian 6 dan 8):

| Nama | Feature | Matcher | Keypoint maks | Sisi terpanjang gambar |
|---|---|---|---|---|
| `aliked-lightglue` | ALIKED | LightGlue | 1024 | 1024 |
| `sift-lightglue` | SIFT | LightGlue | 1024 | 1024 |
| `aliked-nn` | ALIKED | nearest neighbor + ratio test 0,8 | 1024 | 1024 |
| `sift-nn` | SIFT | nearest neighbor + ratio test 0,8 | 1024 | 1024 |
| `sift-colmap-default` | SIFT | nearest neighbor + ratio test 0,8 | 8192 | 2560 |

**Perangkat:** GPU dan CPU untuk tiap konfigurasi. CPU dipaksa dengan menyembunyikan GPU dari proses anak
(`CUDA_VISIBLE_DEVICES=""`). Perangkat yang tidak tersedia dilewati, tidak diam-diam diganti.

**Gambar:** 15 pasangan frame berjarak 2 frame (sekitar 1 detik, karena frame diekstrak 2 fps), jadi 30 gambar,
dari 402 frame lorong lantai 10 (job 2). Satu pasangan per irisan rute (tersebar di sepanjang rute), dan
ketajamannya (variance Laplacian) sengaja disebar dari yang paling buram sampai paling tajam. "Variance" dibaca
dua arti sekaligus: beragam, dan variance ketajaman yang berbeda-beda. Seed 7, hasil tetap.

**Variasi noise** (OpenCV, kedua gambar dalam pasangan diberi realisasi noise yang berbeda):

| Variasi | Noise |
|---|---|
| `clean` | tanpa noise (tetap disimpan ulang lewat encoder JPEG yang sama) |
| `gauss10`, `gauss25`, `gauss50` | Gaussian, sigma 10, 25, 50 (`cv2.randn`), dipotong ke 0 sampai 255 |
| `sp2` | salt-and-pepper, 2% piksel (`cv2.randu`), sama banyak hitam dan putih |

**Ulangan:** 3 per kombinasi, dilaporkan median dan rentang. Satu putaran pemanasan (tidak dicatat) di awal tiap
proses.

## 4. Cara mengukur

Tiap tahap (ekstraksi fitur, pencocokan) diukur terpisah lewat `extract_features.main` dan
`match_features.main` dari hloc, jalur yang sama dengan `spike/run.py`.

| Besaran | Cara |
|---|---|
| Waktu dinding | `time.perf_counter()` di sekitar tahap, dengan sinkronisasi CUDA |
| CPU | waktu CPU proses ditambah proses anak yang sudah selesai (`RUSAGE_CHILDREN`), dibagi waktu dinding = rata-rata inti terpakai |
| RSS | `/proc/self/status` setelah tahap (nilai saat itu, bukan puncak) |
| VRAM puncak | `torch.cuda.max_memory_allocated()` per tahap |
| Utilisasi GPU | cuplikan `nvidia-smi` tiap 200 ms, rata-rata dan puncak di dalam jendela tahap; utilisasi GPU saat diam dicatat sebagai pembanding |
| Kualitas | keypoint per gambar, match per pasangan, inlier setelah `cv2.findFundamentalMat` (RANSAC, 1 px) |

**Pelajaran dari uji kecil di laptop:** pekerja DataLoader hloc memuat gambar di proses terpisah. `process_time()`
saja mencatat 0,01 inti, padahal pekerjanya memakai 1,08 inti (diukur di container PC lab), jadi pemakaian CPU
ekstraksi terlihat jauh terlalu kecil. Karena itu proses anak dihitung. Di Windows hal ini tidak tersedia, jadi
angka hanya dianggap sah dari mesin Linux.

## 5. Batas yang diakui

- **SIFT hanya jalan di CPU** selama `pycolmap` tidak dibangun dengan CUDA (`pycolmap.has_cuda` bernilai `False`
  di instalasi kita). Di tabel tertulis "tidak tersedia di GPU", bukan angka. SIFT dengan CUDA belum diuji.
- **Waktu tahap sudah termasuk memuat model**, karena hloc memuatnya di setiap panggilan. Laporan memberi juga waktu
  per item.
- **GPU dipakai bersama layanan `api`** yang sedang diam (sekitar 2,2 GiB VRAM terpakai oleh modelnya). Pengukuran
  dijalankan saat tidak ada pembangunan peta atau unggahan, dan utilisasi diam dilaporkan.
- **Noise sintetis** bukan noise sensor ponsel asli, dan satu sumber gambar (satu lorong, satu ponsel).
- **15 pasangan, 3 ulangan, satu mesin** (i7-10700K 16 thread, RTX 3070 8 GB, 15 GB RAM). Tidak menggantikan
  pengukuran di server instansi (2 vCPU), yang tetap satu-satunya yang boleh diklaim untuk "server instansi tanpa GPU".
- Pengukuran ini **tidak mengukur akurasi dalam meter**.
- Jumlah titik tidak otomatis berarti lebih akurat.

## 6. Cara menjalankan

Di PC lab, dari `~/eutopos-vps/deploy`, di container worker (`/app`, `/data` bisa ditulis, `nvidia-smi` ada di
`/usr/bin`). Pastikan tidak ada job `queued` atau `running`:

```bash
docker compose exec -T worker python -m server.manage jobs
docker compose exec -T worker python spike/bench_usage.py prepare \
    --frames /data/jobs/2/dataset/mapping --out /data/experiments/usage
docker compose exec -T worker sh -c 'nohup python spike/bench_usage.py run \
    --out /data/experiments/usage --devices gpu cpu --repeats 3 \
    > /data/experiments/usage/run.log 2>&1 &'
# setelah selesai
docker compose exec -T worker python spike/bench_usage.py report --out /data/experiments/usage
```

Perkiraan waktu 1,5 sampai 2 jam, dari angka laptop (belum diukur di PC lab). Hasil per konfigurasi ditulis ke
`results/*.jsonl` begitu selesai, jadi proses yang dihentikan tetap meninggalkan hasil parsial.

## 7. Hasil

Dijalankan 2026-10-07 di PC lab (i7-10700K, RTX 3070 8 GB, 15 GB RAM; PyTorch 2.14.0+cu130 memakai 8 thread;
`pycolmap` tanpa CUDA). Rancangan di bagian 3 tidak diubah setelah melihat angka. Berkas mentah (`results/*.jsonl`,
`summary.csv`, `summary.md`) ada di `/data/experiments/usage` di PC lab dan di `outputs/usage/` di laptop (tidak masuk git).

### 7.1 Kejadian saat menjalankan (dicatat apa adanya)

- Run pertama dimulai 15:15 WIB. **WSL di PC lab restart sendiri pukul 15:35** (penyebab belum diketahui; bukan deploy,
  bukan kehabisan memori), semua container ikut mati, dan run terputus. Enam hasil sudah lengkap sebelum itu.
- Percobaan lanjut pertama gagal karena berkas fitur `.h5` yang setengah tertulis tertinggal di
  `work/aliked-nn-cpu/` (`file signature not found`). Setelah berkas itu dihapus, `aliked-nn` di CPU diulang dari awal
  dan tiga konfigurasi sisanya dijalankan. Jadi **`aliked-nn` di CPU dijalankan setelah restart, bukan dalam satu run
  yang sama dengan yang lain**; mesin dan kondisinya sama.
- Sepuluh berkas hasil (lima konfigurasi, GPU dan CPU) masing-masing lengkap: satu baris meta dan 30 pengukuran.

### 7.2 Waktu dan pemakaian sumber daya (gambar bersih, median dari 3 ulangan)

30 gambar untuk extraction, 15 pasang untuk matching.

| Konfigurasi | Perangkat | Extraction (s) | Matching (s) | Total (s) | CPU time (core-seconds) | Inti CPU rata-rata (ext / match) | GPU rata-rata % (ext / match) | VRAM puncak (MB) |
|---|---|---|---|---|---|---|---|---|
| ALIKED + LightGlue | GPU | 1,1 | 0,68 | 1,7 | 3,9 | 2,2 / 2,2 | 32 / 22 | 913 |
| ALIKED + LightGlue | CPU | 17,8 | 2,57 | 20,3 | 109,6 | 5,1 / 7,7 | - | - |
| ALIKED + nearest neighbor | GPU | 1,1 | 0,36 | 1,5 | 3,3 | 2,1 / 2,4 | 29 / 18 | 913 |
| ALIKED + nearest neighbor | CPU | 19,0 | 0,27 | 19,3 | 90,2 | 4,7 / 4,0 | - | - |
| SIFT + LightGlue | GPU | 8,9 (tetap di CPU) | 0,87 | 9,8 | 11,9 | 1,2 / 1,9 | tidak dipakai / 27 | 104 |
| SIFT + LightGlue | CPU | 8,9 | 3,25 | 12,1 | 32,8 | 1,1 / 7,0 | - | - |
| SIFT + nearest neighbor | GPU | 9,8 (tetap di CPU) | 0,42 | 10,2 | 11,6 | 1,1 / 2,5 | tidak dipakai / 14 | 23 |
| SIFT + nearest neighbor | CPU | 9,4 | 0,29 | 9,7 | 11,2 | 1,1 / 3,8 | - | - |
| SIFT bawaan COLMAP (8.192 keypoint, 2.560 px) | GPU | 66,9 (tetap di CPU) | 0,58 | 67,5 | 69,3 | 1,0 / 2,4 | tidak dipakai / 47 | 406 |
| SIFT bawaan COLMAP (8.192 keypoint, 2.560 px) | CPU | 68,2 | 0,89 | 69,1 | 73,9 | 1,0 / 5,6 | - | - |

Catatan: pada baris SIFT di GPU, extraction tetap berjalan di CPU karena `pycolmap.has_cuda` bernilai `False`; hanya
matching yang memakai GPU. Waktu tahap sudah termasuk memuat model. GPU dipakai bersama layanan `api` yang sedang diam.

### 7.3 Ketahanan terhadap noise (rata-rata inlier per pasangan)

Noise buatan OpenCV: Gaussian dengan sigma 10, 25, 50 (`cv2.randn`) dan salt and pepper 2% piksel. Angka CPU dan GPU
hampir sama (selisih rata-rata kurang dari 5 inlier); tabel memakai hasil GPU.

| Konfigurasi | Bersih | Gaussian 10 | Gaussian 25 | Gaussian 50 | Salt and pepper 2% | Tersisa di Gaussian 50 | Tersisa di salt and pepper |
|---|---|---|---|---|---|---|---|
| ALIKED + LightGlue | 253 | 255 | 226 | 126 | 167 | 50% | 66% |
| ALIKED + nearest neighbor | 128 | 126 | 108 | 70 | 90 | 55% | 70% |
| SIFT + LightGlue | 168 | 176 | 138 | 97 | 137 | 57% | 81% |
| SIFT + nearest neighbor | 129 | 107 | 66 | 43 | 63 | 34% | 49% |
| SIFT bawaan COLMAP (8.192 keypoint, 2.560 px) | 338 | 185 | 85 | 40 | 82 | 12% | 24% |

### 7.4 Yang terbaca dari angka

- **ALIKED mendapat paling banyak dari GPU.** Extraction 30 gambar 1,05 s di GPU dibanding 17,8 s di CPU (sekitar 17 kali),
  dan di CPU ia memakai sekitar 5 dari 8 inti (110 core-seconds untuk satu rangkaian dengan LightGlue).
- **SIFT di instalasi kita tidak ikut dipercepat GPU.** Extraction sama saja (sekitar 0,30 s per gambar untuk 1.024
  keypoint, satu inti). Yang berubah hanya matching LightGlue (3,25 s di CPU, 0,87 s di GPU). Total CPU SIFT + LightGlue 33
  core-seconds, dan SIFT + nearest neighbor hanya 11.
- **Matching nearest neighbor dengan 1.024 keypoint lebih cepat di CPU** (0,27 s dan 0,29 s) daripada di GPU (0,36 s dan
  0,42 s): pekerjaannya terlalu kecil untuk menutup biaya memindahkan data ke GPU. Dengan 8.192 keypoint GPU kembali
  lebih cepat (0,58 s dibanding 0,89 s). LightGlue 3,7 sampai 3,8 kali lebih cepat di GPU.
- **SIFT bawaan COLMAP (8.192 keypoint, 2.560 px) 7,7 kali lebih lambat** daripada SIFT 1.024 keypoint (68 s untuk 30 gambar),
  paling banyak inlier pada gambar bersih (338) tetapi paling rapuh: tersisa 12% di Gaussian 50 dan 24% di salt and pepper,
  dan waktu extraction naik sampai 94 s di bawah noise.
- **Noise menambah keypoint tetapi mengurangi inlier**: keypoint SIFT 737 pada gambar bersih menjadi 1.420 di Gaussian 50,
  sedangkan inlier turun. Jumlah keypoint tidak sama dengan kualitas.
- **ALIKED + LightGlue paling banyak inlier di antara setelan 1.024 keypoint** (253 bersih, 126 di Gaussian 50), tetapi
  persentase yang bertahan sedikit di bawah SIFT + LightGlue (50% dibanding 57%; salt and pepper 66% dibanding 81%).
- Proses GPU memakai RAM lebih besar (RSS 1,3 sampai 2,3 GB dibanding 0,7 sampai 1,1 GB di CPU); penyebabnya diduga
  CUDA context tetapi belum diuji, dan RSS dicatat di akhir tahap, bukan puncak.

### 7.5 Yang tidak boleh disimpulkan dari sini

Bagian 5 tetap berlaku: satu mesin dengan GPU dan 8 thread, 15 pasang, noise sintetis, belum diukur di server instansi
2 vCPU. Karena itu **jangan** menulis "SIFT cocok untuk server tanpa GPU" atau menyebut angka CPU di atas sebagai latensi
server. Inti-detik memberi gambaran beban relatif per konfigurasi, bukan waktu di 2 vCPU.

## 8. Cara melaporkan

Tabel putih polos (tanpa warna) di grup Bimbingan PA: pemakaian per konfigurasi dan perangkat, ketahanan terhadap
noise, lalu pros dan cons yang ditulis dari angka di atas. Kesimpulan yang melampaui data (misalnya "SIFT lebih
cocok untuk server tanpa GPU") tidak ditulis sebagai fakta.
