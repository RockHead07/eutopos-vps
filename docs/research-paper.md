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

## Yang belum diketahui

1. Latensi hloc (dan varian XFeat) di server tanpa GPU. **Harus diukur sendiri lewat spike.**
2. Lisensi bobot MegaLoc dan NetVLAD.
3. Akurasi meter MobileARLoc.
4. Apakah pengaturan hloc berjalan mulus di Windows, atau perlu WSL2 atau Linux.
