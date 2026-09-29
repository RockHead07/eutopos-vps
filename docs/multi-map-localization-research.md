# Riset: Memilih Peta Area dan Mengelola Banyak Peta

Riset untuk satu pertanyaan desain eutopos: kalau gedung dipetakan sebagai **banyak peta per area**,
bagaimana server memutuskan foto pengguna dilokalisasi ke peta yang mana, dan bagaimana peta-peta itu
dikelola (tumpang tindih, penggabungan, pembaruan).

**Cara verifikasi.** Metadata paper dicek ke Crossref atau halaman arXiv. Kemampuan hloc dibaca
langsung dari kode lokal `third_party/Hierarchical-Localization` (commit `c13273b`), pycolmap dari
paket terpasang (4.2.0), LaMAR dan Immersal dari kode di repo resminya. Klaim vendor dibaca dari
dokumentasi resmi. Angka hanya dimuat kalau terbaca di sumber. Tanda ⚠️ berarti belum terverifikasi
penuh. Tanggal pengecekan: 29 September 2026.

**Keputusan yang sudah dikunci (brainstorming) dan tidak dibahas ulang di sini:** peta terpisah per
area, masing-masing punya versi, semuanya diselaraskan ke satu kerangka koordinat gedung; pemetaan
terus-menerus oleh banyak orang lewat aplikasi capture (video + pose ARCore); server membangun peta
otomatis; manusia menyetujui sebelum terbit; wajah diburamkan; video mentah dihapus.

## Ringkasan

| Pertanyaan | Jawaban singkat | Dasar |
|---|---|---|
| Bagaimana memilih peta untuk foto pertama (belum ada posisi)? | Retrieval global (MegaLoc) atas **gabungan** gambar semua area kandidat, lalu voting per area, lalu verifikasi geometris (jumlah inlier PnP). Petunjuk lantai dari aplikasi mempersempit kandidat | hloc, InLoc, ESAC, MultiSet `hintFloorHeight` |
| Bagaimana untuk foto berikutnya? | Posisi dari koreksi terakhir dirambatkan dengan pelacakan ARCore menjadi **prior**. Server hanya mencari di area dalam radius prior | LaMAR, hloc InLoc "temporal", Immersal `SolverType.Prior`, MultiSet `hintPosition` |
| Prior salah? | Prior adalah **filter yang gagal terbuka**: kalau tidak ada prior atau hasilnya gagal, perluas pencarian | LaMAR `filter_by_radio`, MultiSet `hintRadius`, Immersal reset prior |
| Perlu menggabungkan peta? | **Tidak.** Setiap peta diselaraskan sendiri ke kerangka gedung lewat titik acuan. Tumpang tindih 5 sampai 10 m antar-area tetap dianjurkan untuk perpindahan area dan pemeriksaan konsistensi | MultiSet "Merging by Georeference", Immersal "Aligning Maps", COLMAP `model_aligner` |
| Bagaimana memperbarui peta? | Bangun **versi baru** area itu dari nol, selaraskan ulang, uji pada set uji tertahan, setujui, lalu tukar penunjuk versi aktif. Jangan menambal peta aktif di tempat | Niantic reactivation, MultiSet Map Versioning, COLMAP FAQ |
| Apa yang dibangun untuk PA? | Hampir tidak ada mesin multi-peta. Cukup `area_id` dan `map_version` di model data dan respons API, supaya kontraknya tidak berubah saat area kedua datang | Bagian 5 |

---

## 1. Masalah

Dengan satu peta, lokalisasi hloc berjalan: retrieval global memilih k gambar basis data paling mirip,
fitur lokal dicocokkan, PnP menghasilkan pose. Dengan banyak peta area, muncul tiga masalah baru.

1. **Pemilihan peta (coarse localization).** Foto harus dicocokkan ke peta yang benar. Mencocokkan ke
   semua peta satu per satu memperbesar latensi sebanding jumlah peta, padahal target server adalah
   CPU 2 vCPU.
2. **Aliasing antar-area dan antar-lantai.** Lorong gedung kampus mirip satu sama lain, dan lantai yang
   bertumpuk sering nyaris identik. Semakin banyak peta, semakin banyak "pengecoh".
3. **Pengelolaan peta dari waktu ke waktu.** Peta dibangun oleh banyak orang, diperbarui berkala, dan
   harus tetap berada di satu kerangka gedung supaya POI dan NavMesh tidak bergeser.

---

## 2. Apa yang dilakukan riset

### 2.1 hloc: retrieval dulu, pencocokan kemudian

