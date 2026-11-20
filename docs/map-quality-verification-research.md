# Riset: Verifikasi Kualitas Peta dan Skala Metrik Tanpa Ukur Meteran

Riset untuk satu pertanyaan desain eutopos: bagaimana memastikan peta hasil scan video **layak dipakai
navigasi** dan **berskala meter** tanpa mewajibkan developer mengukur titik dengan meteran, sambil tetap
menyediakan jalur ukur penuh untuk laporan PA.

**Cara verifikasi.** Dokumentasi vendor dibaca langsung dari situs resmi (MultiSet, Google ARCore, Apple
ARKit, Niantic Spatial, Immersal). Kode Immersal dibaca dari klon `immersal/imdk-unity` (commit
`fba192e`). COLMAP dibaca dari `colmap.github.io` (CLI dan FAQ) dan kode sumber `src/colmap/exe/model.cc`
cabang `main`. Opsi bawaan pycolmap dibaca dari paket terpasang di `.venv` (**4.2.0**, bukan 4.2.1
seperti yang tertulis di brief). Metadata paper dicek ke Crossref, isi paper dibaca dari arXiv/ar5iv.
Kode eutopos yang menjadi acuan: `spike/eval_meter.py`, `server/alignment.py`, `server/localizer.py`,
`server/navgraph.py`, `spike/inspect_map.py`. Tanda ⚠️ berarti belum terverifikasi penuh. Tanggal
pengecekan: 19 November 2026.

**Tiga label dipakai tegas di seluruh dokumen:** **Fakta** (bersumber, ada URL), **Inferensi** (tafsiran
saya dari fakta), **Rekomendasi** (usulan untuk eutopos).

## Ringkasan eksekutif

1. **Tidak ada vendor yang mewajibkan titik ukur per peta untuk skala.** Skala datang dari pelacakan
   perangkat (ARKit/ARCore, satuannya meter) atau LiDAR; untuk peta tanpa sensor (MultiSet, kamera
   Insta360) cukup **satu panjang yang diketahui**, misalnya pintu 2 m. Titik kontrol (≥ 3) hanya
   diminta untuk georeferensi, bukan untuk skala.
2. **Gerbang kualitas vendor saat capture bersifat kualitatif**: indikator "cukup/baik" (ARCore
   `FeatureMapQuality`, ARKit `mapped`), notifikasi keterhubungan gambar (Immersal), dan "scan gagal
   kalau tampilan berurutan tidak tersambung" (Niantic). Angka galat meter tidak ditampilkan ke pemindai.
3. **Validasi vendor yang paling dekat dengan "ground truth" adalah data tertahan**: Niantic menahan
   sebagian pindaian untuk mengukur kualitas lokalisasi; MultiSet menyediakan simulasi lokalisasi atas
   data rekaman, tetapi penilaiannya visual (frustum di mesh) plus skor confidence.
4. **Metrik SfM otomatis tersedia gratis di pycolmap 4.2.0**: jumlah frame terdaftar, jumlah potongan
   model, galat reproyeksi rata-rata, panjang track rata-rata, pengamatan per gambar. Semuanya murah,
   tetapi **tidak satu pun membuktikan skala atau geometri benar**. Galat reproyeksi rendah tetap mungkin
   pada peta yang skalanya melantur.
5. **Lokalisasi frame tertahan dari video yang sama bias optimistis** (inferensi). Ia mengukur cakupan
   peta di sepanjang lintasan rekaman, bukan generalisasi. Video kedua (arah berlawanan atau jam berbeda)
   jauh lebih jujur, sejalan dengan praktik Niantic dan LaMAR yang memisahkan sesi peta dan sesi uji.
6. **Benchmark mapan hampir semuanya memakai pseudo ground truth** (SfM, KinectFusion, LiDAR SLAM +
   SfM), dan Brachmann dkk. (ICCV 2021) membuktikan peringkat metode bisa berubah tergantung algoritma
   acuannya. Titik lantai yang diukur meteran, dengan ketidakpastian dilaporkan, setara bahkan lebih
   transparan untuk skala PA.
7. **Metrik baku untuk laporan**: median galat posisi dan persentase kueri di bawah ambang. Ambang
   indoor yang lazim 0,25 / 0,5 / 1 m (InLoc), luar ruang 0,25 / 0,5 / 5 m (Aachen), AR 10 cm / 1 m
   (LaMAR). `eval_meter.py` sudah memenuhi pola ini, tinggal menambah kolom recall per ambang.
8. **Jalur skala tercepat tanpa merepotkan developer**: arah gravitasi dari orientasi gambar (COLMAP
   `IMAGE-ORIENTATION`, tanpa ukur) ditambah **satu jarak acuan** panjang (≥ 10 m) yang ditandai di video.
   Jalur terbaik jangka panjang: rekam pose ARCore bersama video, lalu skala diturunkan dari pose itu
   (`pose_prior_mapper` / `pycolmap.PosePrior`), tanpa ukur sama sekali.
9. **Penghambat demo saat ini ada di kode, bukan di riset**: `server/localizer.py` mengembalikan `None`
   untuk pose gedung bila `align.json` tidak ada, dan `server/alignment.py` menolak `align.json` dengan
   `reference_points < 4`. Jadi peta baru tanpa ukur meteran **tidak bisa** tampil di navigasi. Butuh
   keputusan pemilik: izinkan `align.json` provisional dengan kolom `method`.
10. **Job 22 tidak lolos gerbang otomatis yang diusulkan** (78% terdaftar, 3 potongan, putus di frame
    157-158 menghadap dinding polos). Gerbang otomatis seharusnya memberi tahu developer detik ke berapa
    harus direkam ulang, bukan diam-diam memakai potongan terbesar.

