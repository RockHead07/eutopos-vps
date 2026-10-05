# Rujukan Penelitian

Daftar semua paper, kode, dan dokumentasi yang dipakai untuk merancang eutopos-vps.

**Cara verifikasi.** Metadata paper dicek ke API arXiv atau Crossref. Lisensi kode dibaca dari
berkas LICENSE di repositori resmi. Klaim angka hanya dimuat kalau terbaca di sumber primer.
Tanda ⚠️ berarti belum terverifikasi. Tanggal pengecekan: September 2026.

**PDF paper** disimpan lokal di `docs/papers/` (di-gitignore, tidak ikut ke repo publik).

## Ringkasan keputusan

| Keluarga metode | Keputusan | Alasan utama |
|---|---|---|
| **Berbasis peta SfM (hloc)** | ✅ **Jalur utama** | Satu-satunya dengan bukti akurasi indoor dan lisensi bersih |
| Regresi pose + VIO | Cadangan | Tanpa server, tapi akurasi APR rawan tertinggal |
| Regresi koordinat scene (ACE, GLACE) | ❌ | Lisensi non-komersial |
| Pose relatif (Reloc3r, Map-free) | ❌ | Lisensi non-komersial |
| Lokalisasi denah (F³Loc) | ❌ untuk sekarang | Bukti nyata hanya kualitatif, repo tanpa lisensi |
| Mesh (MeshLoc) | ❌ | Butuh GPU dan mesh padat |
| Papan nama + OCR (INSUS) | Cadangan | Hanya bekerja di dekat papan |
| Sensor saja (magnet + barometer) | Pelengkap | Deteksi lantai, tidak menggantikan VPS |

---

## 1. Inti pipeline (dipakai)

### hloc: From Coarse to Fine
- **Sarlin, Cadena, Siegwart, Dymczyk.** *From Coarse to Fine: Robust Hierarchical Localization at
  Large Scale.* CVPR 2019. (Crossref)