- **Sarlin, Cadena, Siegwart, Dymczyk.** *From Coarse to Fine: Robust Hierarchical Localization at
  Large Scale.* CVPR 2019, hlm. 12708-12717.
  [DOI 10.1109/CVPR.2019.01300](https://doi.org/10.1109/CVPR.2019.01300),
  [arXiv 1812.03506](https://arxiv.org/abs/1812.03506).
- Inti pendekatannya (abstrak): retrieval global lebih dulu untuk mendapat hipotesis lokasi, baru
  kemudian mencocokkan fitur lokal *"within those candidate places"*. Artinya **pemilihan tempat sudah
  menjadi tahap pertama hloc**. Pertanyaannya tinggal: retrieval dijalankan atas gambar yang mana.

**Kemampuan hloc yang relevan, dibaca dari kode lokal (commit `c13273b`, Apache-2.0):**

| Berkas | Kemampuan | Arti untuk banyak peta |
|---|---|---|
| `hloc/pairs_from_retrieval.py` | `main()` menerima `db_prefix` (boleh daftar prefiks), `db_list`, atau `db_model`, dan `db_descriptors` boleh **daftar beberapa berkas** deskriptor. Skor = perkalian titik deskriptor global, dipilih top-k | Retrieval bisa dibatasi ke area kandidat tanpa mengubah hloc: beri nama gambar berprefiks area (misalnya `L10-A/…`) lalu kirim prefiks area kandidat. Deskriptor per area bisa disimpan di berkas terpisah |
| `hloc/localize_sfm.py` | `do_covisibility_clustering()` mengelompokkan gambar hasil retrieval menurut kovisibilitas di model SfM, lalu PnP dijalankan per kelompok dan kelompok dengan inlier terbanyak menang | Pola yang sama berlaku lintas peta: gambar dari peta berbeda otomatis tidak kovisibel, jadi voting per area lalu pilih yang inlier-nya terbanyak adalah perluasan wajar |
| `hloc/localize_sfm.py`, `main()` | Kalau PnP gagal dan `covisibility_clustering=False`, pose yang ditulis adalah **pose gambar basis data teratas** (`closest.cam_from_world()`), bukan status gagal | ⚠️ Jebakan: memakai `localize_sfm.main()` apa adanya menyembunyikan kegagalan. Kode spike (`spike/run.py`, `spike/bench_localize.py`) sudah memanggil `QueryLocalizer` langsung dan membaca `num_inliers`, jadi tidak terkena |
| `hloc/pairs_from_poses.py` | Membuat pasangan antar-gambar **referensi** berdasarkan jarak pusat kamera dan sudut sumbu optik (ambang bawaan 30°) dari model COLMAP | Untuk membangun peta dari pose yang diketahui (misalnya pose ARCore), **bukan** untuk menyaring kandidat kueri dengan prior. Filter prior untuk kueri harus ditulis sendiri (lihat LaMAR di bawah) |
| `hloc/pipelines/CMU/pipeline.py` | Setiap *slice* Extended CMU Seasons punya model referensi dan daftar kueri sendiri (`run_slice`) | Preseden benchmark: peta terpisah per wilayah, dan kueri sudah tahu wilayahnya. Di dunia nyata "tahu wilayahnya" itulah yang harus dikerjakan pemilihan peta |
| `hloc/pipelines/4Seasons/utils.py` | `generate_localization_pairs()` memakai frame referensi yang sudah diberikan benchmark lalu mengambil tetangganya dari daftar pasangan | Contoh pasangan lokalisasi dari **prior pose**, bukan dari retrieval |

Context7 tidak memiliki dokumentasi hloc (pencarian hanya mengembalikan pustaka lain), jadi kode
lokal dipakai sebagai sumber primer.

### 2.2 hloc pada InLoc: konsistensi temporal menentukan gedung dan lantai

- README hloc memuat dua baris InLoc SuperPoint+SuperGlue: tunggal 46,5 / 65,7 / 78,3 (DUC1) dan
  52,7 / 72,5 / 79,4 (DUC2), serta varian **"temporal"** 49,0 / 68,7 / 80,8 dan 53,4 / 77,1 / 82,4
  (persen dalam 0,25 / 0,5 / 1 m, NetVLAD top 40) (`third_party/Hierarchical-Localization/README.md`).
- Deskripsi kiriman "temporal" di
  [visuallocalization.net/details/10937](https://www.visuallocalization.net/details/10937/):
  *"For the difficult queries, temporal consistency with the easier queries determines the building
  and floor"*.
- **Arti:** bahkan pada benchmark indoor rujukan, cara yang dipakai penulis hloc untuk menaikkan
  akurasi adalah memakai kueri tetangga yang mudah untuk **memilih gedung dan lantai** bagi kueri yang
  sulit. Untuk eutopos, "kueri tetangga" itu adalah koreksi sebelumnya yang dirambatkan ARCore.
- Catatan: SuperPoint dan SuperGlue berlisensi non-komersial. Angka ini hanya dikutip sebagai bukti
  efek prior, bukan sebagai konfigurasi yang dipakai.

### 2.3 InLoc: lantai lain sebagai pengecoh

- **Taira dkk.** *InLoc: Indoor Visual Localization with Dense Matching and View Synthesis.* CVPR
  2018, hlm. 7199-7209. [DOI 10.1109/CVPR.2018.00752](https://doi.org/10.1109/CVPR.2018.00752),
  [arXiv 1803.10368](https://arxiv.org/abs/1803.10368).
- Basis data: 277 panorama RGBD dari dua gedung, lima lantai (DUC1, DUC2, CSE3, CSE4, CSE5). Kueri
  356 foto iPhone 7 hanya di DUC1 dan DUC2. Tiga lantai lain sengaja dibiarkan sebagai *"confusers at
  search time"*. Paper menyebut pola berulang (tangga, pilar, koridor, pintu, jendela) sebagai
  tantangan utama ([ar5iv](https://ar5iv.labs.arxiv.org/html/1803.10368)).
- **Arti:** benchmark indoor yang dipakai eutopos sebagai dasar target (≤ 1 m pada ≥ 70%) justru
  **mengukur akurasi dengan lantai lain ikut dicari**. Kalau eutopos mempersempit ke satu lantai
  lewat prior, angkanya tidak lagi sebanding langsung dengan InLoc. Laporkan keduanya.

### 2.4 LaMAR: sinyal radio dan urutan frame sebagai prior

- **Sarlin dkk.** *LaMAR: Benchmarking Localization and Mapping for Augmented Reality.* ECCV 2022,
  LNCS hlm. 686-704. [DOI 10.1007/978-3-031-20071-7_40](https://doi.org/10.1007/978-3-031-20071-7_40),
  [arXiv 2210.10770](https://arxiv.org/abs/2210.10770). Kode
  [microsoft/lamar-benchmark](https://github.com/microsoft/lamar-benchmark): **kode MIT**, dokumen
  CC-BY-4.0 (berkas `LICENSE-CODE` dan `LICENSE`, dibaca di commit `5ffd891`).

**Dari kode (terverifikasi):**

- `lamar/run.py`: opsi `--use_radios` menyalakan `filter_radio` dengan `window_us = 2_000_000` (2 s)
  dan `frac_pairs_filter = 0.025`, artinya sebelum retrieval visual, kandidat gambar dipangkas ke
  **2,5% peta** yang sidik jari WiFi/Bluetooth-nya paling mirip.
- `lamar/utils/retrieval.py`, `filter_by_radio()`: kalau kueri **tidak punya sinyal radio**, atau
  pencarian radio tidak menemukan apa pun, **semua gambar dipertahankan** (`keep[i, :] = True`). Filter
  gagal terbuka.
- `lamar/utils/retrieval.py`, `filter_by_pose()`: untuk lokalisasi multi-frame, kandidat dibuang kalau
  selisih rotasi > `max_rotation` (bawaan 120°) atau translasi > `max_translation` (bawaan 20 m) dari
  pose prior. `lamar/run.py` memakai `num_pairs_filter: 100` untuk tahap ini.
- `lamar/tasks/chunk_alignment.py`: filter radio **dimatikan** pada relokalisasi tahap kedua dengan
  komentar *"we have stronger priors"*. Prior dari pelacakan perangkat dianggap lebih kuat daripada
  radio.
- `scantools/utils/radio_mapping.py`: peta radio dibangun per sel ruang dari pose gambar referensi;
  gambar tanpa radio ditempelkan ke sel valid terdekat.

**Dari paper** (dibaca lewat ringkasan [ar5iv](https://ar5iv.labs.arxiv.org/html/2210.10770)):
penyaringan radio disebut *"always improves the localization accuracy over vanilla vision-only
retrieval"*, dan lokalisasi berurutan yang memadukan pelacakan perangkat dengan lokalisasi absolut
memberi peningkatan besar dibanding frame tunggal. ⚠️ Angka persisnya (peningkatan sekitar 20%,
*time-to-recall* dari lebih dari 10 s menjadi 1,40 s dan 3,58 s) terbaca lewat alat ringkasan, belum
dicocokkan ke PDF.

**Arti untuk eutopos:** pola yang sama persis dengan yang dibutuhkan. (1) Prior radio dan prior pose
bekerja sebagai **penyaring daftar gambar basis data sebelum retrieval**, bukan pengganti retrieval.
(2) Prior pose dari pelacakan lebih kuat daripada radio. (3) Filter harus gagal terbuka. Karena kode
LaMAR berlisensi MIT, idenya (bahkan kodenya) boleh diadaptasi ke repo AGPL-3.0.

### 2.5 ESAC: klasifikasi "bagian peta mana" dengan campuran pakar

- **Brachmann, Rother.** *Expert Sample Consensus Applied to Camera Re-Localization.* ICCV 2019,
  hlm. 7524-7533. [DOI 10.1109/ICCV.2019.00762](https://doi.org/10.1109/ICCV.2019.00762),
  [arXiv 1908.02484](https://arxiv.org/abs/1908.02484). Kode
  [vislearn/esac](https://github.com/vislearn/esac), **BSD-3-Clause**, terakhir diperbarui 2020.
- Cara kerja ([ar5iv](https://ar5iv.labs.arxiv.org/html/1908.02484)): *gating network* memprediksi
  distribusi peluang atas "pakar", masing-masing pakar bertanggung jawab atas satu bagian lingkungan.
  Hipotesis RANSAC **dibagi ke beberapa pakar** menurut distribusi multinomial dari peluang itu, tidak
  hanya ke pakar teratas.
- Hasil pada gabungan 7Scenes + 12Scenes (19 ruangan, sekitar 645 m³): 88,1% berhasil direlokalisasi,
  dibanding 53,3% untuk DSAC++. Paper menyebut beberapa ruangan *"too similar"* sehingga prediksi
  gating teratas sering salah, dan pembagian hipotesis itulah yang membuatnya tetap tangguh.
- **Arti untuk eutopos:** ESAC sendiri tidak cocok (regresi koordinat scene, dilatih per scene, butuh
  GPU). **Pelajarannya yang dipakai:** pemilih peta kasar (di eutopos: retrieval global) **pasti
  kadang salah** pada ruang yang mirip. Jangan langsung percaya peta teratas. Coba dua kandidat teratas
  kalau selisih skornya tipis, dan biarkan verifikasi geometris (inlier PnP) yang memutuskan.

### 2.6 Verifikasi pose di dalam ruangan

- **Taira dkk.** *Is This the Right Place? Geometric-Semantic Pose Verification for Indoor Visual
  Localization.* ICCV 2019, hlm. 4372-4382.
  [DOI 10.1109/ICCV.2019.00447](https://doi.org/10.1109/ICCV.2019.00447),
  [arXiv 1908.04598](https://arxiv.org/abs/1908.04598).
- Fokusnya tahap kedua: memilih pose terbaik di antara beberapa kandidat, karena indoor bertekstur
  lemah dan berpola berulang. Memakai tampilan, geometri, dan semantik.
- **Arti:** memilih peta sama dengan memilih di antara kandidat pose dari peta berbeda. Untuk eutopos
  cukup kriteria geometris yang sudah ada (jumlah inlier dan rasio inlier). ⚠️ Verifikasi berbasis
  semantik atau view synthesis belum diperlukan, dan belum dicek lisensi kodenya.

### 2.7 Deteksi lantai dari sensor (Kim & Shin 2025)

- **Kim, Shin.** *Deep Learning-Based Multi-Floor Indoor Localization Using Smartphone IMU Sensors
  With 3D Location Initialization.* IEEE Access 13, 101532-101544, 2025.
  [DOI 10.1109/ACCESS.2025.3578354](https://doi.org/10.1109/ACCESS.2025.3578354). Sudah diverifikasi di
  `docs/research-paper.md` bagian 6.
- Magnetometer menentukan lantai awal, **barometer mendeteksi perpindahan lantai**. Akurasi deteksi
  lantai 92,06% dan 93,7%, dengan satu ponsel di satu jalur.
- Barometer Android adalah sensor perangkat keras yang *"available only if a device manufacturer has
  built them into a device"*
  ([Android environment sensors](https://developer.android.com/develop/sensors-and-location/sensors/sensors_environment)).
  ⚠️ Keberadaan barometer di ponsel uji belum dicek.
- **Arti:** barometer lebih cocok untuk **mendeteksi perubahan lantai** (relatif) daripada menebak
  lantai absolut dari nol. Itu melengkapi prior ARCore, yang sudah menangkap perubahan tinggi di tangga
  tetapi ⚠️ belum terverifikasi di dalam lift.

### 2.8 COLMAP dan pycolmap: penggabungan, penyelarasan, pembaruan

Dari [COLMAP FAQ](https://colmap.github.io/faq.html) (BSD):

- **Menggabungkan sub-model** (`colmap model_merger`) hanya bisa kalau keduanya *"have common
  registered images"*, disusul `bundle_adjuster` global. Peta area yang dibangun dari rekaman
  berbeda tidak punya gambar bersama, jadi penggabungan jenis ini tidak langsung berlaku.
- **Geo-registration** (`colmap model_aligner`): transformasi similaritas 3D dari posisi pusat kamera
  acuan, minimal 3 gambar, diestimasi dengan RANSAC. Ini jalur penyelarasan ke kerangka gedung yang
  tidak membutuhkan tumpang tindih visual antar-peta.
- **Menambah gambar ke rekonstruksi** (`image_registrator`, atau `mapper --input_path` untuk
  melanjutkan). FAQ memperingatkan: *"the coordinate frame of the model can change"* setelah `mapper`
  atau `bundle_adjuster`. **Setiap pembangunan ulang wajib diikuti penyelarasan ulang ke kerangka
  gedung.**

Dari pycolmap 4.2.0 terpasang (dibaca dengan `help()` di `.venv`):

| Fungsi | Guna untuk banyak peta |
|---|---|
| `align_reconstruction_to_locations(src, tgt_image_names, tgt_locations, min_common_images, ransac_options)` | Menyelaraskan satu peta area ke kerangka gedung dari posisi terukur |
| `estimate_sim3d_robust` | Sudah dipakai eutopos untuk titik acuan |
| `align_reconstructions_via_reprojections`, `..._via_points`, `..._via_proj_centers` | Menyelaraskan dua rekonstruksi yang berbagi gambar. Berguna kalau versi baru dan versi lama sama-sama berisi gambar kueri yang dilokalisasi |
| `compare_reconstructions(...)` | Membandingkan dua rekonstruksi, untuk memeriksa pergeseran antar-versi |
| `Reconstruction.transform(sim3d)` | Menerapkan Sim3 ke seluruh peta, sehingga peta yang terbit sudah berada di kerangka gedung |
| `hierarchical_mapping(...)` | Docstring: mempartisi scene ke klaster tumpang tindih, merekonstruksi terpisah, lalu **menggabungkannya menjadi satu rekonstruksi**. Alat untuk area yang terlalu besar bagi satu peta, bukan untuk mengelola banyak area |
| `PosePrior`, `create_pose_prior_bundle_adjuster` | Memasukkan pose prior ke bundle adjustment. ⚠️ Docstring kosong dan belum diuji dengan pose ARCore; berpotensi memberi skala metrik dari rekaman aplikasi capture |

### 2.9 Pemetaan jangka panjang (lifelong)

- **Churchill, Newman.** *Experience-based navigation for long-term localisation.* IJRR 32(14),
  1645-1661, 2013. [DOI 10.1177/0278364913499193](https://doi.org/10.1177/0278364913499193).
  Abstrak: kegagalan melokalisasi pada cukup banyak "pengalaman" sebelumnya dianggap tanda model belum
  memadai, dan memicu penyimpanan urutan gambar terkini sebagai **pengalaman baru**. Jumlah pengalaman
  yang dibutuhkan cenderung konstan seiring waktu (3 bulan, 37 km data mobil).
  **Arti:** laju gagal lokalisasi per area adalah pemicu alami pembangunan ulang peta.
- **Mühlfellner dkk.** *Summary Maps for Lifelong Visual Localization.* Journal of Field Robotics
  33(5), 561-590, 2016. [DOI 10.1002/rob.21595](https://doi.org/10.1002/rob.21595). ⚠️ Hanya metadata
  yang diverifikasi. Isinya (meringkas peta yang terus tumbuh) belum dibaca, jadi jangan dikutip lebih
  jauh sebelum PDF dibaca.

---

## 3. Apa yang dilakukan industri

Semua layanan di bawah ini **berbasis cloud atau tertutup**, jadi tidak boleh dipakai di platform PA
(arah mengikat: fully local). Mereka dikaji hanya sebagai rujukan pola.

| Vendor | Cara memilih peta | Cara mengelola banyak peta | Sumber |
|---|---|---|---|
| Google ARCore Geospatial (VPS) | GPS dan sensor perangkat menentukan lingkungan, lalu dicocokkan ke model VPS dari Street View | Satu model global dari citra Street View | [Geospatial](https://developers.google.com/ar/develop/geospatial), [VPS availability](https://developers.google.com/ar/develop/unity-arf/geospatial/check-vps-availability) |
| Apple ARKit location anchors | GPS menentukan citra lokalisasi yang diunduh, lalu kamera dicocokkan | Citra dari jalan, hanya luar ruangan | [ARGeoTrackingConfiguration](https://developer.apple.com/documentation/arkit/argeotrackingconfiguration) |
| Azure Spatial Anchors (sudah pensiun) | *Sensor fingerprint*: GPS di luar, WiFi dan BLE di dalam, untuk indeks spasial anchor | Indeks spasial jawaban kasar, lalu relokalisasi visual | [coarse-reloc.md, arsip MicrosoftDocs](https://github.com/MicrosoftDocs/azure-docs/blob/279abd3127e6db0db97dc83e663070ce7840ca87/articles/spatial-anchors/concepts/coarse-reloc.md) |
| Niantic Lightship VPS | Foto kueri + lokasi GPS, dicocokkan ke peta yang ada di lokasi itu | Peta per lokasi, dibangun dari banyak pindaian (crowdsourcing), dibangun ulang saat "reactivation" | [VPS FAQ, arsip](http://web.archive.org/web/20260119144632/https://niantic.dev/docs/ardk/vps/vps_faq.html) |
| Immersal | Klien mengirim daftar `mapIds`; mode Prior memakai posisi kamera dari pelacakan AR relatif terhadap peta terakhir; mode GeoPose memakai lintang-bujur + radius | Peta terpisah per area, penyelarasan ke satu kerangka, atau *stitching* peta yang bertumpang tindih (maks. 8) | [How To Map](https://developers.immersal.com/docs/mapsmapping/howtomap/), [Stitching](https://developers.immersal.com/docs/mapsmapping/developerportal/stitching-maps/), [Aligning](https://developers.immersal.com/docs/mapsmapping/developerportal/aligning-maps/), kode [imdk-unity](https://github.com/immersal/imdk-unity) |
| MultiSet | Petunjuk sebagai filter sebelum pencocokan visual: `hintMapCodes`, `hintPosition` + `hintRadius`, `hintFloorHeight`, `geoHint` | MapSet (area berbeda, satu kerangka), Map Versioning (area sama, waktu berbeda), penggabungan lewat tumpang tindih, manual, atau *georeference* | [Localization](https://docs.multiset.ai/fundamentals/localization.md), [MapSet](https://docs.multiset.ai/fundamentals/mapset-multiple-maps.md), [Map Versioning](https://docs.multiset.ai/fundamentals/map-versioning.md) |

### 3.1 Google ARCore Geospatial

- API memakai *"device sensor and GPS data to detect the device's environment"*, lalu mencocokkan ke
  model VPS yang dibangun dari citra Street View
  ([Geospatial](https://developers.google.com/ar/develop/geospatial)).
- Di tempat dengan akurasi GPS rendah *"such as indoor spaces and dense urban environments, the API
  will rely on VPS coverage"*, dan ketersediaan VPS bisa dicek per posisi horizontal sebelum sesi AR
  ([Check VPS availability](https://developers.google.com/ar/develop/unity-arf/geospatial/check-vps-availability)).
- **Pola:** prior lokasi kasar (GPS) memilih potongan peta global. Tidak relevan langsung untuk
  eutopos karena GPS tidak berguna di lantai 10 gedung beton.

### 3.2 Apple ARKit location anchors

- *"Based on the user's GPS coordinates, ARKit downloads imagery that depicts the physical environment
  in that area"*, lalu kamera dicocokkan ke citra itu. *"Geotracking occurs exclusively outdoors"*
  ([ARGeoTrackingConfiguration](https://developer.apple.com/documentation/arkit/argeotrackingconfiguration),
  dibaca dari JSON dokumentasi resmi).
- **Pola:** sama dengan Google. Prior lokasi menentukan potongan peta yang dimuat.

### 3.3 Azure Spatial Anchors: coarse relocalization

Halaman resminya sudah dihapus dari Microsoft Learn. Teks dibaca dari riwayat repo
[MicrosoftDocs/azure-docs](https://github.com/MicrosoftDocs/azure-docs/blob/279abd3127e6db0db97dc83e663070ce7840ca87/articles/spatial-anchors/concepts/coarse-reloc.md)
(versi `ms.date: 01/28/2021`). Layanan pensiun 20 November 2024 menurut staf Microsoft di
[Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/1433376/azure-spatial-anchors-retirement-recommended-repla).

- Jawaban kasar berbentuk *"You're close to these anchors. Try to locate one of them"*.
- Di luar ruangan memakai GPS. *"When GPS is unavailable or unreliable, like when you're indoors, the
  sensor data consists of the Wi-Fi access points and Bluetooth beacons in range."*
- Dianjurkan untuk ruang *"larger than a tennis court"*.
- Perkiraan radius ruang pencarian: GPS 20 sampai 30 m, WiFi 50 sampai 100 m, BLE 70 m.
- Keterbatasan WiFi di Android: mulai API level 28 pemindaian dibatasi *"four calls every 2
  minutes"*. iOS tidak menyediakan kekuatan sinyal WiFi.
- Beacon: UUID unik, minimal tiga beacon terjangkau dari mana pun, dan cakupan harus diuji manual.
- **Pola:** radio hanya untuk jawaban kasar dengan radius puluhan meter, lalu pencocokan visual
  menyelesaikan. Radius WiFi 50 sampai 100 m **lebih besar dari satu lantai lorong**, jadi WiFi paling
  banter membantu memilih gedung atau sayap, bukan area.

### 3.4 Niantic Lightship VPS

Dari [VPS FAQ ARDK 2.5.2, arsip Wayback 2026-01-19](http://web.archive.org/web/20260119144632/https://niantic.dev/docs/ardk/vps/vps_faq.html)
(halaman asli sekarang dialihkan dan tidak memuat isi yang sama):

- *"the service takes a query image from the user's device along with their GPS location as inputs
  and attempts to localize them using the map(s) that exist at that location."*
- Peta dibangun dari pindaian AR banyak orang (pemain, pengembang, surveyor). Aktivasi butuh
  minimal 10 pindaian yang lolos cek kualitas, dengan selisih waktu minimal 5 jam antara pindaian
  tertua dan terbaru. Sebagian besar pindaian dipakai membangun peta, **sisanya untuk validasi dan
  mengukur kualitas lokalisasi**.
- Pindaian digabung menjadi satu peta per lokasi, dan *"it is not yet possible to add new scans to an
  existing fused map"*. Reaktivasi (minimal 5 pindaian baru) **membangun peta gabungan baru**.
- Dianjurkan pindaian dari banyak kondisi (misalnya hari hujan).
- **Pola yang paling mirip keputusan eutopos:** banyak penyumbang, server membangun, sebagian data
  ditahan untuk validasi, pembaruan = membangun ulang. Yang berbeda: Niantic memilih peta dengan GPS,
  eutopos harus memilih tanpa GPS.

### 3.5 Immersal

- Dokumen [How To Map](https://developers.immersal.com/docs/mapsmapping/howtomap/): *"Large indoor
  spaces can be divided into separate maps for each area or room. This makes it easy to update any
  areas that may change over time."* dan *"Not all areas need to be connected in just one map."* Ini
  dukungan langsung untuk keputusan peta per area.
- [Stitching](https://developers.immersal.com/docs/mapsmapping/developerportal/stitching-maps/): peta
  bertetangga yang punya tumpang tindih bisa digabung, *"up to 8 maps"*.
  [Aligning](https://developers.immersal.com/docs/mapsmapping/developerportal/aligning-maps/): satu
  *root map* menjadi acuan transform peta lain.
- **Dari kode** [immersal/imdk-unity](https://github.com/immersal/imdk-unity) (commit `6fd5c0b`,
  ⚠️ repo **tanpa berkas lisensi**, hanya dibaca, jangan disalin):
  - `ServerLocalization.cs`: setiap permintaan membawa `mapIds` dari klien. Dengan
    `SolverType.Prior`, posisi kamera dari pelacakan AR dipetakan ke ruang peta yang terakhir berhasil
    (`m_previouslyLocalizedMapId`) dan dikirim sebagai `priorPos` dengan `m_PriorRadius` bawaan 6,0.
    Kalau peta terakhir tidak ditemukan, prior di-*reset*.
  - `GeoPoseLocalization.cs`: mengirim lintang, bujur, dan `m_SearchRadius` bawaan 200 (meter menurut
    label editornya).
- **Pola:** prior dari pelacakan AR relatif terhadap peta terakhir, dengan radius kecil, dan reset
  ketika prior tidak berlaku.

### 3.6 MultiSet

Dari dokumentasi resmi (versi Markdown, dibaca 2026-09-29):

- **Filter sebelum pencocokan visual**
  ([Localization](https://docs.multiset.ai/fundamentals/localization.md)): *"By default the search
  covers the entire map. In large maps or multi-floor buildings this can be slow and prone to confusion
  between visually similar areas."* Urutan filter: `hintMapCodes` (peta tertentu dalam MapSet), lalu
  `hintPosition`/`geoHint` + `hintRadius`, lalu `hintFloorHeight` (pita Y), lalu pencocokan visual.
  Posisi hasil lokalisasi sebelumnya boleh langsung dipakai sebagai `hintPosition` untuk kueri
  berikutnya.
- **Radius menurut sumber prior**
  ([HintRadius](https://docs.multiset.ai/fundamentals/localization/hint-radius.md)): bawaan 25 m,
  rentang 5 sampai 100 m. Saran: hasil lokalisasi sebelumnya dengan pelacakan perangkat 5 sampai 15 m,
  QR atau titik awal 5 sampai 10 m, BLE/WiFi 10 sampai 25 m, GPS luar 25 sampai 50 m. *"If localization
  starts failing with a tight radius, the hint is probably drifting outside the search area: widen the
  radius or refresh the hint."* Juga: bola 25 m bisa mencakup beberapa lantai, jadi gabungkan dengan
  `hintFloorHeight`.
- **Lantai** ([HintFloorHeight](https://docs.multiset.ai/fundamentals/localization/hint-floor-height.md)):
  menyaring gambar referensi menurut Y kamera, dengan saran penyangga sekitar ±0,3 m, untuk mengurangi
  *"cross-floor mismatches"*.
- **MapSet** ([MapSet](https://docs.multiset.ai/fundamentals/mapset-multiple-maps.md)): koordinat
  setiap peta relatif terhadap peta pertama. Peta baru diselaraskan ke seluruh MapSet, dan *"existing
  maps are not impacted"*. Praktik baik: bagi venue menjadi bagian logis, beri tumpang tindih cukup.
- **Tumpang tindih**
  ([Merging with Overlap](https://docs.multiset.ai/fundamentals/mapset-multiple-maps/merging-maps-with-overlap.md)):
  *"around 5-10 meters of overlap between maps to be merged or 15-20% overlap area"*. Penyelarasan
  memakai pipeline VPS mereka, bukan ICP.
- **Tanpa tumpang tindih**
  ([Merging without Overlap](https://docs.multiset.ai/fundamentals/mapset-multiple-maps/merging-maps-without-overlap.md)):
  banyak orang boleh memetakan area berbeda bersamaan lalu digabung. Durasi ideal satu bagian
  *"up to 5 minutes"*. Penggabungan dilakukan dengan melokalisasi di peta pertama lalu berjalan ke peta
  berikutnya dan melokalisasi lagi (jadi pelacakan perangkat menjembatani celah).
- **Georeference**
  ([Merging by Georeference](https://docs.multiset.ai/fundamentals/mapset-multiple-maps/merging-maps-by-georeference.md)):
  pindaian yang tidak saling melihat digabung lewat kerangka survei bersama. *"the placement is exact
  rather than estimated"* dan *"Maps already in the set never move."* **Ini padanan langsung pendekatan
  eutopos**: setiap peta area diselaraskan ke kerangka gedung lewat titik acuan terukur.
- **Map Versioning** ([Map Versioning](https://docs.multiset.ai/fundamentals/map-versioning.md)):
  versi untuk area yang sama pada waktu berbeda, MapSet untuk area berbeda. Versi baru diselaraskan ke
  peta dasar dengan transform rigid, konten tetap di kerangka peta dasar. Beberapa versi boleh aktif
  sekaligus, sehingga pembaruan sebagian praktis: versi lama tetap aktif untuk bagian yang tidak
  berubah. Setidaknya satu peta harus tetap aktif.

---

## 4. Prinsip best practice

Disarikan dari bagian 2 dan 3. Setiap prinsip disertai sumbernya.

1. **Persempit dulu, cocokkan kemudian.** Pencocokan fitur lokal dan PnP mahal, jadi hanya
   dijalankan pada kandidat yang lolos tahap kasar (hloc 2.1, LaMAR 2.4, Azure 3.3, MultiSet 3.6).
2. **Prior adalah filter, bukan jawaban.** Prior (lantai, posisi, radio) hanya membuang kandidat
   sebelum retrieval visual. Pose tetap dari pencocokan visual (LaMAR `filter_by_*`, urutan filter
   MultiSet).
3. **Filter harus gagal terbuka.** Tanpa prior, atau kalau lokalisasi dengan prior gagal, perluas
   pencarian (LaMAR mempertahankan semua gambar kalau tidak ada radio, MultiSet menyarankan memperlebar
   radius, Immersal me-*reset* prior).
4. **Prior terkuat datang gratis dari pelacakan perangkat.** Setelah koreksi pertama, posisi di
   kerangka gedung diketahui terus dari ARCore. LaMAR mematikan radio saat prior ini ada, hloc memakai
   konsistensi temporal untuk memilih gedung dan lantai di InLoc, Immersal dan MultiSet memakai hasil
   sebelumnya sebagai prior dengan radius kecil.
5. **Pemilih kasar pasti kadang salah, verifikasi geometris yang memutuskan.** Jangan hanya mencoba
   peta teratas pada ruang yang mirip (ESAC 2.5, covisibility clustering hloc 2.1, Taira 2.6). Tolak
   hasil dengan inlier rendah.
6. **Lantai adalah sumber aliasing terbesar di dalam gedung.** InLoc sengaja memakai lantai lain
   sebagai pengecoh, MultiSet punya filter khusus lantai (2.3, 3.6). Informasi lantai layak dijadikan
   prior tersendiri.
7. **Satu kerangka gedung, satu transform per peta, konten tidak pernah bergeser.** POI dan NavMesh
   hidup di kerangka gedung. Menambah atau memperbarui peta tidak boleh menggeser peta lain (MultiSet
   MapSet dan Georeference, Immersal Aligning).
8. **Peta per area supaya bisa diperbarui sebagian** (Immersal How To Map). Bedakan "area baru"
   (tambah peta) dari "area sama, waktu baru" (versi baru), seperti MultiSet memisahkan MapSet dan Map
   Versioning.
9. **Pembaruan = bangun versi baru, selaraskan ulang, validasi, tukar.** Jangan menambal peta aktif
   di tempat (Niantic reactivation membangun peta baru, COLMAP memperingatkan kerangka bisa berubah
   setelah `mapper` atau `bundle_adjuster`).
10. **Tahan sebagian data untuk validasi** sebelum peta terbit (Niantic memisahkan pindaian untuk
    validasi). Sejalan dengan prinsip eutopos "jangan membakar set uji" (`docs/design-notes.md` §5).
11. **Kegagalan lokalisasi adalah sinyal perawatan.** Laju gagal per area memicu pemetaan ulang
    (Churchill & Newman 2.9).

---

## 5. Rekomendasi bertahap untuk eutopos

### 5.1 Best practice (tujuan akhir)

Alur lokalisasi di server untuk gedung dengan banyak area:

```text
masukan: foto, intrinsik, opsional: prior_posisi (kerangka gedung) + umur prior, opsional: lantai

1. Kandidat area C:
   - ada prior segar  -> area yang wilayahnya (kotak pusat kamera + margin) dalam radius r dari prior
   - ada lantai       -> area di lantai itu
   - tidak ada        -> semua area aktif
2. Retrieval MegaLoc atas gambar basis data area di C saja
   (pairs_from_retrieval: db_prefix = prefiks area C, db_descriptors = berkas per area)
3. Voting top-k per area. Urutkan area menurut suara.
4. PnP (QueryLocalizer + pose_from_cluster) di area teratas.
   Kalau inlier < ambang dan area kedua suaranya dekat, coba area kedua.
5. Gagal semua dan C bukan "semua area" -> ulangi sekali dengan semua area (gagal terbuka).
6. Kembalikan pose di kerangka gedung + area_id + map_version + inlier + status.
```

Catatan desain:

- **Peta terbit sudah berada di kerangka gedung** (`Reconstruction.transform` dengan Sim3 dari titik
  acuan saat publikasi). Server tidak perlu menerapkan transform per permintaan.
- **Prior dihitung klien**, karena klien sudah punya `T_sesi←gedung` dari koreksi terakhir
  (`docs/design-notes.md` §1): `prior = T_gedung←sesi × posisi_kamera_ARCore`. Klien juga mengirim
  jarak tempuh sejak koreksi terakhir, supaya server bisa melebarkan radius sesuai drift. Radius awal
  bisa mengikuti saran MultiSet untuk prior dari pelacakan (5 sampai 15 m), lalu **disetel dengan data
  sendiri** pada set penyetelan, bukan set uji.
- **Tumpang tindih 5 sampai 10 m antar-area** (angka MultiSet) memberi dua hal: perpindahan area tanpa
  celah, dan **pemeriksaan konsistensi**: foto di zona tumpang tindih dilokalisasi di kedua peta, selisih
  posisinya adalah galat penyelarasan antar-peta. Angka ini layak menjadi syarat persetujuan terbit.
- **Pembaruan satu area** (alur yang sudah diputuskan: capture, build, setujui):
  1. Bangun ulang peta area dari rekaman baru (dan rekaman lama yang masih relevan).
  2. Selaraskan ke kerangka gedung: titik acuan (`estimate_sim3d_robust`), dan sebagai pemeriksaan
     silang, lokalisasi sebagian frame baru di versi aktif lalu bandingkan pusat kamera.
  3. Jalankan set uji tertahan area itu. Bandingkan dengan versi aktif.
  4. Manusia menyetujui. Tukar penunjuk `versi_aktif` secara atomik. Simpan versi lama untuk *rollback*.
- **Pemicu pembaruan:** laju gagal atau median inlier per area yang memburuk (prinsip 11).

### 5.2 Tahapan

| Tahap | Kapan | Yang dibangun | Yang sengaja tidak dibangun |
|---|---|---|---|
| **0. PA** | Sekarang, satu area (lantai 10) | `area_id` dan `map_version` di model data dan di respons `/localize`. Kolom `versi_peta` di `building` (`docs/design-notes.md` §3) cukup dipindah ke tingkat area | Pemilihan peta, voting, prior, radio. Dengan satu area semuanya no-op |
| **0b. Eksperimen opsional PA** | Kalau spike selesai dan waktu ada | (a) Pecah peta lantai 10 menjadi dua area secara offline, ukur seberapa sering retrieval + voting memilih area benar. (b) Ukur pengaruh prior posisi berradius terhadap akurasi dan latensi di lorong berulang | Tidak masuk layanan. Hasilnya bukti skalabilitas untuk laporan |
| **1. Beberapa area, satu lantai** | Setelah PA | Alur 5.1 langkah 1 sampai 6 dengan prior ARCore dari klien, tumpang tindih antar-area, pemeriksaan konsistensi saat terbit | Radio, barometer |
| **2. Banyak lantai** | Saat lantai kedua dipetakan | Petunjuk lantai dari aplikasi (lantai tujuan atau pilihan pengguna, lalu diperbarui ARCore di tangga), deteksi perpindahan lantai dengan barometer bila ponsel punya | Penebak lantai absolut dari magnetometer (Kim & Shin), kecuali prior lain terbukti gagal |
| **3. Skala gedung, banyak penyumbang** | Kalau cold start tanpa prior terbukti lambat atau sering salah | Filter WiFi ala LaMAR untuk cold start, gagal terbuka. Laju gagal per area sebagai pemicu rebuild. Regresi otomatis per versi | BLE beacon (perangkat keras tambahan, bertentangan dengan "tanpa penanda") |

### 5.3 Kompromi dan risikonya

| Pilihan | Keuntungan | Kerugian atau risiko |
|---|---|---|
| Retrieval atas semua area tanpa prior | Paling sederhana, tidak butuh data dari klien | Pengecoh bertambah seiring jumlah area (InLoc). ⚠️ Biaya retrieval tumbuh linear dengan jumlah gambar basis data, belum diukur di 2 vCPU |
| Prior dari ARCore | Gratis, paling kuat, tidak butuh izin tambahan | Tidak ada untuk foto pertama. Salah kalau ARCore kehilangan pelacakan, jadi harus gagal terbuka dan klien mengirim umur prior |
| Petunjuk lantai dari aplikasi | Murah, menghapus aliasing antar-lantai | Bergantung pengguna atau alur aplikasi. Salah lantai berarti gagal, jadi tetap gagal terbuka |
| WiFi BSSID | Tanpa perangkat keras tambahan | Android membatasi 4 pemindaian per 2 menit (Azure 3.3, `docs/research-paper.md` §9.2). Radius 50 sampai 100 m lebih besar dari satu area. Butuh izin lokasi dan data survei radio per versi peta. ⚠️ Keberagaman AP di gedung PENS belum dicek |
| Menggabungkan semua area menjadi satu peta | Satu model, tanpa pemilihan | Setiap perubahan kecil memaksa membangun ulang seluruh gedung, bertentangan dengan keputusan per area. `model_merger` butuh gambar bersama |
| Semua peta area dimuat di RAM server | Latensi rendah | ⚠️ Kebutuhan memori per area belum diukur. Kalau tidak muat di server instansi, muat sesuai permintaan dengan cache |

### 5.4 Lisensi komponen yang disebut

| Komponen | Lisensi | Status untuk repo AGPL-3.0 |
|---|---|---|
| hloc | Apache-2.0 | ✅ sudah dipakai |
| COLMAP / pycolmap | BSD | ✅ sudah dipakai |
| LaMAR (`lamar-benchmark`) | Kode MIT, dokumen CC-BY-4.0 | ✅ ide filter radio dan filter pose boleh diadaptasi |
| kapture-localization (Naver) | BSD-3-Clause (menurut GitHub API) | ✅ kalau dibutuhkan, belum dipakai |
| ESAC (`vislearn/esac`) | BSD-3-Clause | Lisensi bersih, tapi metodenya tidak cocok (regresi koordinat scene, dilatih per scene) |
| Immersal `imdk-unity` | Tidak ada berkas lisensi | 🚨 hanya dibaca sebagai rujukan, jangan disalin |
| SuperPoint, SuperGlue (dipakai di angka InLoc hloc) | Non-komersial | 🚨 hanya dikutip angkanya, tidak dipakai |
| Layanan Google, Apple, Niantic, Immersal, MultiSet | Layanan komersial cloud | 🚨 dilarang oleh arah PA, hanya rujukan pola |
| Bobot MegaLoc | MIT (halaman model `gberton/MegaLoc` di Hugging Face, dicatat di `docs/spike-plan.md`) | ✅ sudah dipakai |

---

## 6. Yang belum terverifikasi

1. ⚠️ Angka LaMAR (peningkatan sekitar 20% dari lokalisasi berurutan, *time-to-recall* 1,40 s dan
   3,58 s) dibaca lewat ringkasan ar5iv, belum dicocokkan ke PDF.
2. ⚠️ Isi *Summary Maps for Lifelong Visual Localization* belum dibaca, hanya metadata.
3. ⚠️ Biaya retrieval dan memori per area di server CPU 2 vCPU. Harus diukur sendiri, sama seperti
   latensi hloc.
4. ⚠️ Radius prior yang cocok untuk ARCore di lorong PENS. Saran MultiSet (5 sampai 15 m) hanya titik
   awal. Harus disetel pada set penyetelan terpisah dari set uji.
5. ⚠️ Keberadaan barometer di ponsel uji, dan perilaku pelacakan ARCore di dalam lift.
6. ⚠️ `pycolmap.PosePrior` dengan pose ARCore sebagai prior pembangunan peta (docstring kosong, belum
   diuji). Kalau berhasil, bisa mengurangi ketergantungan pada titik acuan untuk skala, tapi titik
   acuan tetap wajib untuk kerangka gedung.
7. ⚠️ Metode verifikasi semantik Taira dkk.: lisensi kode dan biaya CPU belum dicek.
8. ⚠️ Dokumentasi Azure dibaca dari riwayat git karena halaman resminya dihapus setelah pensiun.
   Dokumentasi Niantic dibaca dari arsip Wayback karena halaman aslinya dialihkan.
9. ⚠️ Label satuan radius Immersal (`m_PriorRadius` 6,0 dan `m_SearchRadius` 200) diambil dari kode
   dan label editor, bukan dari dokumentasi.

---

## 7. Daftar sumber

### Paper (metadata dicek ke Crossref)

- Sarlin, Cadena, Siegwart, Dymczyk. *From Coarse to Fine: Robust Hierarchical Localization at Large
  Scale.* CVPR 2019. https://doi.org/10.1109/CVPR.2019.01300 · https://arxiv.org/abs/1812.03506
- Taira dkk. *InLoc: Indoor Visual Localization with Dense Matching and View Synthesis.* CVPR 2018.
  https://doi.org/10.1109/CVPR.2018.00752 · https://arxiv.org/abs/1803.10368
- Sarlin dkk. *LaMAR: Benchmarking Localization and Mapping for Augmented Reality.* ECCV 2022.
  https://doi.org/10.1007/978-3-031-20071-7_40 · https://arxiv.org/abs/2210.10770
- Brachmann, Rother. *Expert Sample Consensus Applied to Camera Re-Localization.* ICCV 2019.
  https://doi.org/10.1109/ICCV.2019.00762 · https://arxiv.org/abs/1908.02484
- Taira dkk. *Is This the Right Place? Geometric-Semantic Pose Verification for Indoor Visual
  Localization.* ICCV 2019. https://doi.org/10.1109/ICCV.2019.00447 · https://arxiv.org/abs/1908.04598
- Kim, Shin. *Deep Learning-Based Multi-Floor Indoor Localization Using Smartphone IMU Sensors With 3D
  Location Initialization.* IEEE Access 13, 2025. https://doi.org/10.1109/ACCESS.2025.3578354
- Churchill, Newman. *Experience-based navigation for long-term localisation.* IJRR 32(14), 2013.
  https://doi.org/10.1177/0278364913499193
- Mühlfellner dkk. *Summary Maps for Lifelong Visual Localization.* JFR 33(5), 2016.
  https://doi.org/10.1002/rob.21595 (⚠️ hanya metadata)

### Kode (dibaca langsung)

- hloc, commit `c13273b`: `third_party/Hierarchical-Localization/hloc/pairs_from_retrieval.py`,
  `hloc/localize_sfm.py`, `hloc/pairs_from_poses.py`, `hloc/pipelines/CMU/pipeline.py`,
  `hloc/pipelines/4Seasons/utils.py`, `README.md` · https://github.com/cvg/Hierarchical-Localization
- Kiriman InLoc "temporal": https://www.visuallocalization.net/details/10937/
- LaMAR, commit `5ffd891`: `lamar/run.py`, `lamar/utils/retrieval.py`,
  `lamar/tasks/chunk_alignment.py`, `scantools/utils/radio_mapping.py` ·
  https://github.com/microsoft/lamar-benchmark
- pycolmap 4.2.0 (paket terpasang di `.venv` repo eutopos-vps, dibaca dengan `help()`)
- COLMAP FAQ: https://colmap.github.io/faq.html
- ESAC: https://github.com/vislearn/esac
- Immersal Unity SDK, commit `6fd5c0b`: `Runtime/Scripts/XR/Localization/ServerLocalization.cs`,
  `GeoPoseLocalization.cs`, `Localizer.cs` · https://github.com/immersal/imdk-unity

### Dokumentasi vendor

- Google ARCore Geospatial: https://developers.google.com/ar/develop/geospatial ·
  https://developers.google.com/ar/develop/unity-arf/geospatial/check-vps-availability
- Apple ARKit: https://developer.apple.com/documentation/arkit/argeotrackingconfiguration
- Azure Spatial Anchors, coarse relocalization (arsip git):
  https://github.com/MicrosoftDocs/azure-docs/blob/279abd3127e6db0db97dc83e663070ce7840ca87/articles/spatial-anchors/concepts/coarse-reloc.md
- Azure Spatial Anchors, pensiun:
  https://learn.microsoft.com/en-us/answers/questions/1433376/azure-spatial-anchors-retirement-recommended-repla
- Niantic Lightship VPS FAQ (arsip Wayback):
  http://web.archive.org/web/20260119144632/https://niantic.dev/docs/ardk/vps/vps_faq.html
- Immersal: https://developers.immersal.com/docs/mapsmapping/howtomap/ ·
  https://developers.immersal.com/docs/mapsmapping/developerportal/stitching-maps/ ·
  https://developers.immersal.com/docs/mapsmapping/developerportal/aligning-maps/
- MultiSet: https://docs.multiset.ai/fundamentals/localization.md ·
  https://docs.multiset.ai/fundamentals/localization/hint-radius.md ·
  https://docs.multiset.ai/fundamentals/localization/hint-floor-height.md ·
  https://docs.multiset.ai/fundamentals/mapset-multiple-maps.md ·
  https://docs.multiset.ai/fundamentals/mapset-multiple-maps/merging-maps-with-overlap.md ·
  https://docs.multiset.ai/fundamentals/mapset-multiple-maps/merging-maps-without-overlap.md ·
  https://docs.multiset.ai/fundamentals/mapset-multiple-maps/merging-maps-by-georeference.md ·
  https://docs.multiset.ai/fundamentals/map-versioning.md
- Android environment sensors:
  https://developer.android.com/develop/sensors-and-location/sensors/sensors_environment
