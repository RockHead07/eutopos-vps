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

**Variasi luminance** (ditambahkan 2026-10-11 atas permintaan Bu Evi, 8 Okt: kasus sore dan malam; tingkat
ditetapkan sebelum pengukuran, bukan disetel sesudahnya). Gambar digelapkan pada cahaya linear (`dim()` di
`spike/bench_usage.py`), bukan dengan mengalikan nilai piksel: cahaya yang tersisa `g` berarti nilai piksel
dikali `g^(1/2,2)`, dengan gamma 2,2 sebagai pendekatan kurva sRGB. Cara ini deterministik (tanpa seed) dan tidak
memakai noise.

| Variasi | Isi | Setara | Kecerahan rata-rata* |
|---|---|---|---|
| `dim50` | cahaya 50% | turun 1 stop | 90,6 |
| `dim25` | cahaya 25% | turun 2 stop | 66,1 |
| `dim10` | cahaya 10% | turun sekitar 3,3 stop | 43,6 |
| `dim25-gauss10` | `dim25`, lalu Gaussian sigma 10 | gelap dan berisik | 66,2 |

*Rata-rata abu-abu 0 sampai 255 atas 30 gambar; `clean` 124,1. Dari `manifest.json` (`luma`) hasil `prepare` di PC lab
(frame job 2, pasangan yang sama dengan 7 Okt), bukan dari rumus. Noise pada `dim25-gauss10` ditambahkan
setelah redup karena sensor makin berisik saat gelap; sigma 10 sama dengan `gauss10`, jadi pengaruh noise saja dan
redup saja bisa dipisahkan dari kombinasinya. Varian baru ditaruh di belakang daftar supaya seed noise varian lama
(indeks varian ikut menentukan seed) dan gambar ber-noise di laporan 7 Okt tidak berubah.

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
- **Redup sintetis** tidak meniru exposure otomatis, motion blur akibat waktu paparan yang memanjang, atau
  perubahan warna lampu sore dan malam. Hasilnya menjawab "bagaimana pencocokan bila gambar lebih gelap",
  bukan "bagaimana di malam hari". Rekaman asli sore dan malam di gedung tetap diperlukan sebagai validasi.
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

**Pengukuran luminance** memakai folder keluaran sendiri dan frame serta seed yang sama (pasangan sama persis).
`child` menghapus `results/<konfigurasi>-<perangkat>.jsonl` miliknya saat mulai, jadi menjalankan sebagian
varian di folder lama akan menghapus hasil 7 Okt. `clean` ikut dijalankan lagi sebagai pembanding pada sesi yang
sama:

```bash
docker compose exec -T worker python spike/bench_usage.py prepare     --frames /data/jobs/2/dataset/mapping --out /data/experiments/usage-luminance
docker compose exec -T worker sh -c 'nohup python spike/bench_usage.py run     --out /data/experiments/usage-luminance --devices gpu cpu --repeats 3     --variants clean dim50 dim25 dim10 dim25-gauss10     > /data/experiments/usage-luminance/run.log 2>&1 &'
docker compose exec -T worker python spike/bench_usage.py report --out /data/experiments/usage-luminance
```

Lima variasi, sama banyak dengan pengukuran 7 Okt, jadi lama pengerjaannya diperkirakan serupa. Berkas `.h5`
sisa proses yang terhenti kini dihapus di awal tiap ulangan.

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

### 7.6 Variasi luminance (dijalankan 2026-10-11)

