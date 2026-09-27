# Rencana Spike: Lokalisasi Visual Satu Koridor

> 🔒 **STATUS: RENCANA. TIDAK DIEKSEKUSI sebelum judul PA di-ACC.** Keputusan pemilik repo, 2026-09-20:
> tidak ada pengembangan sebelum ACC. Dokumen ini hanya menyusun apa yang akan dikerjakan,
> apa yang diukur, dan kapan hasilnya dianggap lolos. Tidak ada kode, unduhan model, atau
> pengukuran yang dijalankan untuk menyusunnya.
>
> Semua **angka ambang, jumlah foto, dan estimasi waktu** di bawah adalah **usulan penyusun**
> (bukan dari sumber). Yang belum disepakati pembimbing ditandai 🟡.
>
> Konteks: `CLAUDE.md` dan `docs/research-paper.md`.


> 🧪 **Uji coba awal sebelum ACC (keputusan 2026-09-25).** Lorong lab lantai 10 gedung PENS pusat,
> dijalankan di laptop (i5-12450HX, RAM 24 GB, tanpa CUDA). Menjawab: pipeline bisa dipasang, berapa
> foto terdaftar di peta, berapa query berhasil dilokalisasi, dan waktu per lokalisasi di CPU laptop.
> **Tidak** menjawab akurasi di area uji resmi maupun latensi di server instansi. Gerbang G0 tetap
> berlaku untuk spike resmi.

## 1. Pertanyaan yang dijawab spike

| # | Pertanyaan | Kenapa penting |
|---|---|---|
| Q1 | Apakah pipeline hloc memberi galat posisi horizontal ≤ 1,0 m pada ≥ 70% foto ponsel di satu koridor PENS? | Ini target di dokumen pengajuan |
| Q2 | Berapa waktu per lokalisasi di tiga tingkat perangkat (lihat 4.3), terutama server instansi? | Angka ini belum ada di sumber mana pun dan menentukan interval koreksi berkala |
| Q3 | Apakah ekstraktor yang lebih ringan (ALIKED, opsional XFeat) menurunkan biaya CPU tanpa merusak akurasi? | Risiko terbesar adalah CPU |
| Q4 | Berapa lama dan berapa RAM untuk membangun peta, dan apakah muat di perangkat yang tersedia? | Peta dibangun offline, tapi harus bisa dilakukan |

## 2. Di luar cakupan spike

Klien Unity, integrasi ARCore, anchoring tool, RAG, avatar, dan uji pengguna. Uji "koreksi berkala
mengurangi drift ARCore" butuh klien, jadi baru setelah spike ini lolos.

## 3. Gerbang G0: sebelum spike boleh mulai

Semua harus terpenuhi:

- [ ] **Judul di-ACC** (MIS).
- [ ] **Izin memotret dan memindai** koridor terpilih (lewat pembimbing). Tentukan koridor dan jamnya.
- [ ] **Jawaban pembimbing** untuk pertanyaan di bagian 9.
- [ ] **Disk kosong yang cukup.** Disk C: PC lab sisa sekitar 56 GiB (88% terpakai), pakai disk lain.
- [ ] **Jadwal PC lab dan server instansi** supaya tidak bentrok dengan pemakai lain (RAM PC lab sedang
      terpakai 13 GiB, server instansi berbagi dengan layanan lain).

**Yang boleh dilakukan sebelum ACC** (bukan pengembangan): mengajukan pertanyaan ke pembimbing,
mengurus izin lokasi, dan mengecek spesifikasi server instansi secara baca-saja (`nproc`, `lscpu`,
`free -h`). Tidak ada yang lain.

## 4. Rancangan

### 4.1 Data

| Data | Isi | Catatan |
|---|---|---|
| **Basis data (untuk peta)** | Foto sepanjang koridor, dua arah, dengan tumpang tindih tinggi dan sedikit variasi lateral | Usulan awal **200 sampai 400 foto**, sesuaikan setelah percobaan pertama. Ponsel yang sama, catat tipe dan pengaturannya |
| **Query (untuk uji)** | Foto lain di **hari atau jam berbeda**, dipegang setinggi dada seperti pengguna sungguhan | Usulan **≥ 40 foto**. Dengan 40 sampel, ketidakpastian pada angka 70% sekitar ±7 poin (satu galat baku), jadi ≥ 50 lebih kokoh |
| **Titik acuan (ground truth)** | Sekitar **20 titik** di lantai dengan koordinat diukur (meteran laser atau pita) terhadap titik asal koridor | Catat ketidakpastian alat |

**Sumber galat acuan yang harus dicatat:** posisi ponsel di tangan tidak persis di atas titik lantai
(kira-kira puluhan sentimeter). Galat ini ikut terhitung, jadi laporkan sebagai batas bawah
ketidakpastian, jangan diabaikan.

**Penyelarasan peta ke koordinat gedung** butuh beberapa titik kontrol yang terlihat di model SfM.
Pakai titik alami (sudut pintu, sambungan ubin) yang diukur. Kalau tidak memungkinkan, penanda
sementara **hanya untuk penyelarasan** dan dicopot setelah pengambilan data. Penanda itu bukan bagian
sistem dan tidak dipakai pengguna. 🟡 Putuskan saat eksekusi.

### 4.2 Varian yang dibandingkan

