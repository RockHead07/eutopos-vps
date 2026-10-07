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

Belum ada. Diisi setelah pengukuran dijalankan.

## 8. Cara melaporkan

Tabel putih polos (tanpa warna) di grup Bimbingan PA: pemakaian per konfigurasi dan perangkat, ketahanan terhadap
noise, lalu pros dan cons yang ditulis dari angka di atas. Kesimpulan yang melampaui data (misalnya "SIFT lebih
cocok untuk server tanpa GPU") tidak ditulis sebagai fakta.