Dijalankan 15:33 sampai sekitar 16:30 WIB di PC lab, dengan kode `5dcd5bc` (PR #66), lima konfigurasi, GPU dan CPU,
3 ulangan, lima kondisi (`clean` dijalankan ulang sebagai pembanding sesi yang sama). Rancangan di bagian 3 tidak diubah
setelah melihat angka. Berkas mentah ada di `/data/experiments/usage-luminance` di PC lab dan `outputs/usage-luminance/`
di laptop (tidak masuk git). `clean` **identik** dengan sesi 7 Okt pada kelima konfigurasi (selisih inlier 0,0), jadi hasilnya
dapat dibandingkan langsung. Selisih inlier GPU dan CPU paling besar 6,4 (sekitar 4%); tabel memakai hasil GPU.

**Inlier rata-rata per pasangan (dan persentase terhadap gambar bersih)**

| Konfigurasi | Bersih | Cahaya 50% | Cahaya 25% | Cahaya 10% | Cahaya 25% + noise sigma 10 |
|---|---|---|---|---|---|
| ALIKED + LightGlue | 253 | 243 (96,0%) | 216 (85,5%) | 181 (71,4%) | 220 (86,7%) |
| ALIKED + nearest neighbor | 128 | 116 (90,1%) | 105 (81,5%) | 83 (64,4%) | 98 (76,6%) |
| SIFT + LightGlue | 168 | 148 (88,0%) | 117 (69,5%) | 81 (48,0%) | 121 (71,9%) |
| SIFT + nearest neighbor | 129 | 110 (85,2%) | 89 (69,0%) | 65 (50,8%) | 72 (56,2%) |
| SIFT bawaan COLMAP (8.192 keypoint, 2.560 px) | 338 | 270 (79,7%) | 209 (61,7%) | 157 (46,4%) | 100 (29,6%) |

Yang terbaca dari angka:

- **Urutan ketahanan sama di setiap tingkat redup**: ALIKED + LightGlue paling baik (71% pada cahaya 10%), lalu ALIKED +
  nearest neighbor (64%), lalu dua konfigurasi SIFT (48% dan 51%), dan SIFT bawaan COLMAP (46%). Dalam angka mutlak, ALIKED +
  LightGlue pada cahaya 10% (181 inlier) masih di atas SIFT bawaan COLMAP (157).
- **Saat gelap, ekstraktor yang paling menentukan**: SIFT menjadi ALIKED dengan LightGlue menambah retensi 23 poin pada
  cahaya 10% (48,0% menjadi 71,4%), sedangkan nearest neighbor menjadi LightGlue menambah 7 poin pada ALIKED dan mengurangi 3
  poin pada SIFT (inlier mutlaknya tetap lebih banyak, 65 menjadi 81). Ini berbeda dari 7.4 untuk noise (matcher lebih
  menentukan); keduanya berlaku untuk gangguan masing-masing.
- **Redup mengurangi jumlah fitur, bukan kemurnian pencocokan**: rasio inlier terhadap match hampir datar (ALIKED +
  LightGlue 65,0% pada bersih dan 68,4% pada cahaya 10%), sedangkan match turun (390 menjadi 264) dan keypoint turun (ALIKED
  644 menjadi 440, SIFT 737 menjadi 329).
- **Noise berat umumnya lebih merusak daripada gelap berat, tidak untuk semua konfigurasi**: retensi pada Gaussian 50
  (7.3) lebih rendah daripada pada cahaya 10% untuk empat dari lima konfigurasi; pengecualiannya SIFT + LightGlue (57,4%
  lawan 48,0%). Tingkat keparahan kedua gangguan tidak setara, jadi ini gambaran, bukan peringkat.
- **Gelap dan noise hampir saling mengalikan**: retensi cahaya 25% dikali retensi Gaussian 10 (7.3) mendekati retensi
  gabungan (ALIKED + LightGlue 86,2% diperkirakan dan 86,7% terukur; SIFT bawaan COLMAP 33,7% dan 29,6%). Pengamatan atas
  lima konfigurasi, bukan model.
- **Jumlah keypoint menyesatkan saat ada noise**: keypoint SIFT naik pada cahaya 25% dengan noise (737 menjadi 838; COLMAP
  3.324 menjadi 4.472) sementara rasio inlier turun (SIFT + LightGlue 53,6% menjadi 39,4%).
- **Gelap tidak mengubah kebutuhan sumber daya secara berarti**: ekstraksi ALIKED di GPU 1,05 s (bersih) dan 1,02 s (cahaya
  10%), di CPU 17,9 s dan 17,7 s. Ekstraksi SIFT sedikit lebih cepat pada gambar redup (COLMAP bawaan 64,3 s menjadi 59,0 s)
  dan matching LightGlue di CPU lebih cepat karena keypoint lebih sedikit (SIFT + LightGlue 3,16 s menjadi 1,54 s).
- **Satu anomali, penyebabnya dugaan**: pada redup berisik ekstraksi ALIKED di GPU naik sekitar 36% (1,05 s menjadi 1,43 s),
  tidak di CPU. Berkas JPEG kondisi itu 55 MB, sedangkan cahaya 25% tanpa noise 12 MB (sekitar 4,5 kali). Dugaan: dekode
  berkas lebih besar. Belum diuji.

**Yang tidak boleh disimpulkan dari sini** (bagian 5 dan 7.5 tetap berlaku):

- Inlier mengukur kontinuitas pencocokan fitur, **bukan akurasi lokalisasi dalam meter** (tujuan 4 belum diukur).
- `summary.csv` hanya menyimpan rata-rata atas 15 pasangan: tidak ada sebaran, tidak ada hitungan pasangan di bawah ambang
  50 inlier, tidak ada uji kemaknaan. Selisih kecil antar konfigurasi (misalnya 48,0% dan 50,8%) bukan urutan.
- Redup sintetis bukan malam hari: tidak meniru exposure otomatis, motion blur dari waktu paparan panjang, noise sensor yang
  bergantung sinyal, atau perubahan warna lampu. Rekaman asli sore dan malam tetap diperlukan sebagai validasi.
- Satu lorong, satu ponsel, 15 pasangan, satu mesin; gambar redup berasal dari frame yang sama dengan gambar bersih.

Tindak lanjut yang diusulkan: simpan inlier per pasangan di `bench_usage.py` (sebaran dan hitungan di bawah ambang),
uji dugaan JPEG dengan PNG, dan rekaman asli sore dan malam.

## 8. Cara melaporkan

Tabel putih polos (tanpa warna) di grup Bimbingan PA: pemakaian per konfigurasi dan perangkat, ketahanan terhadap
noise, lalu pros dan cons yang ditulis dari angka di atas. Kesimpulan yang melampaui data (misalnya "SIFT lebih
cocok untuk server tanpa GPU") tidak ditulis sebagai fakta.