| Faktor | Nilai |
|---|---|
| Ekstraktor + pencocok | `disk+lightglue`, `aliked+lightglue` (keduanya ada di `hloc`). **Opsional:** XFeat (tidak ada konfigurasi bawaan, perlu integrasi manual) |
| Retrieval global | Pilih satu dari yang tersedia di `extract_features.py` (`netvlad`, `dir`, `openibl`, `megaloc`) **setelah lisensi bobotnya dicek** |
| Jumlah kandidat retrieval (k) | 5, 10, 20 |
| Resolusi sisi terpanjang query | 640, 1024, 1600 px (usulan) |

### 4.3 Tiga tingkat perangkat

| Tingkat | Perangkat | Peran |
|---|---|---|
| **T1** | PC lab dengan GPU (RTX 3070, 7,83 GiB VRAM) | Pengembangan dan batas kecepatan atas |
| **T2** | PC lab tanpa GPU (i7-10700K, GPU dimatikan) | Batas atas CPU. **Bukan bukti untuk server instansi** |
| **T3** | Server instansi (VM, 2 vCPU, RAM 7,8 GB) | **Satu-satunya tingkat yang boleh diklaim sebagai "server instansi tanpa GPU"** |

i7-10700K adalah CPU yang sama dengan benchmark README LightGlue (20 FPS pada 512 keypoint), jadi angka
itu bisa direproduksi di T2 sebagai titik acuan.

### 4.4 Yang diukur

- **Akurasi:** galat horizontal (m) dan galat orientasi (°), median, persentase ≤ 0,5 m dan ≤ 1,0 m,
  dan **jumlah kegagalan** (tidak ada pose). Catat kondisi tiap kegagalan.
- **Waktu per query:** total dan dipecah per tahap (retrieval global, ekstraksi lokal, pencocokan,
  PnP). **Ukur kondisi hangat** (model sudah termuat), pisahkan waktu pemuatan model. Ulang minimal 5
  kali per query, laporkan **median dan persentil 95**.
- **Peta:** waktu pembangunan, jumlah foto yang berhasil terdaftar (bukan hanya yang diambil), ukuran
  berkas, dan **puncak RAM**.
- **Konteks:** beban server instansi saat pengukuran (`uptime`, `free -h`), suhu dan mode daya PC lab.

### 4.5 Perangkat capture (riset 2026-09-24)

**Prinsip:** perangkat dipilih per **peran**, bukan satu perangkat "terbaik" untuk semuanya.

| Peran | Yang menentukan |
|---|---|
| **Foto peta** untuk VPS | Kemiripan dengan gambar query dari ponsel pengguna. Menurut penilaian penyusun, faktor ini lebih menentukan akurasi daripada kelengkapan peta |
| **Skala dan penyelarasan** ke denah | Ukuran metrik yang tepercaya |
| **Titik acuan** untuk evaluasi | Ketelitian yang lebih tinggi dari target (≤ 1,0 m) |

**Pembanding tingkat riset.** LaMAR (ECCV 2022, dibaca ke paper) memakai **NavVis M6 trolley atau VLX
backpack**, yaitu laser scanner dengan kamera panorama, sebagai peta rujukan dan ground truth, lalu
mendaftarkan rekaman iPhone, iPad, dan HoloLens 2 terhadap peta itu. SLAM NavVis bersifat
proprietary. Ini standar emas, tapi mahal dan tidak realistis untuk PA D3.

| Kategori | Kelebihan | Kekurangan | Status untuk PA |
|---|---|---|---|
| **Ponsel Android** (kamera bawaan) | Sama dengan kamera query. Tanpa biaya | Tanpa skala meter. Pemotretan lambat | ✅ **Spike, peta dan query** |
| **Aplikasi rekam ARCore** | Frame + pose + intrinsik. Skala dari ARCore. Sama dengan domain query | Perlu dikembangkan. Pose ARCore drift | ⏭ Sistem akhir |
| **Kamera 360: GoPro MAX (milik Bagus)** | Cakupan penuh sekali jalan, pemetaan ulang cepat | Resolusi per arah lebih rendah, beda kamera dengan query, operator ikut terekam, privasi | ⏭ **Percobaan pembanding setelah spike** |
| **Kamera mirrorless atau DSLR** | Kualitas foto tinggi | Beda domain dengan query, lambat | ❌ Tidak perlu |
| **LiDAR iPhone atau iPad Pro** | Skala metrik langsung | Butuh perangkat iOS. Aplikasi pemindai populer perlu dicek apakah memproses secara lokal | ⚠️ Hanya kalau tersedia |
| **iPhone 15 Pro milik rekan (LiDAR)** | Pemeriksa silang skala hasil meteran | Bergantung jadwal rekan. Kamera beda dengan query. Pakai aplikasi yang memproses **di perangkat**, bukan cloud. Pindahkan data lalu hapus dari ponsel rekan | ⏭ **Simpanan, opsional** |
| **Kamera RGB-D** (misalnya RealSense D455) | Kedalaman metrik | Jangkauan terbatas (⚠️ sumber sekunder: efektif sekitar 6 m), butuh laptop | ❌ Tidak perlu |
| **Laser scanner** (NavVis, Leica, Trimble) | Paling teliti untuk ground truth | Sangat mahal, perangkat lunak proprietary | ⚠️ Hanya kalau kampus punya |
| **Meteran laser dan pita ukur** | Murah, cukup untuk titik acuan dan skala | Manual | ✅ **Spike** |