---

## 1. Cara vendor menilai kualitas peta dan menetapkan skala

### 1.1 Tabel ringkas (fakta)

| Vendor | Sumber skala | Yang diminta saat capture | Indikator kualitas / syarat terbit | Sumber |
|---|---|---|---|---|
| **MultiSet** (scan ARKit/ARCore) | Pelacakan perangkat; LiDAR opsional menambah kedalaman | Jarak 1 sampai 5 m dari permukaan, gerak pelan dan konstan, lanskap, lorong dipindai **dua arah**, sesi baru harus berbagi fitur dengan sesi sebelumnya, hindari kaca, cermin, dinding polos | Tidak ada angka di halaman instruksi. Validasi lewat Simulation: status pose, skor confidence, posisi XYZ, frustum dilihat di mesh | [Mapping Instruction](https://docs.multiset.ai/fundamentals/maps/mapping-instruction.md), [Simulation](https://docs.multiset.ai/fundamentals/localization/simulation.md) |
| **MultiSet** (360° Insta360, tanpa sensor) | **Satu panjang diketahui**: `scaleFactor = panjang nyata (m) ÷ panjang di peta`. Contoh resmi: pintu 2 m terukur 2,35 unit, faktor ≈ 0,85 | Pilih dua titik pada objek di viewer splat, isi panjangnya | Skala multiplikatif (memanggil dua kali = dikalikan dua kali). Hanya untuk peta Insta360 aktif yang berdiri sendiri. Tidak ada angka akurasi | [Map Scale](https://docs.multiset.ai/fundamentals/rest-api-docs/map-scale) |
| **MultiSet** (georeferensi) | Bukan skala: menempatkan peta ke WGS84 | **≥ 3 titik kontrol**, tidak boleh horizontal berimpit | Mengembalikan `horizontalRmseMeters` (disebut indikator paling andal), `rmseMeters`, `maxErrorMeters`, residual per titik dengan `isInlier`, `tiltCheck` (`tiltAngleDeg`, `thresholdDeg`), dan `scale` bila `solveScale` (scan metrik seharusnya ≈ 1,0). Contoh permintaan memakai `outlierThresholdMeters` 2,5, contoh respons `thresholdDeg` 1,5. Halaman tidak menyebut keduanya sebagai bawaan | [Georeference API](https://docs.multiset.ai/fundamentals/rest-api-docs/georeference.md) |
| **Immersal** | ⚠️ Tidak didokumentasikan di How To Map. **Dari kode**: setiap gambar yang diunggah (`SDKImageRequest`, endpoint `capture`) membawa posisi `px,py,pz`, matriks rotasi `r00..r22`, intrinsik `fx,fy,ox,oy`, lintang-bujur. Permintaan bangun (`SDKConstructRequest`) punya `preservePoses` (bawaan `false`) dan `featureCount` (bawaan 1024) | Tumpang tindih sepertiga sampai setengah gambar, titik fitur idealnya terlihat di ≥ 3 gambar (minimum 2), setidaknya 3 sudut pandang per objek | Aplikasi Mapper memberi tahu apakah gambar berurutan tersambung; grafik koneksi gambar. Tanpa paralaks: *"the resulting map either fails or is inaccurate"* | [How To Map](https://developers.immersal.com/docs/mapsmapping/howtomap/), kode [imdk-unity](https://github.com/immersal/imdk-unity) `Runtime/Scripts/REST/REST.cs`, `RESTJobsAsync.cs` |
| **Niantic** (Lightship VPS / Scaniverse) | Pose perangkat direkam (*"Device position and orientation in 3D space"*); LiDAR menambah kedalaman | Scan maks. 5 menit, tiga putaran (datar, ke atas, ke bawah). Aktivasi lokasi: ≥ 10 pindaian lolos cek kualitas, rentang waktu ≥ 5 jam | Umpan balik meshing langsung; *"Scans can fail if the system cannot connect sequential views"*. Sebagian pindaian ditahan untuk validasi dan mengukur kualitas lokalisasi. ⚠️ Skor kualitas 0 sampai 1 di perangkat hanya terbaca dari cuplikan pencarian, halaman aslinya sudah 404 | [Scaniverse Techniques](https://www.nianticspatial.com/docs/scaniverse/techniques), VPS FAQ arsip (lihat `docs/multi-map-localization-research.md` §3.4) |
| **Google ARCore** (Cloud Anchors) | Pelacakan ARCore; *"Translation units are meters"* | Gerak mengitari titik minat, jarak kira-kira tetap, tunggu beberapa detik setelah sesi mulai | `FeatureMapQuality`: `INSUFFICIENT`, `SUFFICIENT` (akurasi berkurang), `GOOD`. Tanpa ambang angka | [FeatureMapQuality](https://developers.google.com/ar/reference/java/com/google/ar/core/Session.FeatureMapQuality), [Cloud Anchors guide](https://developers.google.com/ar/develop/java/cloud-anchors/developer-guide), [Pose](https://developers.google.com/ar/reference/java/com/google/ar/core/Pose) |
| **Google ARCore** (Geospatial) | Model VPS dari Street View | Tidak ada capture oleh pengembang | Setiap pose membawa `HorizontalAccuracy`, `VerticalAccuracy`, `OrientationYawAccuracy` sebagai **radius persentil ke-68** | [GeospatialPose](https://developers.google.com/ar/reference/java/com/google/ar/core/GeospatialPose) |
| **Apple ARKit** (ARWorldMap) | Pelacakan ARKit | Simpan peta saat status `mapped` | `WorldMappingStatus.mapped`: *"World tracking has adequately mapped the visible area"*; keandalan relokalisasi tertinggi bila disimpan saat `mapped` dan sesi baru dimulai dari posisi serupa. Location anchors hanya luar ruang | [WorldMappingStatus.mapped](https://developer.apple.com/documentation/arkit/arframe/worldmappingstatus-swift.enum/mapped), [ARGeoTrackingConfiguration](https://developer.apple.com/documentation/arkit/argeotrackingconfiguration) |
| **Mapxus, Oriient, Navisens** | Tidak ditemukan di sumber primer | Tidak ditemukan | Tidak ditemukan. Oriient: kalibrasi otomatis di latar belakang menurut tutorial pihak ketiga Mappedin, bukan dokumentasi Oriient | [Mappedin + Oriient](https://www.mappedin.com/resources/blog/indoor-orientation-with-oriient-and-mappedin/) |
| **Dent Reality** | Tidak ditemukan | Tidak ditemukan | **Klaim pemasaran**: Apple Indoor Maps sekitar 5 m, dinilai kurang untuk AR. Tidak ada angka akurasi AR milik Dent Reality | [Medium Dent Reality](https://medium.com/dent-reality/dent-reality-building-the-future-of-indoor-ar-navigation-9dd6431b31d6) |

**Klaim pemasaran MultiSet**: blog [Visual positioning from 3D GIS data](https://multiset.ai/post/visual-positioning-from-3d-gis-data)
menyebut RMSE horizontal, residual per titik, penolakan outlier bawaan 2,5 m, dan cek kemiringan
gravitasi. Angka median di bawah 5 cm di blog itu adalah akurasi lokalisasi, bukan penyelarasan, dan
tidak dapat diverifikasi.

### 1.2 Inferensi

- **Pola umum**: pemindai tidak pernah diminta ground truth per titik. Kualitas dijaga dengan (a)
  aturan capture yang mencegah putus (tumpang tindih, dua arah, hindari dinding polos), (b) indikator
  keterhubungan saat merekam, (c) validasi lokalisasi atas data tertahan setelah peta dibangun.
- **Skala dianggap masalah sensor, bukan masalah pengukuran.** Semua vendor berbasis ponsel mendapat
  meter dari VIO. Satu-satunya jalur tanpa sensor (MultiSet 360) cukup memakai satu panjang. Immersal
  mengirim pose AR per gambar, jadi hampir pasti skala diturunkan dari pose itu. ⚠️ Arti persis
  `preservePoses` tidak ditemukan di dokumentasi.
- **Angka galat meter yang dilaporkan vendor hanya muncul di georeferensi** (RMSE titik kontrol,
  MultiSet) atau sebagai **estimasi ketidakpastian per pose** (ARCore Geospatial, persentil 68). Ini
  model yang baik untuk eutopos: residual titik acuan (`residual_median_m`) dan inlier PnP per kueri
  sudah ada.
- **Kasus eutopos mirip MultiSet 360, bukan scan ARCore**, karena video ponsel direkam tanpa pose. Maka
  pola "satu panjang diketahui" paling langsung bisa ditiru.

---

## 2. Metrik gerbang kualitas otomatis untuk peta SfM

### 2.1 Metrik yang tersedia (fakta)

Semua metode di bawah ada di `pycolmap.Reconstruction` 4.2.0 terpasang. COLMAP `model_analyzer`
mencetak statistik serupa ([CLI](https://colmap.github.io/cli.html)). Opsi bawaan dibaca dari
`pycolmap.IncrementalPipelineOptions()` dan `IncrementalMapperOptions()`:
`multiple_models=True`, `min_model_size=10`, `min_num_matches=15`, `init_min_num_inliers=100`,
`abs_pose_min_num_inliers=30`, `abs_pose_min_inlier_ratio=0.25`, `filter_max_reproj_error=4.0` px,
`filter_min_tri_angle=1.5`°. hloc `reconstruction.py` memindahkan **hanya model terbesar** ke `sfm/`,
sisanya di `sfm/models/<n>/` (baris 117-139).

| Metrik | Cara hitung | Ambang di sumber | Keterbatasan |
|---|---|---|---|
| Rasio frame terdaftar | `num_reg_images()` model utama ÷ frame terekstrak | Tidak ada ambang baku di sumber primer | Frame duplikat (berdiri diam) menaikkan rasio tanpa menambah cakupan |
| Jumlah potongan model | Jumlah folder `sfm/models/*` dengan `images.bin` | COLMAP membuang model < 10 gambar (`min_model_size`) | Satu model belum berarti tidak terlipat; potongan kecil < 10 frame tidak terlihat sama sekali |
| Rentang frame yang hilang | Frame tidak terdaftar berurutan (sudah ada di `spike/inspect_map.py`, fungsi `ranges`) | Tidak ada | Lokasi putus diketahui, sebabnya tidak |
| Galat reproyeksi rata-rata | `compute_mean_reprojection_error()` | Titik dengan galat > 4 px sudah dibuang mapper, jadi rata-rata selalu kecil. NAVER LABS melaporkan SfM mereka *"under 1.5 pixels"* | **Tidak mendeteksi skala melantur atau peta terlipat**; konsisten secara lokal bisa salah secara global |
| Panjang track rata-rata | `compute_mean_track_length()` | Immersal: fitur idealnya di ≥ 3 gambar | Video 2 fps dengan langkah kecil menaikkan track length tanpa menambah keragaman sudut |
| Pengamatan per gambar | `compute_mean_observations_per_reg_image()` | Tidak ada | Mengukur kepadatan, bukan kebenaran |
| Jumlah titik 3D | `num_points3D()` | Tidak ada | Sebanding panjang rekaman, sulit dibandingkan antar-area |
| Inlier pasangan berurutan | Dari `matches.h5` hloc per pasangan sekuensial | Tidak ada | Penanda dini titik putus (job 22: pasangan 157-158 nol inlier, 227-228 31 vs median 240) |
| Lokalisasi frame tertahan | Sisihkan tiap frame ke-N sebelum mapping, lokalisasi dengan `server/localizer.py`, hitung yang ≥ `MIN_INLIERS` (50) | Tidak ada di sumber primer | Lihat 2.2 |

Pembanding kecil (fakta, diukur lokal): peta uji 9 gambar di `outputs/demo/sfm` dan
`outputs/bench-verify/kp1024-r1024/sfm` memberi galat reproyeksi 0,81 dan 0,66 px, track length 5,0 dan
4,5. Peta lantai 10 job 22 tidak ada di mesin ini, jadi angkanya belum dihitung.

Metadata acuan metrik rekonstruksi: Schönberger, Hardmeier, Sattler, Pollefeys. *Comparative Evaluation
of Hand-Crafted and Learned Local Features.* CVPR 2017,
[DOI 10.1109/CVPR.2017.736](https://doi.org/10.1109/CVPR.2017.736). ⚠️ Halaman CVF menolak akses (403),
jadi daftar metrik di paper itu belum dibaca langsung; jangan dikutip lebih jauh.

### 2.2 Held-out dari video yang sama (inferensi)

- Frame tertahan berjarak sekitar 0,5 s (2 fps) dari frame peta terdekat, dengan pencahayaan, arah
  pandang, dan orang yang sama. Hampir pasti terlokalisasi, sehingga **mengukur "apakah lintasan
  rekaman tertutup peta", bukan "apakah pengguna lain akan terlokalisasi"**.
- Pengguna navigasi sering berjalan **berlawanan arah** dengan perekam. Lorong yang hanya direkam satu
  arah memberi fitur berbeda total dari arah sebaliknya, dan MultiSet secara eksplisit mewajibkan
  lorong dipindai dua arah.
- Praktik benchmark yang mengurangi bias ini: Niantic menahan **pindaian terpisah** untuk validasi;
  LaMAR memisahkan sesi peta dan sesi kueri yang direkam pada waktu berbeda
  ([arXiv 2210.10770](https://arxiv.org/abs/2210.10770)).
- **Tetap berguna sebagai gerbang negatif**: kalau frame tertahan dari lintasan yang sama saja gagal,
  peta pasti buruk. Lulus tidak membuktikan baik.

### 2.3 Cek geometri tanpa ground truth (inferensi, alat dari fakta)

- **Gravitasi**: COLMAP `model_orientation_aligner` metode `IMAGE-ORIENTATION` mengestimasi sumbu
  gravitasi dari orientasi gambar (`EstimateGravityVectorFromImageOrientation`) lalu memutar model
  ([model.cc](https://github.com/colmap/colmap/blob/main/src/colmap/exe/model.cc), fungsi
  `RunModelOrientationAligner`). Metode `MANHATTAN-WORLD` butuh COLMAP dibangun dengan LSD. Fungsi
  estimasi ini **tidak terekspos** di pycolmap 4.2.0 (hanya `run_gravity_refinement`,
  `compute_rot90_from_gravity`), jadi untuk eutopos cukup ditulis ulang: rata-rata vektor "bawah"
  kamera, karena video direkam dengan ponsel tegak.
- **Pita tinggi kamera**: setelah sumbu gravitasi diketahui, pusat kamera ponsel yang dipegang orang
  berjalan seharusnya berada di pita tinggi sempit. Sebaran tinggi yang besar atau tren miring
  sepanjang lorong menandakan peta terlipat atau melengkung. Ini meniru `tiltCheck` MultiSet tanpa
  titik kontrol.
- **Konsistensi skala**: kalau dua jarak acuan diketahui di dua ujung lorong, rasio skala keduanya
  adalah ukuran langsung *scale drift* monokular.

---

## 3. Ground truth akurasi lokalisasi yang murah dan diterima akademik

### 3.1 Benchmark mapan (fakta)

| Benchmark | Cara membuat ground truth | Metrik dan ambang | Sumber |
|---|---|---|---|
| 7-Scenes | KinectFusion (ICP, frame-to-model) dari Kinect genggam 640×480 | Lazim median galat dan persen dalam 5 cm / 5° (⚠️ ambang ini tidak dicek di sumber primer pada riset ini) | [Microsoft Research 7-Scenes](https://www.microsoft.com/en-us/research/project/rgb-d-dataset-7-scenes/); Shotton dkk., CVPR 2013, [DOI 10.1109/CVPR.2013.377](https://doi.org/10.1109/CVPR.2013.377) |
| Cambridge Landmarks | *"generated using structure from motion techniques which we use as ground truth"* | Median galat posisi dan orientasi | Kendall, Grimes, Cipolla, ICCV 2015, [arXiv 1505.07427](https://arxiv.org/abs/1505.07427) |
| Aachen Day-Night | Siang: model COLMAP perantara, skala dari model Aachen yang sudah tergeoregistrasi. Malam (98 foto): **10 sampai 30 korespondensi 2D-3D dilabeli manual**, P3P + refinement; galat median rata-rata 36 cm dan 1° | 0,25 m / 2°, 0,5 m / 5°, 5 m / 10° (malam dilonggarkan 0,5 m / 2°, 1 m / 5°, 5 m / 10°) | Sattler dkk., CVPR 2018, [DOI 10.1109/CVPR.2018.00897](https://doi.org/10.1109/CVPR.2018.00897), [arXiv 1707.09092](https://arxiv.org/abs/1707.09092) |
| InLoc | Pemindai 3D Faro. Panorama paling mirip dipilih manual, pencocokan otomatis, P3P-RANSAC + BA; kueri sulit dianotasi manual 5 sampai 20 korespondensi; korespondensi > 20 px dibuang, pose dengan median reproyeksi < 5 px diperiksa visual; **329 dari 356** kueri diterima | Persen kueri dalam 0,25 / 0,5 / 1,0 m dengan batas sudut 10° | Taira dkk., CVPR 2018, [arXiv 1803.10368](https://arxiv.org/abs/1803.10368) |
| NAVER LABS indoor | LiDAR SLAM (pose graph, ICP, odometri roda) lalu disempurnakan SfM berbasis COLMAP; reproyeksi < 1,5 px; **tidak ada angka akurasi GT** | 0,1 m / 1°, 0,25 m / 2°, 1 m / 5° | Lee dkk., CVPR 2021, [DOI 10.1109/CVPR46437.2021.00324](https://doi.org/10.1109/CVPR46437.2021.00324), [arXiv 2105.08941](https://arxiv.org/abs/2105.08941) |
| LaMAR | Pemindai laser, sesi AR (ARKit, HoloLens) diselaraskan lalu BA + pose graph; pose dipertahankan bila benar dalam 10 cm pada kepercayaan 99,7%, 0,8% frame dibuang. Penulis: *"We do not claim that our GT is perfect"* | Recall 10 cm / 1° dan 1 m / 5° | Sarlin dkk., ECCV 2022, [arXiv 2210.10770](https://arxiv.org/abs/2210.10770) |
| Map-free (Niantic) | Pose ARKit/ARCore dari pindaian ponsel, didaftarkan dan di-BA dengan COLMAP, **diskalakan ulang ke pose ARKit/ARCore** dengan faktor rata-rata; disebut *pseudo ground truth* | Galat translasi dan rotasi, VCRE (5% dan 10% diagonal gambar), kurva presisi pada 25 cm / 5° | Arnold dkk., ECCV 2022, [DOI 10.1007/978-3-031-19769-7_40](https://doi.org/10.1007/978-3-031-19769-7_40), [arXiv 2210.05494](https://arxiv.org/abs/2210.05494) |

**Peringatan metodologis (fakta)**: Brachmann, Humenberger, Rother, Sattler. *On the Limits of Pseudo
Ground Truth in Visual Camera Re-localisation.* ICCV 2021,
[DOI 10.1109/ICCV48922.2021.00616](https://doi.org/10.1109/ICCV48922.2021.00616),
[arXiv 2109.00524](https://arxiv.org/abs/2109.00524). Benchmark mengukur *"how well each method
replicates the results of the reference algorithm"*, dan hasil evaluasi berubah dengan pilihan
algoritma acuan.

### 3.2 Pilihan murah untuk eutopos

| Metode | Fakta yang ada | Inferensi untuk eutopos |
|---|---|---|
| Hitung ubin lantai | Tidak ditemukan di sumber primer sebagai metode benchmark | Murah dan cepat, tetapi ukuran ubin dan nat harus diukur dulu di lokasi; galat menumpuk sebanding jumlah ubin. Cocok untuk Tingkat 1 |
| Meteran / laser distance meter | Tidak ada spesifikasi alat yang dicek di riset ini | Laser untuk jarak lurus panjang (garis pandang bebas), meteran untuk offset pendek. Akurasi alat ambil dari spesifikasi pabrik dan tulis di laporan |
| Marker ArUco/AprilTag | OpenCV: pose dari marker butuh kalibrasi kamera, dan *"translation vectors of the estimated poses will be in the same units"* dengan panjang sisi marker ([tutorial OpenCV](https://github.com/opencv/opencv/blob/4.x/doc/tutorials/objdetect/aruco_detection/aruco_detection.markdown)) | Satu marker tercetak memberi skala, tetapi galat skala dari satu marker kecil (sisi 15 sampai 20 cm) jauh lebih besar daripada dari jarak 10 m. Lebih cocok sebagai **titik acuan** yang terdeteksi otomatis di video daripada sebagai sumber skala |
| Denah CAD / as-built | Tidak dicek | Bagus untuk kerangka gedung, tetapi as-built sering berbeda dari gambar rencana; perlu verifikasi beberapa ukuran |
| Roda ukur | Tidak dicek | Sejenis meteran untuk lorong panjang |
| Total station | Dipakai sebagai GT pemindaian indoor di makalah ISPRS 2023 (⚠️ hanya dari cuplikan pencarian, belum dibaca) | Akurasi tinggi tetapi butuh alat dan operator jurusan sipil/geomatika |
| Motion capture | Tidak dicek | Hanya ruangan kecil, tidak cocok untuk lorong |
| Laser scanner | InLoc (Faro), LaMAR | Standar emas benchmark, di luar anggaran PA |

**Yang diterima di paper (inferensi dari 3.1)**: semua benchmark melaporkan median galat dan recall
pada ambang; ground truth boleh pseudo selama metode dan ketidakpastiannya dijelaskan (LaMAR, Map-free,
Brachmann 2021). Titik lantai yang diukur meteran dengan skema leave-one-out (`eval_meter.py`) adalah GT
yang **lebih independen** dari pipeline daripada GT berbasis SfM, karena tidak dihasilkan oleh algoritma
yang sama yang dievaluasi.

---

## 4. Menetapkan skala metrik dari video monokular

### 4.1 Pilihan (fakta dan inferensi dipisah)

| Pilihan | Fakta | Inferensi: cocok untuk "developer cukup rekam video"? |
|---|---|---|
| **Satu jarak acuan** | MultiSet memakai tepat ini untuk peta tanpa sensor | **Ya, paling cocok sekarang.** Satu kali ukur, bisa digabung dengan gravitasi dari orientasi gambar |
| **Marker berukuran diketahui** | OpenCV: translasi dalam satuan sisi marker | Ya, otomatis terdeteksi, tetapi harus memasang marker sebelum merekam dan butuh intrinsik kamera |
| **Pose VIO ARCore/ARKit direkam** | ARCore: *"Translation units are meters"*. Map-free menskalakan SfM ke pose ARKit/ARCore. Immersal mengunggah pose AR per gambar. COLMAP `pose_prior_mapper` = *"incremental mapper with prior position constraints"*, deviasi bawaan 1,0 m per sumbu ([FAQ](https://colmap.github.io/faq.html)). `pycolmap.PosePrior` 4.2.0 punya `position`, `position_covariance`, `gravity` | **Terbaik jangka panjang**, nol ukur, dan sekaligus memberi gravitasi. Butuh aplikasi capture sendiri: ARCore Recording API hanya merekam citra **640×480** untuk pelacakan plus IMU, dan halaman itu tidak menyebut pose ([Recording and Playback](https://developers.google.com/ar/develop/recording-and-playback)). ⚠️ Besar drift VIO ARCore di lorong panjang tidak ditemukan di sumber primer |
| **IMU saja** | Tidak ditemukan sumber primer untuk skala SfM dari IMU ponsel tanpa VIO | Tidak disarankan: integrasi ganda akselerometer melantur cepat. Kalau IMU dipakai, pakai lewat VIO (baris di atas) |
| **Ukuran objek standar** (pintu, ubin) | Contoh pintu 2 m di dokumentasi MultiSet | Bisa sebagai cadangan, tetapi tinggi pintu bervariasi antar-gedung; selisih 5 cm pada 2 m = 2,5% skala. Ukur sekali satu pintu nyata lebih baik daripada menganggap ukuran standar |
| **Kedalaman monokular** | Map-free: kedalaman prediksi (DPT, PlaneRCNN) dipakai menskalakan pose relatif, presisi *"acceptable"* hanya pada sebagian kasus | Tidak untuk peta; terlalu kasar |

### 4.2 Berapa titik atau jarak minimal (inferensi, matematika sederhana)

- **Galat skala relatif = galat ukur ÷ panjang acuan.** Jarak 10 m dengan galat ukur 2 cm memberi 0,2%
  skala, yaitu 6 cm pada titik 30 m dari asal. Jarak 1 m dengan galat 2 cm memberi 2%, yaitu 60 cm pada
  30 m. Maka **acuan harus panjang**, minimal 10 m, idealnya hampir sepanjang area.
- **SfM monokular bisa melantur skalanya sepanjang lintasan.** Satu jarak hanya memperbaiki skala
  rata-rata di ruas itu. Dua jarak di dua ujung lorong memberi skala sekaligus **ukuran drift**; kalau
  kedua faktor berbeda lebih dari beberapa persen, peta perlu direkam ulang atau dibangun dengan pose
  prior.
- **Rotasi dan translasi tidak butuh titik ukur untuk satu area.** Gravitasi dari orientasi gambar
  (§2.3) memberi sumbu z; arah utara dan titik asal boleh sembarang selama `navgraph.json` digambar di
  kerangka yang sama (`server/navgraph.py` mewajibkan `"frame": "building"`, meter, z ke atas).
  Titik acuan baru wajib saat **beberapa area** harus berbagi satu kerangka gedung
  (`docs/multi-map-localization-research.md` §2.8).
- **Sim3 penuh dari titik**: COLMAP butuh minimal 3 gambar ([FAQ](https://colmap.github.io/faq.html));
  eutopos mewajibkan ≥ 4 karena leave-one-out menyisakan 3. `eval_meter.py` sudah memperingatkan bila
  titik nyaris segaris (`point_spread < 0.05`). Lorong lurus hampir pasti memicu peringatan ini, jadi
  titik harus zig-zag kiri-kanan lorong.

---

## 5. Rekomendasi untuk eutopos

### 5.1 Best practice lebih dulu

**Tujuan akhir**: aplikasi capture merekam video plus pose ARCore, peta dibangun dengan pose prior
(skala dan gravitasi dari ARCore), gerbang otomatis menilai peta, dan video kedua dari arah berlawanan
dipakai sebagai set validasi. Developer tidak mengukur apa pun. Meteran hanya untuk laporan PA. Ini
pola Immersal, Niantic, dan Map-free.

**Kompromi untuk sekarang** (video tanpa pose): gravitasi dari orientasi gambar ditambah satu atau dua
jarak acuan panjang. Ini **meredakan**, bukan menyembuhkan: drift skala di dalam peta tetap tidak
terdeteksi kalau hanya satu jarak.

### 5.2 Tabel tingkat verifikasi

| Tingkat | Siapa dan kapan | Masukan manusia | Metrik dan ambang awal (inferensi, setel dengan data sendiri) | Keluaran |
|---|---|---|---|---|
| **0. Gerbang otomatis** | Server, setiap job selesai | Tidak ada | (1) Model utama berisi ≥ 90% frame terekstrak dan **tidak ada potongan lain ≥ 10 frame**. (2) Tidak ada celah frame tak terdaftar > 4 frame (2 s pada 2 fps). (3) Galat reproyeksi rata-rata ≤ 1,5 px (angka NAVER). (4) Track length rata-rata ≥ 3 (anjuran Immersal). (5) Frame tertahan tiap ke-10: ≥ 90% lolos `MIN_INLIERS` 50. (6) Setelah sumbu gravitasi diestimasi: sebaran tinggi pusat kamera kecil relatif terhadap panjang lintasan (ambang ditetapkan setelah melihat 3 sampai 5 peta baik) | Status lulus / peringatan / gagal, plus **rentang frame dan detik video yang putus** (job 22: frame 157-158 ≈ detik 78, 227-228 ≈ detik 113). Gagal = jangan terbitkan, rekam ulang ruas itu |
| **1. Cek opsional cepat** | Developer, sekali per peta, ±10 menit | Tandai 2 jarak acuan (masing-masing ≥ 10 m, di dua ujung) dan 1 sampai 3 titik cek | Skala dari jarak 1, divalidasi dengan jarak 2: selisih faktor skala ≤ 3% (lebih dari itu = drift). Titik cek: galat ≤ 1 m (toleransi pembimbing 3 sampai 4 m terpenuhi dengan longgar) | `align.json` provisional dengan `method` dan selisih skala tercatat |
| **2. Ukur penuh untuk laporan PA** | Penulis PA, sekali untuk bab hasil | ≥ 8 titik zig-zag (tidak segaris), foto 4 arah per titik (akhiran `_xp/_yp/_xn/_yn`), 2 titik holdout | Sudah ada di `eval_meter.py`: median, p90, RMSE, % ≤ 1 m dan ≤ 2 m, salah yakin > 3 m, arah hadap. **Tambahkan** recall pada 0,25 / 0,5 / 1 / 5 m agar sebanding InLoc dan Aachen, serta ketidakpastian alat ukur | Tabel hasil PA. Kueri sebaiknya dari **sesi terpisah** (hari atau arah berbeda), bukan frame video peta |

### 5.3 Yang paling cepat membuat demo navigasi tampil berjalan

1. **Keputusan pemilik dibutuhkan (menyentuh kode yang ada).** Saat ini `validate_align` di
   `server/alignment.py` menolak `reference_points < 4`, dan `Localizer.to_building` di
   `server/localizer.py` mengembalikan `None` tanpa `align.json`. Usulan: tambah kolom `method`
   (`"survey"` | `"known_distance"` | `"pose_prior"`) dan wajibkan `reference_points >= 4` **hanya**
   untuk `survey`; untuk `known_distance` wajibkan panjang acuan dan sumbu gravitasi tercatat. Respons
   `/localize` sebaiknya ikut membawa `method` supaya klien dan laporan tahu pose itu provisional.
2. **Jangan mengakali validator** dengan mengisi `reference_points: 4` dari titik karangan. Itu
   memalsukan bukti akurasi, persis yang akan dibaca penguji.
3. Urutan kerja tercepat: gerbang Tingkat 0 (sebagian besar sudah ada di `spike/inspect_map.py`,
   tinggal metrik dari §2.1 dan keputusan lulus/gagal) → gravitasi dari orientasi gambar → satu jarak
   acuan → `align.json` provisional → navgraph digambar di kerangka yang sama → demo jalan.
4. Rekam ulang ruas job 22 di sekitar frame 157 (tikungan menghadap dinding polos) sesuai aturan
   MultiSet: lebih pelan, tetap ada tekstur di bingkai, dan lorong direkam dua arah.

### 5.4 Kompromi dan risikonya

| Pilihan | Keuntungan | Risiko |
|---|---|---|
| Satu jarak acuan | Satu kali ukur, cepat | Drift skala tidak terdeteksi; galat membesar di ujung jauh |
| Dua jarak acuan | Mendeteksi drift | Dua kali ukur, perlu tanda yang terlihat di video |
| Gravitasi dari orientasi gambar | Nol ukur | Mengandalkan ponsel dipegang tegak; ponsel miring konsisten menggeser sumbu z |
| Pose ARCore + `pose_prior_mapper` | Nol ukur, skala dan gravitasi sekaligus | Butuh aplikasi capture baru; resolusi rekaman ARCore 640×480; ⚠️ belum diuji dengan pycolmap 4.2.0 |
| Held-out dari video sama | Otomatis, tanpa rekaman tambahan | Bias optimistis; hanya sah sebagai gerbang negatif |
| Video kedua arah berlawanan | Validasi jujur, mendeteksi lorong satu arah | Rekaman dan waktu proses dua kali |

---

## 6. Yang belum terverifikasi

1. ⚠️ Arti `preservePoses` di API Immersal dan sumber skala Immersal; hanya disimpulkan dari isi
   `SDKImageRequest`. Dokumentasi REST Immersal tidak ditemukan (halaman Mapper 404, sitemap 404).
2. ⚠️ Skor kualitas scan Niantic 0 sampai 1 dan aturan scan minimal 15 detik: hanya dari cuplikan
   mesin pencari; halaman ARDK asli 404 dan Wayback tidak bisa diakses alat.
3. ⚠️ Mapxus, Oriient, Navisens: tidak ditemukan dokumentasi primer tentang kualitas peta atau GT.
4. ⚠️ Ambang 7-Scenes 5 cm / 5° tidak dicek ke sumber primer dalam riset ini.
5. ⚠️ Isi Schönberger dkk. CVPR 2017 (daftar metrik rekonstruksi) tidak terbaca (CVF 403); hanya
   metadata Crossref.
6. ⚠️ Total station sebagai GT (ISPRS 2023) hanya dari cuplikan pencarian.
7. ⚠️ Besar drift VIO ARCore dan scale drift SfM monokular di lorong panjang: tidak ditemukan angka di
   sumber primer. Ukur sendiri dengan dua jarak acuan.
8. ⚠️ Semua ambang Tingkat 0 dan 1 di §5.2 adalah inferensi titik awal, bukan angka dari sumber. Setel
   dengan beberapa peta baik dan buruk, dan **jangan setel memakai set uji PA** (prinsip eval set burns on
   reuse).
9. ⚠️ `pose_prior_mapper` / `pycolmap.PosePrior` dengan pose ARCore belum diuji di eutopos.
10. ⚠️ Versi pycolmap: terpasang 4.2.0, brief menyebut 4.2.1. Opsi bawaan di §2.1 dibaca dari 4.2.0.

---

## 7. Daftar sumber

### Paper (metadata dicek ke Crossref)

- Schönberger, Hardmeier, Sattler, Pollefeys. *Comparative Evaluation of Hand-Crafted and Learned Local
  Features.* CVPR 2017. https://doi.org/10.1109/CVPR.2017.736 (⚠️ hanya metadata)
- Brachmann, Humenberger, Rother, Sattler. *On the Limits of Pseudo Ground Truth in Visual Camera
  Re-localisation.* ICCV 2021. https://doi.org/10.1109/ICCV48922.2021.00616 · https://arxiv.org/abs/2109.00524
- Sattler dkk. *Benchmarking 6DOF Outdoor Visual Localization in Changing Conditions.* CVPR 2018.
  https://doi.org/10.1109/CVPR.2018.00897 · https://arxiv.org/abs/1707.09092
- Taira dkk. *InLoc: Indoor Visual Localization with Dense Matching and View Synthesis.* CVPR 2018.
  https://doi.org/10.1109/CVPR.2018.00752 · https://arxiv.org/abs/1803.10368
- Lee dkk. *Large-scale Localization Datasets in Crowded Indoor Spaces.* CVPR 2021.
  https://doi.org/10.1109/CVPR46437.2021.00324 · https://arxiv.org/abs/2105.08941
- Sarlin dkk. *LaMAR: Benchmarking Localization and Mapping for Augmented Reality.* ECCV 2022.
  https://doi.org/10.1007/978-3-031-20071-7_40 · https://arxiv.org/abs/2210.10770
- Arnold dkk. *Map-free Visual Relocalization: Metric Pose Relative to a Single Image.* ECCV 2022.
  https://doi.org/10.1007/978-3-031-19769-7_40 · https://arxiv.org/abs/2210.05494
- Shotton dkk. *Scene Coordinate Regression Forests for Camera Relocalization in RGB-D Images.* CVPR
  2013. https://doi.org/10.1109/CVPR.2013.377
- Kendall, Grimes, Cipolla. *PoseNet: A Convolutional Network for Real-Time 6-DOF Camera
  Relocalization.* ICCV 2015. https://doi.org/10.1109/ICCV.2015.336 · https://arxiv.org/abs/1505.07427

### Kode (dibaca langsung)

- eutopos: `spike/eval_meter.py`, `spike/inspect_map.py`, `server/alignment.py`,
  `server/localizer.py`, `server/navgraph.py`
- hloc `third_party/Hierarchical-Localization/hloc/reconstruction.py` (pemilihan model terbesar)
- pycolmap 4.2.0 terpasang di `.venv` (opsi bawaan mapper, metode `Reconstruction`, `PosePrior`)
- COLMAP `src/colmap/exe/model.cc`, `RunModelOrientationAligner`:
  https://github.com/colmap/colmap/blob/main/src/colmap/exe/model.cc
- Immersal Unity SDK, commit `fba192e`: `Runtime/Scripts/REST/REST.cs`, `RESTJobsAsync.cs` ·
  https://github.com/immersal/imdk-unity (tanpa berkas lisensi, hanya dibaca)
- OpenCV ArUco tutorial: https://github.com/opencv/opencv/blob/4.x/doc/tutorials/objdetect/aruco_detection/aruco_detection.markdown

### Dokumentasi vendor dan alat

- COLMAP: https://colmap.github.io/cli.html · https://colmap.github.io/faq.html
- MultiSet: https://docs.multiset.ai/fundamentals/rest-api-docs/map-scale ·
  https://docs.multiset.ai/fundamentals/rest-api-docs/georeference.md ·
  https://docs.multiset.ai/fundamentals/maps/mapping-instruction.md ·
  https://docs.multiset.ai/fundamentals/localization/simulation.md · https://docs.multiset.ai/llms.txt
- MultiSet, **klaim pemasaran**: https://multiset.ai/post/visual-positioning-from-3d-gis-data
- Immersal: https://developers.immersal.com/docs/mapsmapping/howtomap/
- Niantic Spatial: https://www.nianticspatial.com/docs/scaniverse/techniques
- Google ARCore: https://developers.google.com/ar/reference/java/com/google/ar/core/Session.FeatureMapQuality ·
  https://developers.google.com/ar/develop/java/cloud-anchors/developer-guide ·
  https://developers.google.com/ar/reference/java/com/google/ar/core/GeospatialPose ·
  https://developers.google.com/ar/reference/java/com/google/ar/core/Pose ·
  https://developers.google.com/ar/develop/recording-and-playback
- Apple ARKit: https://developer.apple.com/documentation/arkit/arframe/worldmappingstatus-swift.enum/mapped ·
  https://developer.apple.com/documentation/arkit/argeotrackingconfiguration
- Microsoft Research 7-Scenes: https://www.microsoft.com/en-us/research/project/rgb-d-dataset-7-scenes/
- Pihak ketiga / pemasaran: https://www.mappedin.com/resources/blog/indoor-orientation-with-oriient-and-mappedin/ ·
  https://medium.com/dent-reality/dent-reality-building-the-future-of-indoor-ar-navigation-9dd6431b31d6