- Kode: [cvg/Hierarchical-Localization](https://github.com/cvg/Hierarchical-Localization), **Apache-2.0**.
- **Peran:** kerangka lokalisasi. Retrieval global, lalu pencocokan fitur lokal ke titik 3D, lalu PnP.
- Modul yang dipakai: `reconstruction`, `pairs_from_retrieval`, `match_features`, `localize_sfm`,
  `triangulation`. Konfigurasi bawaan `aliked+lightglue` dan `disk+lightglue` ada di
  `match_features.py`. Butuh `pycolmap >= 3.13`.

### COLMAP: Structure-from-Motion Revisited
- **Schönberger, Frahm.** *Structure-from-Motion Revisited.* CVPR 2016. (Crossref)
- Kode: [colmap/colmap](https://github.com/colmap/colmap), **BSD**.
- **Peran:** membangun peta 3D dari foto.
- Panduan capture resmi: [COLMAP tutorial](https://colmap.github.io/tutorial.html). Intinya:
  tekstur cukup, tumpang tindih tinggi (tiap objek di ≥ 3 foto), berpindah posisi bukan hanya
  memutar kamera, pencahayaan serupa, satu kamera dengan zoom sama.
- Foto 360: [python/examples/panorama_sfm.py](https://github.com/colmap/colmap/blob/main/python/examples/panorama_sfm.py),
  memecah panorama menjadi tampilan perspektif yang tumpang tindih.
- Penyelarasan skala: `pycolmap.estimate_sim3d_robust`
  ([dokumentasi pycolmap](https://colmap.github.io/pycolmap/pycolmap.html)).

### LightGlue
- **Lindenberger, Sarlin, Pollefeys.** *LightGlue: Local Feature Matching at Light Speed.* ICCV 2023.
  (Crossref)
- Kode: [cvg/LightGlue](https://github.com/cvg/LightGlue), **Apache-2.0**.
- **Peran:** pencocok fitur lokal.
- README menyebut 20 FPS pada 512 keypoint di CPU **Intel i7-10700K**, CPU yang sama dengan PC lab,
  jadi bisa direproduksi sebagai titik acuan.
- Hasil InLoc dengan SuperPoint+LightGlue: 49,0 / 68,2 / 79,3% (DUC1) dalam 0,25 / 0,5 / 1 m
  ([supplementary ICCV 2023](https://openaccess.thecvf.com/content/ICCV2023/supplemental/Lindenberger_LightGlue_Local_Feature_ICCV_2023_supplemental.pdf)).
  Kombinasi DISK/ALIKED di InLoc tidak ada di sumber tersebut.

### ALIKED (ekstraktor utama)
- **Zhao dkk.** *ALIKED: A Lighter Keypoint and Descriptor Extraction Network via Deformable
  Transformation.* IEEE Transactions on Instrumentation & Measurement, 2023.
  [arXiv 2304.03608](https://arxiv.org/abs/2304.03608)
- **Peran:** fitur lokal pengganti SuperPoint (yang lisensinya non-komersial).

### SIFT (pembanding klasik, bawaan COLMAP)
- **Lowe.** *Distinctive Image Features from Scale-Invariant Keypoints.* International Journal of
  Computer Vision 60(2), 91-110, 2004. [DOI 10.1023/B:VISI.0000029664.99615.94](https://doi.org/10.1023/B:VISI.0000029664.99615.94) (Crossref).
- **Arandjelović, Zisserman.** *Three things everyone should know to improve object retrieval* (RootSIFT).
  CVPR 2012, 2911-2918. [DOI 10.1109/CVPR.2012.6248018](https://doi.org/10.1109/CVPR.2012.6248018) (Crossref).
- **Peran:** pembanding. Di data lantai 10, hasil ditentukan matcher-nya, bukan feature-nya: SIFT dan ALIKED
  sama-sama 401/402 frame dan 36/46 foto uji dengan LightGlue, dan sama-sama gagal (0/46) dengan nearest neighbor +
  ratio test (`docs/sift-vs-aliked.md`, `docs/spike-plan.md`).

### DISK (ekstraktor pembanding)
- **Tyszkiewicz dkk.** *DISK: Learning local features with policy gradient.* NeurIPS 2020.
  [arXiv 2006.13566](https://arxiv.org/abs/2006.13566)

### MegaLoc (retrieval utama)
- **Berton dkk.** *MegaLoc: One Retrieval to Place Them All.* Tech report, 2025.
  [arXiv 2502.17237](https://arxiv.org/abs/2502.17237)
- Kode: [gmberton/MegaLoc](https://github.com/gmberton/MegaLoc), **MIT**. Dipanggil hloc lewat
  `torch.hub`. ⚠️ Lisensi bobot model belum dicek.

### NetVLAD (retrieval pembanding)
- **Arandjelović dkk.** *NetVLAD: CNN architecture for weakly supervised place recognition.* CVPR
  2016. [arXiv 1511.07247](https://arxiv.org/abs/1511.07247)
- hloc mengunduh bobot dari server ETH. ⚠️ Lisensi bobot belum dicek.

### XFeat (opsional, kalau CPU terlalu lambat)
- **Potje dkk.** *XFeat: Accelerated Features for Lightweight Image Matching.* CVPR 2024.
  [arXiv 2404.19174](https://arxiv.org/abs/2404.19174)
- Kode: [verlab/accelerated_features](https://github.com/verlab/accelerated_features), **Apache-2.0**.
- Klaim abstrak: real-time di CPU laptop, hingga 5x lebih cepat dari fitur deep lain. README:
  real-time sparse di CPU untuk citra VGA. **Tidak ada konfigurasi bawaan di hloc.**

## 2. Pola arsitektur: VIO + koreksi absolut

### VIO-APR
- **Liu, Zhao, Braud.** *Robust Localization with Visual-Inertial Odometry Constraints for
  Markerless Mobile AR.* [arXiv 2308.05394](https://arxiv.org/abs/2308.05394)
- **Peran:** dasar publikasi untuk pola "VIO melacak, lokalisasi absolut mengoreksi drift".
- Median posisi membaik hingga 36%, orientasi 29%. Enam scene, VIO dari ARKit.

### MobileARLoc
- **Liu dkk.** *MobileARLoc: On-device Robust Absolute Localisation for Pervasive Markerless Mobile
  AR.* PerCom workshop. [arXiv 2401.11511](https://arxiv.org/abs/2401.11511)
- Inferensi 80 ms di perangkat, error separuh dari APR dasarnya. ⚠️ Angka meter tidak ada di abstrak.
- **Peran:** rujukan pola arsitektur dan **jalur cadangan tanpa server**.

### KS-APR
- **Liu dkk.** *KS-APR: Keyframe Selection for Robust Absolute Pose Regression.*
  [arXiv 2308.05459](https://arxiv.org/abs/2308.05459)

## 3. Dievaluasi dan ditolak

| Paper | Alasan ditolak |
|---|---|
| **Brachmann dkk., ACE**, CVPR 2023, [arXiv 2305.14059](https://arxiv.org/abs/2305.14059) | Lisensi **non-komersial** (lisensi ACE Niantic) |
| **Wang dkk., GLACE**, CVPR 2024, [arXiv 2406.04340](https://arxiv.org/abs/2406.04340) | Lisensi **non-komersial** (lisensi ACE) |
| **Dong dkk., Reloc3r**, CVPR 2025, [arXiv 2412.08376](https://arxiv.org/abs/2412.08376) | Lisensi **CC BY-NC-SA 4.0** |
| **Arnold dkk., Map-free Relocalization**, ECCV 2022 | Lisensi **non-komersial**. Benchmark tempat kecil, bukan gedung |
| **Chen dkk., F³Loc**, CVPR 2024, [arXiv 2403.03370](https://arxiv.org/abs/2403.03370) | Angka unggulan dari simulasi (iGibson). Uji nyata (LaMAR HGE) hanya kualitatif dan dilatih di lokasi itu. Demo pakai GPU RTX 3070 Ti. **Repo tanpa berkas lisensi** |
| **Panek dkk., MeshLoc**, ECCV 2022, [arXiv 2207.10762](https://arxiv.org/abs/2207.10762) | Butuh mesh padat, CUDA, `faiss-gpu`. Diuji di 12 Scenes (ruangan) dan Aachen (kota). Kode BSD-3, tapi pencocoknya memakai SuperGlue |

**Arti "non-komersial"** (dibaca dari teks lisensi ACE): boleh untuk *"teaching and research at
educational institutions"*. Dikecualikan: pengembangan produk komersial, riset yang dibiayai pihak
komersial, penggunaan untuk atau atas nama entitas komersial. Hak pakai tidak dapat
disublisensikan. Ini pembacaan teks, bukan nasihat hukum.

### Peringatan tentang regresi pose
- **Sattler dkk.** *Understanding the Limitations of CNN-based Absolute Camera Pose Regression.* CVPR
  2019. [arXiv 1903.07504](https://arxiv.org/abs/1903.07504)
- APR *"do not consistently outperform a handcrafted image retrieval baseline"*. Dasar untuk tidak
  menjadikan APR jalur utama.
- **Zhou dkk.** *Is Geometry Enough for Matching in Visual Localization?* ECCV 2022.
  [arXiv 2203.12979](https://arxiv.org/abs/2203.12979)

## 4. Benchmark dan evaluasi

### InLoc
- **Taira dkk.** *InLoc: Indoor Visual Localization with Dense Matching and View Synthesis.* CVPR
  2018. [arXiv 1803.10368](https://arxiv.org/abs/1803.10368)
- **Peran:** benchmark indoor. Dasar target ≤ 1 m pada ≥ 70%.

### LaMAR
- **Sarlin dkk.** *LaMAR: Benchmarking Localization and Mapping for Augmented Reality.* ECCV 2022.
  [arXiv 2210.10770](https://arxiv.org/abs/2210.10770), kode
  [microsoft/lamar-benchmark](https://github.com/microsoft/lamar-benchmark) (CC-BY-4.0).
- **Peran:** acuan cara capture dan ground truth. Peta rujukan dari **NavVis M6 trolley atau VLX
  backpack** (laser scanner + kamera panorama, SLAM proprietary), lalu rekaman iPhone, iPad, dan
  HoloLens 2 didaftarkan ke peta itu. Wajah dan plat nomor dianonimkan.

## 5. Garis riset pendahulu (INSUS)

Ditulis oleh pembimbing PA. Eutopos adalah kelanjutan arah ini.

| Paper | Isi | Keterbatasan yang dijawab eutopos |
|---|---|---|
| **Fajrianti dkk.**, *INSUS: Indoor Navigation System Using Unity and Smartphone for User Ambulation Assistance*, Information 14(7) 359, 2023. [DOI 10.3390/info14070359](https://doi.org/10.3390/info14070359) | Posisi awal dari QR code, pelacakan Visual SLAM, Unity | Pengguna harus menemukan dan memindai QR |
| **Fajrianti dkk.**, *A User Location Reset Method through Object Recognition in INSUS*, Network 4(3) 295-312, 2024. [DOI 10.3390/network4030014](https://doi.org/10.3390/network4030014) | Reset posisi dari papan nama: YOLOv8 + PaddleOCR + Levenshtein. mAP@0,5 0,995, CER < 10% | Hanya bekerja saat papan terlihat. Akurasi dilaporkan untuk deteksi dan OCR, bukan galat posisi meter |
| **Brata dkk.**, *An Enhancement of Outdoor Location-Based AR Anchor Precision through VSLAM and Google Street View*, Sensors 24(4) 1161, 2024 | Anchor AR luar ruangan | Bergantung layanan Google |

## 6. Sensor saja (pelengkap)

### Kim & Shin 2025
- **Kim, Shin.** *Deep Learning-Based Multi-Floor Indoor Localization Using Smartphone IMU Sensors
  With 3D Location Initialization.* IEEE Access 13, 101532-101544, 2025.
  [DOI 10.1109/ACCESS.2025.3578354](https://doi.org/10.1109/ACCESS.2025.3578354), CC BY 4.0.
- **Isi:** magnetometer untuk lantai awal (LSTM) dan posisi 2D awal (k-NN pada peta magnet),
  barometer untuk perpindahan lantai (Seq2Seq), PDR untuk pelacakan, titik kalibrasi di dekat tangga
  dan lift.
- **Pengumpulan data:** satu Galaxy Note 10+, aplikasi Android buatan sendiri, dicatat per langkah,
  130 langkah per lantai.
- **Hasil:** RMSE 0,64 m, 93,42% dalam 1 m. Deteksi lantai 92,06% dan 93,7%.
- **Batasan:** satu jalur sekitar 600 m, satu ponsel, ground truth tidak dijelaskan.
- **Peran untuk eutopos:** deteksi lantai lewat barometer bisa **mempersempit kandidat retrieval**.
  ⚠️ Hipotesis, belum diuji.

## 7. Karya terkait sisi lain platform PA

- **Lewis dkk.** *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* NeurIPS 2020.
  [arXiv 2005.11401](https://arxiv.org/abs/2005.11401)
- **Yang dkk.** *An Embodied AR Navigation Agent: Integrating BIM with Retrieval-Augmented Generation
  for Language Guidance.* IEEE ISMAR 2025. [arXiv 2508.16602](https://arxiv.org/abs/2508.16602).
  RAG multi-agen + BIM + navigasi AR, SUS 80,5. Paling mirip judul PA, sehingga kebaruan PA lebih
  kuat di sisi **lokalisasi lokal**, yaitu repo ini.
- **Liu dkk.** *AR Indoor Wayfinding in Hospital Environments.* [arXiv 2601.00001](https://arxiv.org/abs/2601.00001).
  32 peserta, NASA-TLX, AR lawan peta kertas. Acuan desain evaluasi. ⚠️ Pracetak.

## 8. Perangkat dan format data

- **GoPro MAX:** 6K video, 18 MP foto
  ([GoPro](https://gopro.com/en/us/news/max-tech-specs-stitching-resolution)). Video berformat
  `.360` proyeksi EAC, perlu dikonversi
  ([Trek View](https://www.trekview.org/blog/using-ffmpeg-process-gopro-max-360/)).
- **Resolusi 360 per arah** kira-kira setara 1080p untuk frame 5,7K
  ([SkyeBrowse](https://www.skyebrowse.com/news/posts/phone-vs-360-camera-indoor)). ⚠️ Sumber sekunder.

## 9. Kandidat cadangan dan pengetahuan pendukung (riset awal, September 2026)

Riset pertama membandingkan kandidat berbasis penanda, radio, dan SLAM sebelum arah "tanpa QR, konsep
VPS" ditetapkan. Semuanya **bukan jalur utama**, tapi tetap berguna kalau spike gagal.

### 9.1 Penanda fisik (bertentangan dengan klaim "tanpa penanda", hanya cadangan)

| Kandidat | Isi | Lisensi dan status |
|---|---|---|
| Image tracking ARCore (`ARTrackedImageManager`) | Paling mudah di Unity. Penanda gambar unik per titik, library runtime bisa ditambah tanpa build ulang | Gratis. **Akurasi pose tidak dipublikasikan.** Deteksi awal butuh penanda mengisi sekitar 25% frame |
| AprilTag (`jp.keijiro.apriltag`) | Akurasi pose terdokumentasi di lab: 0,62 mm, ~0,1° pada 0,5 sampai 1,5 m (preprint FMAC) | BSD-2. ⚠️ Kompatibilitas Unity 6.3 belum dicek |
| ArUco (OpenCV) | Std 5,4 / 3,8 / 14,7 mm di lab (FMAC) | Apache-2.0, tapi gratis di Unity hanya kalau membangun plugin sendiri |
| QR code + VIO (gaya INSUS) | ZXing.Net | Apache-2.0. Galat meter tidak ditemukan di sumber |

### 9.2 Sinyal radio (ditolak untuk AR)

| Kandidat | Fakta dari sumber | Kenapa ditolak |
|---|---|---|
| WiFi RSSI fingerprint | Android membatasi aplikasi foreground **4 pemindaian per 2 menit** ([Android Wi-Fi scanning](https://developer.android.com/develop/connectivity/wifi/wifi-scan)). RADAR: median 2 sampai 3 m ([Bahl & Padmanabhan, INFOCOM 2000](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/infocom2000.pdf)) | Terlalu jarang dan terlalu kasar untuk panah AR. Mungkin berguna untuk menebak lantai |
| WiFi RTT (802.11mc/az) | *"typically accurate within 1-2 meters"*, butuh AP yang mendukung FTM ([Android Wi-Fi RTT](https://developer.android.com/develop/connectivity/wifi/wifi-rtt)) | ⚠️ Dukungan AP gedung PENS belum dicek |
| BLE beacon | ~2,6 m pada 95%, 19 beacon di ~600 m² ([Faragher & Harle, IEEE JSAC 2015](https://doi.org/10.1109/JSAC.2015.2430281)) | Harus membeli dan memasang beacon |
| UWB | Ranging 10 cm, tapi kedua perangkat harus punya UWB ([Android UWB](https://developer.android.com/develop/connectivity/uwb)) | Ponsel khusus dan anchor berbayar |
| Anyplace, FIND3 | Platform berbasis radio, MIT | Tidak dirawat sejak 2022 dan 2020 |

### 9.3 SLAM di perangkat dan PDR (ditolak)

- **stella_vslam** ([repo](https://github.com/stella-cv/stella_vslam)): BSD-2, aktif, peta bisa disimpan
  dan dimuat. Tanpa dukungan Android resmi, harus dikompilasi silang dan berjalan berdampingan dengan
  ARCore. Terlalu berat untuk D3.
- **ORB-SLAM3** ([arXiv 2007.11898](https://arxiv.org/abs/2007.11898)): GPL-3.0, commit terakhir 2022.
  3,6 cm di EuRoC dengan stereo-inertial, bukan kamera monokular ponsel.
- **PDR + map matching** ([Harle, IEEE COMST 15(3), 2013](https://www.cl.cam.ac.uk/~rkh23/site/publication/pub35/)):
  tidak perlu dibangun terpisah karena ARCore sudah memadukan kamera dan IMU. Cadangan saat kamera
  kehilangan pelacakan.

### 9.4 Fakta pendukung desain

- **Drift VIO.** Di area industri 1.600 m², ARKit, ARCore, dan HoloLens *"accumulate an average error
  of about 17m per 120m"*, dengan ARCore galat terbesar
  ([Feigl dkk., VISIGRAPP 2020](https://www.scitepress.org/Papers/2020/89899/pdf/index.html)). Versi
  ARCore lama dan lingkungan pabrik, jadi bukan prediksi untuk koridor PENS, tapi alasan kuat koreksi
  berkala dibutuhkan.
- **Koordinat dunia ARCore tidak tetap.** *"every frame should be considered to be in a completely
  unique world coordinate space"* ([ARCore Pose](https://developers.google.com/ar/reference/java/com/google/ar/core/Pose)).
  Hasil penyelarasan harus ditempelkan ke `ARAnchor`, bukan disimpan sebagai angka mentah.
- **ARCore dasar** memakai SLAM dan feature points
  ([ARCore Fundamentals](https://developers.google.com/ar/develop/fundamentals)).
- **ARCore Recording & Playback** menyimpan video kamera dan IMU ke MP4 yang bisa diputar ulang
  ([dokumentasi](https://developers.google.com/ar/develop/recording-and-playback)). Berguna untuk
  membandingkan strategi koreksi pada input identik. ⚠️ Ketersediaan di ARCore XR Plugin 6.3 belum dicek.
- **Metrik ATE dan RPE** ([TUM RGB-D benchmark tools](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/tools)).
  Dipakai di `docs/design-notes.md`.
- **Unity AI Navigation** ([manual](https://docs.unity3d.com/Packages/com.unity.ai.navigation@2.0/manual/index.html)):
  Unity Companion License. Satu scene boleh memuat beberapa NavMesh surface. Tangga dan lift
  dihubungkan dengan NavMesh Link.
- **ProBuilder** ([manual](https://docs.unity3d.com/Packages/com.unity.probuilder@6.0/manual/index.html)):
  untuk memodelkan dinding dan lantai dari denah.

## 10. Rujukan latar belakang Proposal PA (Bab 1), set 2021-2026

Revisi 2026-10-04: set pertama diganti atas permintaan pemilik (sebagian terlalu lama, sebagian kurang
dekat dengan proyek). Semua rujukan di bawah terbit **2021 atau setelahnya**, kecuali Lewis 2020 yang
dipertahankan karena judul PA mengacu padanya. Metadata (penulis, tahun, venue, halaman, DOI)
dicocokkan ke Crossref. Isi klaim dicocokkan ke **abstrak** dari penerbit atau OpenAlex; teks lengkap
belum dibaca, jadi klaim hanya sekuat abstraknya.

**Rantai argumen Bab 1** dan rujukan tiap mata rantainya:

| Mata rantai | Rujukan | Yang dikatakan abstraknya (batasnya) |
|---|---|---|
| Mencari jalan di gedung kompleks bertingkat itu menantang, terutama bagi yang belum mengenalnya | [1] Vater dkk. 2025 | "Navigation in complex multi-level buildings ... can be a challenging wayfinding task, especially if the individual is unfamiliar with the building." Studi VR, 68 peserta, gedung belanja (bukan kampus) |
| Pengunjung gedung publik membutuhkan bantuan navigasi, dan aplikasi ponsel dianggap solusi, tetapi penerimaannya bergantung usia | [2] Ženka dkk. 2021 | Survei 928 pasien dan pengunjung rumah sakit di Ostrava: permintaan perbaikan navigasi (termasuk aplikasi ponsel) naik dengan tingkat pendidikan; kelompok di atas 60 tahun kurang berminat memakai aplikasi. Rumah sakit di Ceko, bukan kampus |
| Di Indonesia baru sedikit gedung yang punya navigasi indoor | [3] Santi dkk. 2023 | Penulis menyatakan "only a small number of buildings in Indonesia implement indoor navigation systems"; sistemnya AR tanpa penanda dengan QR code di titik tertentu, diuji di satu gedung kampus di Bogor. Itu klaim penulis di jurnal nasional, bukan survei |
| GPS tidak menjangkau dalam ruangan, sehingga butuh sistem posisi dalam ruangan (IPS) | [4] Farahsari dkk. 2022 | "most IoT scenarios are in indoor spaces and GPS cannot fully cover them, applying an indoor positioning system (IPS) is necessary"; survei metode dan teknologi IPS |
| Navigasi AR berbasis ponsel (ARCore, Unity) sudah dibangun untuk kampus dan gedung | [5] Lu dkk. 2021; [7] Rubio-Sandoval dkk. 2021 | Lu: sistem navigasi kampus berbasis ARCore dan Unity3D, uji dalam dan luar ruangan di kampus, dibandingkan dengan peta digital. Rubio-Sandoval: metodologi navigasi indoor AR + *semantic web*; mencatat belum ada standardisasi cara membangun sistem semacam ini; diuji di dua gedung akademik |
| Akurasi navigasi AR berbasis sensor ponsel terukur dan masih punya kendala | [6] Hořejší dkk. 2024 | ARCore, AR Foundation, dan ZXing di gudang: 83% mencapai target, akurasi rata-rata 0,48 m, dan kegagalan atau ketidakstabilan akibat pencahayaan. Lingkungan gudang, bukan gedung kampus |
| Pelacakan visual-inersia (VIO) akan melenceng seiring waktu, jadi perlu koreksi berkala | [8] Kim dkk. 2022 | Membandingkan ARKit, ARCore, RealSense T265, dan ZED 2: ARKit paling stabil dengan galat *drift* sekitar 0,02 m per detik. **Angka ARCore sendiri tidak ada di abstrak**, jangan dikutip |
| Evaluasi lokalisasi untuk AR butuh benchmark yang realistis dan *ground truth* yang akurat | [9] Sarlin dkk. 2022 (LaMAR) | Benchmark lama berskala kecil, keragaman rendah, direkam dari kamera diam, dan akurasi *ground truth*-nya umumnya tidak cukup untuk kebutuhan AR |
| Feature matching adalah inti lokalisasi visual dan rekonstruksi 3D | [10] Huang dkk. 2024 | Survei deteksi, deskripsi, dan pencocokan fitur beserta penerapannya pada lokalisasi visual dan SLAM, dibandingkan lewat eksperimen. Dasar untuk Bab 2 (ALIKED, LightGlue) |
| Lokalisasi visual berbasis cloud menimbulkan masalah privasi | [11] Geppert dkk. 2021; [12] Kim dkk. 2025 | Geppert: "privacy concerns arising from cloud-based solutions in mixed reality and robotics". Kim: pada lokalisasi klien-server, pengiriman data visual ke penyedia layanan punya tantangan privasi; studi pengguna menunjukkan rasa tidak aman. Keduanya mengusulkan solusi teknis lain (garis fitur, kamera peristiwa), bukan lokalisasi di server lokal seperti eutopos |
| RAG menjawab keterbatasan LLM (pengetahuan usang, jawaban meyakinkan tapi salah) | [13] Huang dan Huang 2026; [14] Zhao dkk. 2026; [15] Lewis dkk. 2020 | Huang: RAG menggabungkan *retrieval* dengan LLM untuk menekan jawaban yang tampak masuk akal tapi bisa salah. Zhao: survei RAG yang juga membahas keterbatasan sistem RAG saat ini, jadi RAG mengurangi masalah tanpa menghapusnya. Lewis: makalah RAG asli |
| Celah: asisten navigasi AR berbahasa alami dengan RAG sudah ada, tetapi lokalisasinya bukan lokal tanpa penanda | [16] Yang dkk. 2025; [17] [18] Fajrianti dkk. 2023, 2024 | Yang: sistem AR yang menggabungkan BIM dengan RAG multi-agen dan agen AR berwujud (suara, gerak); SUS 80,5. INSUS (pembimbing): navigasi indoor dengan Unity dan ponsel; posisi awal dari QR code, dan versi 2024 mereset posisi lewat pengenalan papan nama |

**Tingkat verifikasi (jujur):**
- Semua metadata cocok di Crossref. Penulis pertama [4] di Crossref adalah **Farahsari** (OpenAlex menulis Farahsary): pakai Crossref.
- Isi: semua dari abstrak. [9] dari abstrak arXiv, [15] dan [17] [18] dari catatan sesi sebelumnya (bagian 5 dan 7).
- **Kelemahan konteks:** [1] pusat belanja, [2] rumah sakit, [6] gudang, [5] kampus di Shanghai. Tidak satu pun gedung kampus teknik di Indonesia, jadi Bab 1 harus menulisnya sebagai bukti pendukung, bukan bukti langsung.
- **Belum dibaca penuh.** Sebelum mengutip angka atau kalimat spesifik, baca teksnya.

**Daftar lengkap (gaya IEEE, nomor sesuai tabel; ubah nomor menurut urutan kemunculan di naskah):**

[1] C. Vater, P. Mavros, J. Zhao, C. Abati, and C. Hölscher, "Don't get lost in the mall! Characteristics of efficient wayfinding and gaze behavior," *J. Environ. Psychol.*, vol. 108, Art. no. 102831, 2025, doi: 10.1016/j.jenvp.2025.102831.

[2] J. Ženka, J. Macháček, P. Michna, and P. Kořízek, "Navigational needs and preferences of hospital patients and visitors: What prospects for smart technologies?," *Int. J. Environ. Res. Public Health*, vol. 18, no. 3, Art. no. 974, 2021, doi: 10.3390/ijerph18030974.

[3] A. N. Santi, S. Hidayat, and S. Agustian, "Pembuatan model navigasi berbasis augmented reality dengan metode markerless di gedung RISE Center," *INFOTECH J.*, vol. 9, no. 2, pp. 637-643, 2023, doi: 10.31949/infotech.v9i2.7464.

[4] P. S. Farahsari, A. Farahzadi, J. Rezazadeh, and A. Bagheri, "A survey on indoor positioning systems for IoT-based applications," *IEEE Internet Things J.*, vol. 9, no. 10, pp. 7680-7699, 2022, doi: 10.1109/JIOT.2022.3149048.

[5] F. Lu, H. Zhou, L. Guo, J. Chen, and L. Pei, "An ARCore-based augmented reality campus navigation system," *Appl. Sci.*, vol. 11, no. 16, Art. no. 7515, 2021, doi: 10.3390/app11167515.

[6] P. Hořejší, T. Macháč, and M. Šimon, "Reliability and accuracy of indoor warehouse navigation using augmented reality," *IEEE Access*, vol. 12, pp. 94506-94519, 2024, doi: 10.1109/ACCESS.2024.3420732.

[7] J. I. Rubio-Sandoval, J. L. Martinez-Rodriguez, I. Lopez-Arevalo, A. B. Rios-Alvarado, A. J. Rodriguez-Rodriguez, and D. T. Vargas-Requena, "An indoor navigation methodology for mobile devices by integrating augmented reality and semantic web," *Sensors*, vol. 21, no. 16, Art. no. 5435, 2021, doi: 10.3390/s21165435.

[8] P. Kim, J. Kim, M. Song, Y. Lee, M. Jung, and H.-G. Kim, "A benchmark comparison of four off-the-shelf proprietary visual-inertial odometry systems," *Sensors*, vol. 22, no. 24, Art. no. 9873, 2022, doi: 10.3390/s22249873.

[9] P.-E. Sarlin *et al.*, "LaMAR: Benchmarking localization and mapping for augmented reality," in *Proc. Eur. Conf. Comput. Vis. (ECCV)*, 2022, pp. 686-704, doi: 10.1007/978-3-031-20071-7_40.

[10] Q. Huang, X. Guo, Y. Wang, H. Sun, and L. Yang, "A survey of feature matching methods," *IET Image Process.*, vol. 18, no. 6, pp. 1385-1410, 2024, doi: 10.1049/ipr2.13032.

[11] M. Geppert, V. Larsson, P. Speciale, J. L. Schönberger, and M. Pollefeys, "Privacy preserving localization and mapping from uncalibrated cameras," in *Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit. (CVPR)*, 2021, pp. 1809-1819, doi: 10.1109/CVPR46437.2021.00185.

[12] J. Kim *et al.*, "Privacy-preserving visual localization with event cameras," *IEEE Trans. Image Process.*, vol. 34, pp. 6215-6230, 2025, doi: 10.1109/TIP.2025.3607640.

[13] Y. Huang and J. X. Huang, "A survey on retrieval-augmented text generation for large language models," *ACM Comput. Surv.*, vol. 58, no. 12, pp. 1-38, 2026, doi: 10.1145/3805774.

[14] P. Zhao *et al.*, "Retrieval-augmented generation for AI-generated content: A survey," *Data Sci. Eng.*, vol. 11, no. 1, pp. 1-29, 2026, doi: 10.1007/s41019-025-00335-5.

[15] P. Lewis *et al.*, "Retrieval-augmented generation for knowledge-intensive NLP tasks," in *Proc. Adv. Neural Inf. Process. Syst. (NeurIPS)*, 2020, arXiv:2005.11401.

[16] H.-K. Yang, T.-C. Hsiao, R. Oka, R. Nishino, S. Tofukuji, and N. Kobori, "An embodied AR navigation agent: Integrating BIM with retrieval-augmented generation for language guidance," in *Proc. IEEE Int. Symp. Mixed Augmented Reality (ISMAR)*, 2025, pp. 1461-1471, doi: 10.1109/ISMAR67309.2025.00150.

[17] E. D. Fajrianti *et al.*, "INSUS: Indoor navigation system using Unity and smartphone for user ambulation assistance," *Information*, vol. 14, no. 7, Art. no. 359, 2023, doi: 10.3390/info14070359.

[18] E. D. Fajrianti, Y. Y. F. Panduman, N. Funabiki, A. L. Haz, K. C. Brata, and S. Sukaridhoto, "A user location reset method through object recognition in indoor navigation system using Unity and a smartphone (INSUS)," *Network*, vol. 4, no. 3, pp. 295-312, 2024, doi: 10.3390/network4030014.

**Dicari tetapi tidak dimasukkan:** Lehman 2022 (risiko privasi aplikasi AR seluler: lebih tentang pengembang aplikasi daripada lokalisasi) dan Kim 2026 (agen virtual berperan dengan MLLM: baru, belum relevan untuk Bab 1). Keduanya bisa dipakai di Bab 2.

**Usia rujukan:** 17 dari 18 terbit 2021 atau setelahnya (Lewis 2020 dipertahankan).

## Yang belum diketahui

1. Latensi hloc (dan varian XFeat) di server tanpa GPU. **Harus diukur sendiri lewat spike.**
2. Lisensi bobot MegaLoc dan NetVLAD.
3. Akurasi meter MobileARLoc.
4. Apakah pengaturan hloc berjalan mulus di Windows, atau perlu WSL2 atau Linux.
