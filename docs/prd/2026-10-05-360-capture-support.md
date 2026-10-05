# PRD: Dukungan video 360 untuk membangun peta

Status: **draf, belum disetujui pemilik repo.** Disusun 2026-10-05. Belum ada kode. Semua angka target di
bagian 4 adalah **usulan** yang perlu dikonfirmasi.

Ditandai di seluruh dokumen: **[terverifikasi]** untuk hal yang dicek langsung ke sumber atau kode yang
terpasang, **[dugaan]** untuk penalaran yang belum diuji, **[belum dicek]** untuk hal yang masih terbuka.

## 1. Latar belakang

Peta eutopos dibangun dari video HP yang dipotong per frame, lalu diproses hloc (ALIKED + LightGlue) dan
rekonstruksi COLMAP (`docs/spike-plan.md`). Pada pembimbingan 4 Oktober 2026, Bu Evi meminta dua hal:
meminjam kamera 360 di lab Pak Dhoto, dan **membandingkan hasilnya dengan HP** ("kira2 hasilnya bagus yg
mana"), dengan alasan "kualitas gambarnya juga pengaruh".

Data kita menunjukkan dua limitasi yang berkaitan dengan sudut pandang kamera
(`docs/colmap-limitations.md`, bagian ini belum di-merge):

- **Limitasi #1, permukaan tanpa tekstur.** Peta putus saat kamera menghadap dinding putih polos dari dekat
  sekitar 5 detik.
- **Limitasi #4, cakupan sudut pandang.** Foto dari arah yang tidak terekam bisa gagal. Aturan rekam kita
  saat ini ("jangan membelakangi tembok", rute keliling) menutupinya dengan prosedur, bukan dengan alat.

Hasil terbaik kita (HP + LightGlue) sudah 401 dari 402 frame dalam satu peta dan 36 dari 46 foto uji. Sisa
masalahnya ada di 10 foto yang ditolak dan di titik putus tertentu, bukan di kinerja rata-rata.

## 2. Masalah yang ingin dijawab

1. Apakah video 360, dipotong menjadi tampilan perspektif, **bisa** masuk ke pipeline hloc kita tanpa
   merombaknya?
2. Apakah peta dari video 360 **lebih baik** daripada peta dari HP pada rute dan foto uji yang sama?

Pertanyaan 2 adalah hipotesis, bukan fakta. Dokumen ini merancang cara menjawabnya dengan adil, dan hanya
membangun integrasi permanen kalau jawabannya mendukung.

## 3. Tujuan dan bukan tujuan

**Tujuan**
- G1. Jalur dari video equirectangular ke peta yang bisa dipakai `/localize`, memakai pipeline yang sudah ada.
- G2. Perbandingan 360 vs HP yang adil dan bisa diulang, dengan metrik yang sama dengan uji sebelumnya.
- G3. Bila G2 mendukung: opsi `projection` pada video peta di API dan dashboard `/new/`.

**Bukan tujuan**
- Foto uji tetap dari HP. Lokalisasi dari foto 360 tidak termasuk.
- Tidak membuat camera model spherical sendiri atau memetakan langsung di ruang equirectangular.
- Tidak mengatur kamera dari aplikasi (live capture, SDK kamera).
- Tidak mengganti jalur HP. Video perspektif tetap jalur utama.

## 4. Hipotesis dan metrik keberhasilan

**H1 (cakupan).** Video 360 menurunkan jumlah titik putus yang diakibatkan arah pandang (limitasi #1 dan #4)
dibanding HP.
**H0 (pembanding).** Hambatan terbesar bukan kamera. Uji SIFT vs ALIKED menunjukkan peta pecah terutama
karena **matcher**, jadi hasil 360 bisa saja tidak berbeda dari HP.

Metrik, diambil dari `inspect.json` yang sudah dihasilkan pipeline:

| Metrik | HP (baseline lantai 10, 2 Okt) | Usulan kriteria "360 lebih baik" |
|---|---|---|
| Bagian peta | 1 | tetap 1 |
| Foto uji diterima (46 foto HP yang sama) | 36/46 | lebih dari 36, atau titik putus yang sebelumnya gagal terisi |
| Posisi rekam terdaftar | 401/402 frame | dihitung per **posisi rekam**, bukan per gambar |
| Waktu bangun peta | sekitar 6 menit | **batas atas** usulan 30 menit; bukan syarat kualitas |

Frame terdaftar **tidak** dibandingkan langsung: satu frame 360 menjadi beberapa view, jadi penyebutnya berbeda.
Keputusan lanjut atau berhenti ada di bagian 9.

## 5. Skenario pengguna

- **Perekam peta** (Bagus): membawa kamera 360 di tongkat, berjalan satu rute, mengekspor equirectangular
  `.mp4`, mengunggahnya sebagai video `peta` dengan projection `equirect`.
- **Peneliti** (untuk PA dan Bu Evi): menjalankan perbandingan yang sama pada rute yang sama, membaca tabel
  hasilnya di dashboard dan laporan.
- **Foto uji**: tetap HP, diambil seperti biasa (video `uji`).

## 6. Kebutuhan

### Fungsional
- FR-1. Skrip CLI `spike/pano_views.py`: membaca frame equirectangular, menulis **N view perspektif** per
  frame (jumlah dan FOV dapat diatur, bawaan 4 yaw × 3 pitch, FOV 90°, mengikuti
  `pycolmap.panorama.PANO_RENDER_OPTIONS`) **[terverifikasi di pycolmap 4.2.1]**.
- FR-2. Penamaan view stabil dan terurut: `<frame>_p<pitch>_y<yaw>.jpg`, dengan pengurutan yang menjaga
  tetangga waktu berdekatan (lihat bagian 7.2).
- FR-3. `extract_frames.py` tetap dipakai untuk memilih frame tertajam dari video equirectangular. Penilaian
  ketajaman dilakukan pada pita horizon, bukan seluruh panorama (kutub equirectangular meregang).
- FR-4. Kamera virtual dideklarasikan sebagai `SIMPLE_PINHOLE` dengan fokal diketahui (`f = lebar/(2·tan(FOV/2))`
  **[terverifikasi di `create_virtual_camera`]**), diteruskan ke impor hloc (`options` pada `import_images`).
- FR-5. `/api` menerima `projection` ("perspective" bawaan, "equirect") per video `peta`. Video `uji`
  hanya `perspective`.
- FR-6. Worker menjalankan langkah konversi hanya untuk video `equirect`, lalu memakai pipeline yang sama.
- FR-7. Dashboard `/new/` menampilkan pilihan Projection per video, dan halaman Job menampilkan projection
  yang dipakai.
- FR-8. Laporan hasil mencatat projection dan konfigurasi view (N, FOV, pitch) supaya perbandingan bisa
  direproduksi.

### Non-fungsional
- NFR-1. Tanpa dependensi baru di luar yang sudah ada. Pemotongan view memakai `opencv` dan `numpy`
  yang sudah terpasang, atau `pycolmap.panorama` **[ekstra `[panorama]` hanya butuh `opencv-python-headless`,
  `pillow`, `tqdm`, sudah ada di worker]**.
- NFR-2. Tidak ada migrasi database: `map_job.videos` adalah kolom JSON, jadi kunci `projection` cukup
  ditambahkan **[terverifikasi di `server/db.py`]**.
- NFR-3. Jalur HP tidak berubah perilakunya (uji regresi: seluruh tes di CI "Tests (Docker)" tetap hijau).
- NFR-4. Fungsi murni (pemetaan nama, perhitungan rotasi, perintah) bisa diuji tanpa GPU, mengikuti pola
  `server/pipeline.py`.

## 7. Rancangan

### 7.1 Dua jalur teknis

**Jalur A, view sebagai gambar biasa (dikerjakan dulu).** Setiap view dianggap gambar perspektif
independen. Pipeline tidak berubah, hanya jumlah gambar naik (4 sampai 12 kali). Tidak ada rig constraint.

**Jalur B, view sebagai rig (kondisional).** Mengikuti pendekatan COLMAP resmi: view dari satu panorama
dikelompokkan sebagai satu rig dengan rotasi relatif tetap, `ba_refine_sensor_from_rig=False`
[terverifikasi di `pycolmap.panorama.run_perspective`]. Skrip bawaan COLMAP memakai SIFT dan matcher COLMAP,
bukan hloc, jadi harus dirakit sendiri: render view, ekstraksi dan pencocokan lewat hloc, impor dengan
`CameraMode.PER_FOLDER`, `apply_rig_config`, lalu mapping dengan opsi rig. **[belum dicek]** apakah
`hloc.reconstruction.main` (parameter `mapper_options`) meneruskan opsi rig ke mapper.

Jalur B hanya dibangun kalau Jalur A menunjukkan potensi tetapi terhambat konsistensi geometri antar view.

### 7.2 Temuan desain: jendela pasangan berurutan

`run.py` menambah pasangan berurutan dengan jendela `SEQ = 10` (`server/pipeline.py`). Pada HP, jendela itu
mencakup 10 frame berurutan. Kalau satu frame 360 menjadi 12 view yang bersebelahan dalam urutan nama, jendela
10 **hampir tidak keluar dari frame yang sama**, sehingga pasangan antar waktu hilang dan hanya retrieval
(`--k-map 20`) yang tersisa. Konsekuensi untuk rancangan:

- **Urutkan view per yaw-pitch dulu, baru per waktu** (semua frame untuk view 0, lalu view 1, dan seterusnya),
  atau
- **Skala `--seq` dengan jumlah view per frame** (mis. 12 × 5 = 60).

Pilihan mana yang lebih baik ditentukan di Fase 1 dengan mengukur pasangan yang terbentuk. Ini **[dugaan]**
sampai diukur.

### 7.3 Fase

| Fase | Isi | Keluaran | Bergantung pada |
|---|---|---|---|
| 0 | Pinjam kamera, rekam rute lantai 10 yang sama dengan HP, ekspor equirect `.mp4` | Video mentah di luar git | Izin Pak Dhoto |
| 1 | `spike/pano_views.py` + jalankan `run.py` pada view, bandingkan dengan HP (Jalur A) | Tabel 360 vs HP | Fase 0 |
| 2 | Integrasi `projection` di API, worker, dashboard (G3) | PR + tes | Gerbang 1 lulus |
| 3 | Jalur B dengan rig | Perbandingan A vs B | Gerbang 2 |

### 7.4 Protokol rekam (Fase 0)

- **Rute dan jam sama** dengan rekaman HP lantai 10 (`docs/field-test-runbook.md`), supaya pembanding adil.
- Kamera di tongkat, operator di belakang kamera atau di luar jangkauan stitching **[dugaan]**.
- Stabilisasi: video kita saat ini mensyaratkan stabilisasi elektronik **mati** karena merusak intrinsik
  (`spike/extract_frames.py`). Pada kamera 360, stabilisasi dan horizon lock biasanya hanya memutar bola
  **[belum dicek di model yang dipinjam]**. Modul `panorama` mengasumsikan panorama "approximately upright"
  **[terverifikasi di komentar `get_virtual_rotations`]**, jadi horizon lock tidak boleh dimatikan sembarangan.
  Catat pengaturan yang dipakai.
- Ekspor lewat GoPro Player (*Export As*, equirectangular) kalau kameranya GoPro [2]. Model belum dikonfirmasi.
- Foto uji tetap **46 foto HP yang sama**, bukan foto baru.

## 8. Rencana uji

Matriks Fase 1 (satu rute, satu hari, foto uji HP yang sama):

| Peta dibangun dari | View per frame | Pencocokan | Keluaran yang dicatat |
|---|---|---|---|
| HP (baseline) | tidak berlaku | ALIKED + LightGlue | sudah ada (36/46, 1 bagian) |
| 360 | 4 (horizontal saja) | ALIKED + LightGlue | bagian, diterima, titik putus, waktu |
| 360 | 12 (4 yaw × 3 pitch) | ALIKED + LightGlue | idem |

Aturan menjaga perbandingan tetap sah:
- Satu variabel berubah per baris. Uji SIFT vs ALIKED mengajarkan bahwa dua variabel yang berubah bersamaan
  menghasilkan kesimpulan keliru.
- Hasil dilaporkan bersama batasnya: satu lantai, satu rute, satu kamera.
- Hasil negatif dicatat sama jelasnya dengan hasil positif.

## 9. Gerbang keputusan

- **Gerbang 1 (setelah Fase 1).** Lanjut ke Fase 2 hanya jika 360 memenuhi kriteria bagian 4 **dan** waktu
  bangun peta masih dalam batas. Jika tidak, berhenti: dokumentasikan sebagai hasil perbandingan.
- **Gerbang 2 (setelah Fase 2).** Fase 3 hanya jika ada bukti bahwa kegagalan tersisa berasal dari
  inkonsistensi geometri antar view, bukan dari matcher atau fitur.

## 10. Risiko

| Risiko | Dampak | Penanganan |
|---|---|---|
| Resolusi per derajat lebih rendah (piksel tersebar ke seluruh bola) **[dugaan]** | Fitur halus di kejauhan hilang | Bandingkan 4 vs 12 view; catat resolusi ekspor |
| Artefak stitching di sambungan lensa | Fitur palsu | Hindari yaw tepat di sambungan; periksa visual |
| Operator terekam | Fitur bergerak | Tongkat panjang; potong area bawah |
| Jendela pasangan berurutan tidak cocok (bagian 7.2) | Peta pecah bukan karena kamera | Ukur pasangan; urutkan atau skala `--seq` |
| Jumlah gambar 4 sampai 12 kali lipat | Waktu dan memori rekonstruksi | Ukur skala (rencana di `docs/colmap-limitations.md` bagian 10) |
| Kamera dipinjam sementara | Data tidak bisa diulang | Rekam rute ganda dan cadangkan video mentah |
| Satu lantai, satu kamera | Hasil sulit digeneralisasi | Dilaporkan sebagai batas, bukan klaim umum |

## 11. Pertanyaan terbuka

1. Model kamera lab Pak Dhoto dan resolusi ekspornya? **[belum dicek]**
2. Apakah `hloc.reconstruction.main` meneruskan opsi rig (Jalur B)? **[belum dicek]**
3. Berapa view per frame yang optimal untuk lorong: 4 horizontal atau 12? Ditentukan di Fase 1.
4. Pilihan 7.2: urutkan view atau skala `--seq`? Ditentukan di Fase 1.
5. Perlukah kamera virtual memakai fokal tetap (tidak di-refine) di Jalur A? Usulan: ya, karena fokalnya
   diketahui dari geometri render.

## 12. Rujukan

[1] COLMAP Developers, "Rig support," *COLMAP documentation*. [Online]. Available: https://colmap.github.io/rigs.html (accessed Oct. 5, 2026).

[2] GoPro, "GoPro Player: Render 360 video," *GoPro Support*. [Online]. Available: https://community.gopro.com/s/article/GoPro-Player-Render-360-Video (accessed Oct. 5, 2026).

[3] FFmpeg Developers, "Filters documentation: v360," *FFmpeg*. [Online]. Available: https://ffmpeg.org/ffmpeg-filters.html#v360 (accessed Oct. 5, 2026).

[4] D. Jung, J. Choi, Y. Lee, and D. Manocha, "IM360: Large-scale indoor mapping with 360 cameras," arXiv, Feb. 2025. [Online]. Available: https://arxiv.org/abs/2502.12545 (accessed Oct. 5, 2026). Hanya abstrak yang dibaca, teks penuh belum.

Fakta tentang `pycolmap.panorama` (jumlah view, FOV, kamera virtual, opsi rig) berasal dari kode `pycolmap 4.2.1`
yang terpasang di worker PC lab, dibaca 2026-10-05, bukan dari makalah.