**Kamera 360 dan COLMAP (dicek ke repo resmi 2026-09-24).** COLMAP punya contoh resmi
`python/examples/panorama_sfm.py`, *"Run Structure-from-Motion on 360-degree panorama images"*.
Panorama dipecah menjadi beberapa tampilan perspektif yang saling tumpang tindih (bawaan
`PERSPECTIVE_OVERLAPPING`). COLMAP juga punya model kamera fisheye dan dukungan rig. Karena hasil
pecahannya gambar perspektif biasa, hasilnya **mungkin** bisa dipakai hloc. ⚠️ Belum dicoba.

**Catatan GoPro MAX:**
- GoPro menyebut resolusi sumber **6K video dan 18 MP foto**
  ([GoPro](https://gopro.com/en/us/news/max-tech-specs-stitching-resolution)).
- Video disimpan sebagai berkas **`.360`** dalam proyeksi **EAC** (cubemap), bukan equirectangular.
  Perlu diekspor lewat GoPro Player atau dikonversi dengan ffmpeg sebelum masuk COLMAP
  ([Trek View](https://www.trekview.org/blog/using-ffmpeg-process-gopro-max-360/)).
- ⚠️ Format foto 360 dan apakah ada model generasi baru belum dicek. **Pastikan model dan firmware
  perangkat yang Bagus punya.**
- Sumber sekunder memperkirakan frame 5,7K equirectangular setara **kira-kira 1080p** per arah
  ([SkyeBrowse](https://www.skyebrowse.com/news/posts/phone-vs-360-camera-indoor)). ⚠️ Belum
  diverifikasi, tapi konsisten dengan pembagian resolusi ke 360°.

**Keputusan:** spike memakai **ponsel + meteran**. GoPro MAX diuji sebagai **peta pembanding**
dengan foto query ponsel yang sama, setelah spike lolos. Tidak ada pembelian perangkat sebelum spike.

## 5. Langkah

1. **Catat lingkungan.** Versi Python, PyTorch, commit `hloc`, versi COLMAP atau pycolmap, driver,
   dan perangkat keras. Tanpa ini hasil tidak bisa direproduksi.
2. **Ambil foto basis data dan query** di koridor terpilih (G0 sudah lolos).
3. **Rekonstruksi peta** dengan `hloc.reconstruction` (pasangan dari `pairs_from_retrieval`).
4. **Selaraskan peta** ke koordinat koridor dengan titik kontrol, catat sisa galat penyelarasan.
5. **Lokalisasi query** dengan `pairs_from_retrieval`, `match_features`, dan `localize_sfm`, untuk semua
   kombinasi di 4.2 pada T1 dulu.
6. **Ulangi kombinasi terpilih di T2, lalu T3.** Tidak perlu semua kombinasi di T3. Pilih 2 atau 3 yang
   paling menjanjikan dari T1 dan T2.
7. **Analisis** dan isi tabel hasil (bagian 7).
8. **Keputusan** memakai bagian 6, lalu catat di `CLAUDE.md` bagian Status.

## 6. Ambang keputusan (🟡 usulan, sepakati dengan pembimbing)

**Peta (G1).** Usulan: ≥ 90% foto basis data terdaftar dan model tampak koheren. Kalau tidak,
ambil ulang data sebelum lanjut. Ambang ini heuristik, bukan dari sumber.

**Akurasi (G2), arm terbaik:**

| Hasil | Tindakan |
|---|---|
| ≥ 70% query ≤ 1,0 m | Lolos |
| 50 sampai 70% | Selidiki (lebih banyak foto basis data, resolusi, k), ulangi sekali |
| < 50% | Eskalasi ke pembimbing |

**Latensi di T3 (G3), median hangat arm terbaik.** Belum ada dasar literatur untuk ambang ini:

| Hasil | Tindakan |
|---|---|
| ≤ 10 detik | Lanjut penuh. Interval koreksi disesuaikan dengan angka ini |
| 10 sampai 30 detik | Lanjut dengan optimasi (resolusi, k, XFeat) dan interval koreksi lebih jarang |
| > 30 detik | **Eskalasi:** server dengan CPU lebih kuat, PC lab sebagai host layanan (perlu izin), atau rencana cadangan |

**RAM (G4).** Puncak RAM tidak boleh melebihi yang tersisa di server instansi (cek `free -h` saat sepi).

**Rencana cadangan** (semuanya butuh persetujuan pembimbing karena mengubah arah dokumen pengajuan):
regresi pose + VIO gaya MobileARLoc, atau pengaturan ulang lewat papan nama gaya INSUS.

## 7. Keluaran

1. **Tabel hasil:** akurasi per varian, waktu per tahap per tingkat perangkat, dan statistik peta.
2. **Log mentah dan skrip ukur**, beserta catatan versi dari langkah 1.
3. **Daftar kegagalan** dan kondisi penyebabnya (cahaya, dinding polos, kaca, orang lewat).
4. **Keputusan tertulis:** lanjut, lanjut dengan optimasi, atau eskalasi. Masuk `CLAUDE.md` bagian Status, beserta
   alasannya kalau berpengaruh ke arsitektur.
5. **Bahan Proposal PA:** angka target latensi yang kini sengaja kosong di dokumen pengajuan.

## 8. Estimasi waktu (🟡 perkiraan, belum divalidasi)

| Tahap | Perkiraan |
|---|---|
| Lingkungan dan versi (langkah 1) | 1 hari |
| Pengambilan foto (langkah 2) | 0,5 sampai 1 hari |
| Peta dan penyelarasan (3 dan 4) | 1 sampai 2 hari, waktu COLMAP belum diketahui |
| Lokalisasi dan pengukuran (5 dan 6) | 2 sampai 3 hari |
| Analisis dan keputusan (7 dan 8) | 1 hari |
| **Total** | **sekitar 1,5 sampai 2 minggu paruh waktu** |

Riset sebelumnya memperkirakan spike gaya penanda 1 sampai 2 minggu. Spike hloc lebih berat, jadi
angka ini kemungkinan bawah, bukan atas.

## 9. Pertanyaan untuk pembimbing (kirim sebelum atau saat ACC)

1. Boleh memakai **PC lab (RTX 3070)** untuk pengembangan dan pengukuran pembanding? Boleh sebagai host
   layanan? Siapa pemiliknya, dan tersedia setelah lulus?
2. **"Tanpa GPU"** tetap dipertahankan sebagai batasan, atau diganti "spesifikasi perangkat dilaporkan
   dan diukur"?
3. **Lisensi non-komersial** (ACE, GLACE, Reloc3r) dianggap masalah untuk platform PA?
4. Ambang latensi di bagian 6 wajar, atau ada angka yang mereka harapkan?
5. **Izin dan koridor mana** untuk pengambilan foto, dan kapan.
6. **"Bisa di mana saja"** dari arahan pembimbing berarti titik mana pun, atau cukup titik yang punya penanda
   alami seperti papan nama? Menentukan apakah spike B di bawah dijalankan.

## 10. Risiko

| Risiko | Penanganan |
|---|---|
| Izin memotret terlambat | Pertanyaan 5 diajukan sedini mungkin. Semua bergantung pada ini |
| Koridor berulang (banyak pintu serupa) menyebabkan lokalisasi keliru | Catat sebagai kondisi kegagalan, pertimbangkan koridor kedua sebagai pembanding |
| Cahaya berubah, kaca, orang lewat | Ambil query di beberapa jam, catat kondisi |
| Kamera ponsel berbeda antara basis data dan query | Pakai satu ponsel dulu, uji ponsel kedua kemudian |
| Pengaturan hloc di Windows bermasalah | ⚠️ belum kucek. Siapkan opsi WSL2 atau Linux, jangan diasumsikan |
| PC lab dan server instansi dipakai orang lain sehingga waktu berfluktuasi | Ulang dan catat beban, laporkan persentil 95 |
| Data foto memuat orang atau area sensitif | Tanyakan aturan pemotretan di gedung, hapus foto yang tidak perlu |

## 11. Spike B (opsional): papan nama gaya INSUS

Hanya dijalankan kalau pembimbing menyetujui (pertanyaan 6). Murah, tanpa peta.

- **Isi:** foto papan nama di koridor yang sama, jalankan deteksi dan OCR, cocokkan ke daftar ruang.
- **Diukur:** tingkat cocok, waktu di T1, T2, T3, dan ketahanan terhadap sudut dan jarak.
- **Catatan:** abstrak paper INSUS melaporkan akurasi deteksi dan OCR, **bukan galat posisi meter**, dan
  cara mendapat pose dari papan belum terverifikasi. YOLOv8 berlisensi AGPL-3.0, jadi cek lisensi
  detektor sebelum dipakai.
- **Perkiraan:** beberapa hari (🟡).

## 12. Hasil uji coba awal (2026-09-25)

**Lingkungan.** Laptop i5-12450HX, RAM 24 GB, **tanpa CUDA**, Windows 11 native (tanpa WSL).
Python 3.12.13 (lewat uv), PyTorch 2.14.0+cpu (8 thread), hloc 1.5 commit `c13273b`, pycolmap
4.2.0. hloc dipasang **tanpa submodul**: keempatnya (d2net, SuperGluePretrainedNetwork,
deep-image-retrieval, r2d2) tidak dipakai, dan SuperGlue berlisensi non-komersial.

**Data.** Dataset contoh bawaan hloc (Sacré-Cœur, foto internet luar ruangan): 9 foto peta, 1 foto
uji **yang tidak ikut peta**. **Bukan lorong gedung**, jadi hanya menguji bahwa pipeline berjalan.

**Hasil pipeline** (`spike/run.py`, bawaan hloc: keypoint ALIKED tanpa batas):

| Hal | Hasil |
|---|---|
| Foto peta terdaftar | 9/9, 2.649 titik 3D |
| Foto uji terlokalisasi | 1/1, 1.492 inlier dari 2.333 korespondensi |
| Ekstraksi fitur peta | 38,6 s untuk 9 foto |
| Pencocokan peta | 433 s untuk 36 pasangan (**~12 s per pasangan**) |
| Rekonstruksi | 7,5 s |
| Estimasi pose | 0,3 s |

**Penyebab lambat, terbukti:** konfigurasi `aliked-n16` di hloc memakai `max_num_keypoints: -1`
(tanpa batas), rata-rata **2.815 keypoint per foto**. Biaya LightGlue naik kira-kira kuadratik
terhadap jumlah keypoint.

**Pengukuran model hangat** (`spike/bench_matching.py`, resize 1024, median):

| Batas keypoint | Ekstraksi per foto | Pencocokan per pasangan | Rata-rata match |
|---|---|---|---|
| 512 | 3,57 s | **0,38 s** | 158 |
| 1024 | 3,52 s | **1,06 s** | 283 |
| 2048 | 3,68 s | **3,79 s** | 523 |

**Perkiraan per lokalisasi di laptop ini** (1 ekstraksi + k pasangan + pose, tanpa retrieval
global):

| Batas keypoint | k = 5 | k = 10 |
|---|---|---|
| 512 | ~6 s | ~8 s |
| 1024 | ~9 s | ~14 s |
| tanpa batas | ~40 s ke atas | ~75 s ke atas |

**Temuan dan konsekuensinya:**
1. **Pipeline hloc berjalan native di Windows.** WSL tidak diperlukan.
2. **Dua kenop utama latensi: batas keypoint dan k.** Bawaan hloc tidak cocok untuk CPU. `run.py`
   sekarang memakai `--max-kp 1024` sebagai bawaan.
3. **Ekstraksi ALIKED ~3,5 s per foto pada resize 1024 adalah biaya tetap per query.** Kenop
   berikutnya: resize lebih kecil (misalnya 640) atau XFeat.
4. **Lebih sedikit keypoint berarti lebih sedikit match** (158 pada 512 lawan 523 pada 2048). Apakah
   512 atau 1024 masih cukup untuk lokalisasi di lorong **harus diukur di data lorong**, bukan
   ditebak.
5. ⚠️ **Server instansi (2 vCPU) kemungkinan beberapa kali lebih lambat dari laptop ini (8 thread).**
   Angka di atas adalah batas atas kecepatan, bukan bukti untuk server.
6. Unduhan bobot model pertama kali lambat di jaringan ini (LightGlue 45 MB ~5 menit). Bobot
   tersimpan di cache torch, jadi hanya sekali.

**Langkah berikutnya:** foto lorong lantai 10, lalu jalankan `run.py` dengan `--max-kp 512` dan
`1024`, lalu bandingkan jumlah query yang terlokalisasi dan waktunya.

### Menyiapkan lingkungan (bisa diulang)

`.venv/`, `third_party/`, `data/`, dan `outputs/` tidak ada di git. Untuk membangun ulang:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv torch torchvision --index-url https://download.pytorch.org/whl/cpu
git clone https://github.com/cvg/Hierarchical-Localization.git third_party/Hierarchical-Localization
git -C third_party/Hierarchical-Localization checkout c13273b
uv pip install --python .venv -e third_party/Hierarchical-Localization
```

Tanpa `--recursive`: submodul hloc tidak dibutuhkan. Data contoh ada di
`third_party/Hierarchical-Localization/datasets/sacre_coeur/mapping`. Bobot ALIKED dan LightGlue
diunduh otomatis saat pertama dipakai.

### Status terakhir (2026-09-27)

| Hal | Status |
|---|---|
| Lingkungan spike di laptop | ✅ Siap: Python 3.12, PyTorch 2.14 CPU, hloc 1.5 (`c13273b`), pycolmap 4.2.0, `huggingface_hub`, `safetensors` |
| uv | ✅ 0.12.19, cocok dengan `required-version` |
| Pipeline pada data contoh | ✅ Berjalan (bagian 12 di atas) |
| Bobot ALIKED dan LightGlue | ✅ Tersimpan di cache torch |
| Bobot MegaLoc (retrieval, 915 MB) | ✅ Terunduh di laptop dan PC lab. Pertama kali: `torch.hub.load("gmberton/MegaLoc", "get_trained_model", trust_repo=True)` supaya tidak macet di prompt interaktif |
| Lingkungan di PC lab (RTX 3070) | ✅ Siap, CUDA aktif. Hasil pengukuran di bagian "Hasil pengukuran hangat di PC lab" |
| Folder foto | ✅ `data/lantai10/mapping/` dan `data/lantai10/query/`, **masih kosong** |
| Foto lorong lantai 10 | ⏸️ Belum diambil. Panduan memotret ada di bagian 4.1 dan 4.5 |

**Temuan baru:**
- **Lisensi bobot MegaLoc: MIT** (halaman model `gberton/MegaLoc` di Hugging Face). Menutup ⚠️
  lisensi bobot untuk MegaLoc. NetVLAD tetap ⚠️.
- `megaloc_model.py` memuat potongan *optimal transport* dari OpenGlue (ucuapps), bukan kode
  SuperGlue milik Magic Leap. ⚠️ Lisensi OpenGlue belum dicek.

**Langkah berikutnya, berurutan:**
1. ~~Selesaikan unduhan MegaLoc.~~ Selesai.
2. Pemilik repo memotret lorong lantai 10 (izin penanggung jawab lab, jam sepi).
3. Jalankan `spike/run.py data/lantai10 --out outputs/lantai10-kp512 --max-kp 512` dan
   `--max-kp 1024`, bandingkan foto peta terdaftar, foto uji terlokalisasi, dan waktu per tahap.
4. Masukkan hasil dan temuan lisensi di atas lewat satu PR.

### Jalur retrieval dan biaya per query (2026-09-27)

**Jalur retrieval MegaLoc terbukti berjalan.** `run.py` kini punya `--exhaustive-max` (0 = selalu
retrieval), sehingga jalur yang biasanya baru aktif di atas 30 foto peta bisa diuji dengan data
contoh. Hasilnya: peta 9/9 terdaftar, foto uji 1/1 terlokalisasi, 72 pasangan peta dan 9 pasangan
query. Jumlah kandidat `k` kini dibatasi maksimal jumlah foto peta, karena `torch.topk` di hloc
gagal kalau `k` lebih besar.

> ⚠️ **Koreksi (2026-09-27, sore):** angka MegaLoc **3,5 s** dan tabel perkiraan di bawah **tidak bisa
> direproduksi**. Dengan kode yang sama, MegaLoc resize 1024 kemudian terukur 13 sampai 15 s. Kecepatan
> laptop terbukti naik turun 2 sampai 4 kali antar-run (lihat "Pengukuran hangat satu proses"), jadi
> angka absolut di bagian ini **jangan dikutip**.

**Pengukuran model hangat di laptop** (resize 1024, 8 thread):

| Tahap per query | Waktu |
|---|---|
| Deskriptor global MegaLoc | **3,5 s** (muat model sekali: 4,2 s) |
| Fitur lokal ALIKED | ~3,5 s |
| Pencocokan LightGlue | 0,38 s (512 kp) atau 1,06 s (1024 kp) per pasangan |
| Estimasi pose | 0,3 s |

**Perkiraan per lokalisasi di laptop:**

| Batas keypoint | k = 5 | k = 10 |
|---|---|---|
| 512 | ~9 s | ~11 s |
| 1024 | ~13 s | ~18 s |

**Temuan:**
1. **Pemanggilan fungsi batch hloc punya biaya tetap beberapa detik** (memuat model dan 5 proses
   pembantu `DataLoader`, mahal di Windows). Tahap pencocokan 9 pasangan butuh 9 sampai 11 detik
   pada 512 maupun 1024 keypoint, padahal ukuran hangat hanya 3,4 dan 9,5 detik. **Layanan
   `/localize` wajib memuat model sekali dan tidak memanggil fungsi batch hloc per permintaan.**
2. **Ekstraksi fitur (MegaLoc + ALIKED) makan ~7 detik per query** sebelum pencocokan dimulai.
   Di server instansi (2 vCPU) kemungkinan jauh lebih lambat, sehingga gerbang ≤ 10 detik berisiko.
3. ⚠️ **Hipotesis untuk dicoba: lewati retrieval global saat koreksi berkala.** Di antara dua
   koreksi, ARCore sudah memberi perkiraan posisi. Kandidat foto peta bisa dipilih dari kedekatan
   posenya (hloc punya `pairs_from_poses`), sehingga ~3,5 detik MegaLoc hilang. Retrieval global
   tetap dipakai untuk lokalisasi pertama, saat posisi belum diketahui. **Belum diuji.**
4. Kenop lain yang belum diuji: resize lebih kecil untuk MegaLoc dan ALIKED, serta XFeat.

### Pengukuran hangat satu proses (2026-09-27)

`spike/bench_localize.py` memuat semua model dan data peta **sekali**, lalu mengukur tiap foto uji
per tahap (baca, MegaLoc, retrieval, ALIKED, LightGlue ke k kandidat, PnP), seperti layanan
`/localize` nanti. Korespondensi 2D-3D mengikuti `pose_from_cluster` hloc, tapi di memori. Hasil
pada data contoh (1 foto uji, k = 5, keypoint 1024): **terlokalisasi, 402 inlier**, sama untuk
kedua resolusi MegaLoc.

**Temuan 1: resolusi MegaLoc adalah kenop terbesar.** MegaLoc berbasis ViT dengan patch 14 piksel,
jadi foto 1020x765 menjadi ~3.900 token dan biaya attention naik kuadratik. Diukur berdekatan waktu:

| Resolusi MegaLoc | Waktu per foto (percobaan 1) | Percobaan 2 | 5 kandidat teratas |
|---|---|---|---|
| 1024 | 13,3 s | 15,0 s | [3, 8, 6, 0, 5] |
| 640 | 3,8 s | | sama |
| 512 | **2,3 s** | **2,4 s** | **sama** |

Satu foto uji dan data luar ruangan saja, jadi **harus diuji ulang dengan foto lorong**, termasuk
apakah kandidat dan akurasi tetap sama. `run.py` dan `bench_localize.py` kini punya
`--global-resize`, dan deskriptor global disimpan per resolusi (`global-r<R>.h5`) supaya tidak
tercampur, bug yang sama jenisnya dengan PR #4.

**Temuan 2: kecepatan laptop tidak stabil, jadi angka absolut dari laptop tidak sah.** Empat run
berurutan (k = 5, keypoint 1024):

| MegaLoc | Thread | MegaLoc | ALIKED | LightGlue | Total |
|---|---|---|---|---|---|
| 512 | 8 | 2,43 s | 3,51 s | 4,10 s | 10,2 s |
| 512 | 2 | 4,19 s | 5,79 s | 7,53 s | 17,6 s |
| 1024 | 8 | 14,99 s | 3,89 s | 4,00 s | 23,0 s |
| 1024 | 2 | 7,46 s | 1,94 s | 1,38 s | 10,8 s ⚠️ |

Run terakhir lebih cepat dari run 8 thread di **semua** tahap, termasuk ALIKED dan LightGlue yang
setelannya tidak berubah. Laptop berbagi CPU dengan aplikasi lain (beban latar 23 sampai 44%, CPU
hibrida P-core dan E-core, skema daya Balanced). Yang sudah dikesampingkan untuk selisih MegaLoc:
praproses (identik dengan hloc), pycolmap/OpenMP, pembatasan daya CPU, bilangan denormal, dan
perubahan kode MegaLoc di cache torch hub.

**Konsekuensi:**
1. Yang boleh dipakai dari laptop hanya **perbandingan relatif yang diukur berdekatan waktu**.
2. **Angka yang diklaim harus dari server instansi (T3)**, diukur dengan `bench_localize.py`.
3. Kalau laptop tetap dipakai untuk angka: tutup aplikasi lain, mode daya performa terbaik,
   tersambung listrik, dan ulangi beberapa run secara berselang-seling antar-setelan.

### Pengecekan server instansi dan keputusan tempat uji (2026-09-27)

Pengecekan baca-saja di server instansi (T3):

| Hal | Hasil | Penilaian |
|---|---|---|
| CPU | 2 vCPU, model virtual generik QEMU, **ada AVX, AVX2, FMA** | ✅ PyTorch bisa memakai jalur cepatnya. Kekhawatiran "CPU generik tanpa AVX2" terbukti keliru |
| RAM | 7,8 GB, tersedia ~5,1 GB, **swap 2,8 dari 4 GB terpakai** | ⚠️ Pernah ada tekanan memori |
| Disk `/` | **sisa 5,6 GB (90%)** | ❌ Lingkungan spike (~3 sampai 4 GB) akan membuat disk ~96% penuh, padahal server menjalankan lebih dari 10 layanan produksi beserta basis datanya |
| Beban | **2,21 pada 2 vCPU**, satu proses macet memakai satu core penuh | ❌ Pengukuran latensi tidak sah selama server jenuh |

**Keputusan (pemilik repo, 2026-09-27): uji sementara dipindah ke PC lab dengan GPU** (i7-10700K,
RTX 3070, RAM 32 GB), diakses dari jauh. Server instansi **belum gugur**: bisa dipakai lagi setelah
disk dibersihkan dan beban normal, lewat koordinasi dengan pemilik server.

**Konsekuensi yang wajib disampaikan ke pembimbing:** dokumen pengajuan menyebut "server instansi
tanpa GPU". PC lab punya GPU, jadi pilihannya: ukur **CPU saja** agar klaim itu tetap bisa diuji,
atau pakai GPU dan klaim diubah menjadi "server dengan GPU konsumen". Paling informatif: ukur
**keduanya di mesin yang sama** (T1 dengan GPU, T2 tanpa GPU), lalu tarik spesifikasi minimum
server untuk instansi. Hal lain soal PC lab sebagai server: Windows 10 22H2 tanpa pembaruan
keamanan, tersambung Wi-Fi, dan harus tidak dipakai aplikasi berat saat pengukuran.

### Memasang lingkungan di PC lab (Windows, GPU)

Dijalankan pemilik repo lewat akses jarak jauh, di PowerShell, folder `C:\Users\<user>\eutopos-vps`.

**Temuan saat memasang:**
- PC lab: driver NVIDIA 616.92 (mendukung CUDA 13), beban CPU 2%, RAM kosong 18 GB, C: sisa 58 GB.
- `uv` dan `python` yang terdeteksi di PATH **milik aplikasi lain ("hermes")**. Jangan dipakai
  atau diubah. uv resmi dipasang terpisah di `%USERPROFILE%\.local\bin` dan dipanggil dengan path
  lengkap.
- Installer uv **jangan dibungkus** `powershell -c "irm ... | iex"` dari dalam PowerShell. Tanda
  kutipnya hilang, `|` diproses shell luar, dan `iex` menerima keluaran profil (fastfetch). Jalankan
  langsung `irm ... | iex`.
- PyTorch 2.14 tersedia untuk Windows Python 3.12 di indeks `cu130` dan `cu126` (bukan `cu128`).

```powershell
irm https://astral.sh/uv/0.12.19/install.ps1 | iex
$uv = "$env:USERPROFILE\.local\bin\uv.exe"
cd "$env:USERPROFILE\eutopos-vps"
& $uv venv --python 3.12 .venv
& $uv pip install --python .venv torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu130
git clone https://github.com/cvg/Hierarchical-Localization.git third_party/Hierarchical-Localization
git -C third_party/Hierarchical-Localization checkout c13273b
& $uv pip install --python .venv -e third_party/Hierarchical-Localization huggingface_hub safetensors
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

**Mengukur di mesin yang sama:** `bench_localize.py --device cuda` untuk GPU (T1), `--device cpu`
untuk CPU (T2). Untuk `run.py`, hloc otomatis memakai GPU kalau ada. Paksa CPU dengan
`$env:CUDA_VISIBLE_DEVICES = ""` sebelum menjalankannya.

**Bukti tambahan ketidakstabilan laptop:** setelan yang sama persis (MegaLoc 512, 8 thread, k = 5)
terukur 10,2 s lalu 3,1 s pada hari yang sama. Angka latensi yang diklaim harus dari PC lab atau
server, diulang, dan dicatat kondisinya.

### Hasil pengukuran hangat di PC lab (2026-09-27)

Data contoh (9 foto peta, 1 foto uji), peta dibangun ulang di PC lab dengan
`run.py --exhaustive-max 0`. `bench_localize.py`: k = 5, keypoint 1024, resize ALIKED 1024,
1 pemanasan lalu median dari 5 ulangan. CPU memakai 8 thread bawaan torch.

| Perangkat | MegaLoc | Baca | MegaLoc | ALIKED | LightGlue | PnP | **Total** | Inlier |
|---|---|---|---|---|---|---|---|---|
| RTX 3070 (T1) | 512 | 0,022 s | 0,029 s | 0,021 s | ~0,07 s ⚠️ | 0,013 s | **0,15 s** | 406 |
| RTX 3070 (T1) | 1024 | 0,023 s | 0,182 s | 0,021 s | ~0,07 s ⚠️ | 0,013 s | **0,31 s** | 406 |
| i7-10700K (T2) | 512 | 0,023 s | 0,517 s | 1,358 s | 0,627 s | 0,016 s | **2,51 s** | 413 |
| i7-10700K (T2) | 1024 | 0,022 s | 2,921 s | 1,354 s | 0,622 s | 0,013 s | **4,91 s** | 413 |
| i7-10700K, 2 thread | 512 | 0,020 s | 1,018 s | 1,791 s | 1,217 s | 0,012 s | **4,05 s** | 413 |

⚠️ Baris LightGlue tidak tampil di keluaran GPU yang ditempel. Angkanya diturunkan dari total
dikurangi tahap lain, jadi perkiraan.

**Temuan:**
1. **Pipeline hangat di GPU sekitar 16 kali lebih cepat dari CPU desktop** (0,15 s vs 2,51 s pada
   MegaLoc 512).
2. **Kenop resolusi MegaLoc terkonfirmasi di mesin stabil:** 1024 ke 512 memangkas MegaLoc di CPU
   dari 2,92 s ke 0,52 s (5,6 kali), sejalan dengan temuan laptop (~6 kali). Kandidat teratas dan
   inlier sama.
3. **Di CPU dengan MegaLoc 512, ALIKED menjadi tahap terlama** (1,36 s, lebih dari separuh total).
   Kenop berikutnya: resize ALIKED (`--resize`) dan batas keypoint (`--max-kp`), diuji dengan
   foto lorong karena keduanya bisa menurunkan akurasi.
4. **MegaLoc 1024 di i7-10700K 2,9 s, di laptop 13 sampai 15 s.** Menguatkan bahwa angka laptop
   tidak sah.
5. **GPU dan CPU memberi hasil sedikit berbeda** (406 vs 413 inlier, pusat kamera bergeser ~0,02
   satuan model). Wajar karena perbedaan aritmetika floating point antara GPU dan CPU. Akurasi
   dibandingkan dalam meter setelah ada titik acuan, bukan dari angka ini.

6. **Dibatasi 2 thread (perkiraan server 2 vCPU): 4,05 s.** MegaLoc dan LightGlue melambat ~2 kali,
   ALIKED hanya ~1,3 kali. Dengan 2 thread, ALIKED tetap tahap terlama.

**Batas:** satu foto uji, data luar ruangan, CPU desktop 8 core. Server instansi hanya 2 vCPU, dan
core-nya kemungkinan lebih lambat dari i7-10700K, jadi baris 2 thread adalah **batas bawah**, bukan
angka server.

### Protokol titik acuan untuk uji lorong lantai 10

Tanpa titik acuan, posisi hasil lokalisasi hanya dalam satuan model SfM, sehingga pertanyaan
akurasi ≤ 1,0 m tidak bisa dijawab. Protokol ini dijalankan bersamaan dengan pemotretan.

**Bawa:** meteran (laser lebih baik, pita cukup), selotip kertas, spidol, ponsel yang sama dengan
foto peta.

**Menandai titik:**
1. Pilih satu **titik asal** yang mudah ditemukan lagi, misalnya sudut pintu lab. Sumbu x sepanjang
   lorong, sumbu y melintang lorong.
2. Tempel sekitar **20 titik** selotip di lantai, beri label `P01` sampai `P20`.
3. ⚠️ **Letakkan titik zig-zag dekat kedua dinding, jangan di satu garis tengah.** Titik yang segaris
   membuat rotasi peta di sekitar garis itu tidak tentu, sehingga penyelarasan ke meter tidak
   stabil. `eval_meter.py` memberi peringatan kalau `sebaran_titik` < 0,05.
4. Ukur `x_m` dan `y_m` tiap titik dari titik asal, catat di `data/lantai10/titik.csv` dengan format
   `spike/titik-acuan-contoh.csv`. Catat juga alat ukur dan perkiraan ketelitiannya.

**Memotret foto uji:** berdiri dengan ujung kaki di titik, ponsel setinggi dada, lalu ambil 2 foto
ke arah berbeda. Namai `P07_a.jpg`, `P07_b.jpg` (ID titik di depan, sebelum `_`). Simpan di
`data/lantai10/query/`. Foto peta tetap diambil terpisah seperti bagian 4.1.

**Menghitung galat:**

```bash
python spike/run.py data/lantai10 --out outputs/lantai10
python spike/eval_meter.py outputs/lantai10/kp1024-r1024/results.csv data/lantai10/titik.csv
```

`eval_meter.py` menyelaraskan peta ke meter dengan Sim3 (`pycolmap.estimate_sim3d_robust`) dari
pusat kamera ke titik acuan, memakai skema **leave-one-out**: galat tiap titik dihitung dari Sim3
yang ditaksir tanpa titik itu. Keluarannya median galat, persentil 90, dan **persen foto ≤ 1,0 m**.
Juga **persen salah yakin**: foto yang dianggap berhasil oleh pipeline (ada pose) tapi galatnya
lebih dari `--salah-m` (bawaan 3 m, kira-kira sudah di depan pintu atau lorong yang salah). Untuk
navigasi ini lebih berbahaya daripada gagal, karena aplikasi tidak tahu harus mencoba lagi. Kolom
`inliers` di `galat_meter.csv` dipakai untuk memilih ambang inlier: kalau foto salah yakin punya
inlier setinggi foto yang benar, ambang inlier saja tidak cukup untuk menyaringnya.
Foto yang gagal dilokalisasi dihitung gagal. Galat dilaporkan 2D (bidang lantai), tinggi ponsel
dianggap tetap (`--tinggi`, bawaan 1,3 m). Uji logikanya dengan `--self-test`.

**Batas:** posisi ponsel di tangan tidak persis di atas titik (puluhan sentimeter, lihat 4.1).
Koordinat titik acuan gedung tidak di-commit sebelum ditanyakan ke pembimbing.
