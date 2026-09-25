# Catatan Desain: Koordinat, Penyelarasan, Rute, dan Evaluasi

Pengetahuan desain yang dibutuhkan saat membangun eutopos dan menyambungkannya ke aplikasi Unity.
Sebagian besar berasal dari riset awal PA (September 2026). Klaim yang belum diuji ditandai ⚠️.

## 1. Dua lapis posisi

1. **Lapis relatif (di antara koreksi).** ARCore melacak gerak perangkat. Akurat untuk jarak pendek,
   tapi **drift menumpuk**, dan kerangka koordinatnya tidak berhubungan dengan gedung.
2. **Lapis absolut (saat koreksi).** eutopos mengembalikan pose kamera dalam koordinat gedung.
   Hubungan antara kerangka ARCore dan kerangka gedung dihitung ulang, dan drift yang terkumpul
   dibuang.

Rumus penyelarasan, dengan `T_a←b` berarti pose kerangka b dinyatakan di kerangka a:

```text
T_sesi←gedung = T_sesi←kamera(ARCore, saat foto diambil) × inverse(T_gedung←kamera(hasil eutopos))
```

**Catatan penting:**
- **Foto dan pose ARCore harus dari frame yang sama.** Simpan pose ARCore saat foto dikirim. Jangan
  memakai pose saat jawaban server datang, karena pengguna sudah bergerak.
- **Tempelkan hasilnya ke `ARAnchor`**, jangan disimpan sebagai angka mentah. Koordinat dunia ARCore
  bisa berubah saat ARCore memperbarui modelnya.
- **Geser konten, bukan XR Origin.** Satu objek induk `BuildingRoot` membawa NavMesh dan semua POI.
  Menggeser origin di tengah sesi mengubah kerangka yang dipakai komponen AR lain.
- **Pertimbangkan 4 derajat kebebasan** (geser X, Y, Z dan putar yaw) kalau sumbu Y sesi ARCore
  terbukti searah gravitasi. ⚠️ Belum terverifikasi untuk sesi biasa, harus dicek dengan log.
- **Tolak koreksi yang meragukan.** Pakai jumlah inlier yang dikembalikan eutopos.
- **Koreksi terlihat sebagai lompatan.** Tampilan boleh dihaluskan, tapi posisi untuk evaluasi harus
  mentah.

**Galat sudut lebih berbahaya daripada galat posisi** (perhitungan): galat yaw θ menghasilkan galat
samping sekitar `d × tan θ` pada jarak d. 1° ≈ 0,17 m pada 10 m, dan 3° ≈ 1,05 m pada 20 m.

## 2. Sistem koordinat gedung

- **Satu kerangka per gedung**, satuan meter, tangan kiri seperti Unity (X kanan, Y atas, Z depan).
- **Titik asal** di titik fisik yang mudah ditemukan ulang, misalnya sudut pintu utama lantai dasar.
- **Sumbu Z sejajar dinding terpanjang**, bukan utara magnetik. Kompas tidak andal di dalam gedung.
- **Setiap lantai punya elevasi Y** dari gambar potongan gedung atau diukur di tangga.
- **Peta SfM tidak punya skala meter.** Skala dan sumbu didapat dari titik acuan terukur lewat
  `pycolmap.estimate_sim3d_robust`. Galat survei titik acuan adalah **batas bawah** akurasi sistem.

## 3. Model data (satu pemilik, PostgreSQL di server instansi)

| Tabel | Kolom inti | Catatan |
|---|---|---|
| `building` | `id`, `nama`, `versi_peta` | `versi_peta` naik setiap peta atau geometri berubah. Klien membandingkan untuk memuat ulang |
| `floor` | `id`, `building_id`, `kode`, `elevasi_y` | |
| `control_point` | `id`, `floor_id`, `x`, `y`, `z`, `akurasi_survei_m` | Titik acuan untuk penyelarasan peta. Akurasi survei wajib diisi |
| `poi` | `id` (GUID stabil), `floor_id`, `x`, `y`, `z`, nama, kategori, alias, deskripsi | Dikelola anchoring tool |
| `nav_geometry` | model lantai atau NavMesh per `versi_peta` | |

**Prinsip:** setiap data punya satu pemilik. Posisi POI **tidak disalin** ke scene Unity. Scene hanya
menyimpan geometri lantai, sedangkan POI dimuat saat runtime sebagai anak `BuildingRoot`.

## 4. Rute

| Pilihan | Kelebihan | Kekurangan |
|---|---|---|
| **Unity AI Navigation (NavMesh)** | Sudah dipakai, rute mengikuti bentuk ruang | Menambah gedung butuh Unity untuk bake ulang. ⚠️ Bake saat runtime belum diverifikasi |
| **Graf waypoint + A\* sendiri** | Pengelola bisa menambah titik tanpa Unity. Rute bisa dihitung di server | Rute patah-patah, simpul harus dirawat |

**Kompromi untuk D3 (penilaian):** NavMesh di dalam lantai, graf kecil antar-lantai (tangga dan lift
sebagai simpul). **Jebakan migrasi:** kalau kode Unity diturunkan dari proyek yang memakai VPS
komersial, paket AI Navigation bisa ikut tertarik sebagai dependensinya. Deklarasikan langsung di
`manifest.json` sebelum SDK itu dicabut.

**Transisi lantai:** lantai aktif ditentukan dari koreksi terakhir, lalu diperbarui dari perubahan Y
di tangga. ⚠️ Pelacakan ARCore di dalam lift yang bergerak belum terverifikasi.

## 5. Evaluasi akurasi dan drift

**Istilah:**
- **ATE (Absolute Trajectory Error):** selisih lintasan sebenarnya dan lintasan estimasi, untuk
  konsistensi global.
- **RPE (Relative Pose Error):** galat gerak relatif antar-waktu, untuk mengukur drift.

Tanpa motion capture, yang realistis adalah galat di titik uji yang diketahui (ATE diskret) dan drift
antar-koreksi (RPE).

| Metrik | Cara ambil |
|---|---|
| **M1. Galat absolut di titik uji** | Titik uji di lantai dengan koordinat terukur, terpisah dari titik acuan penyelarasan. Laporkan ME, RMSE, median, persentil 95 galat horizontal, dan galat arah |
| **M2. Galat terhadap jarak sejak koreksi terakhir** | Kelompokkan titik uji per jarak tempuh (misalnya 0, 10, 20, 40 m). Dasar menentukan interval koreksi |
| **M3. Drift antar-koreksi** | `drift_k = e_k / L_k`: selisih prediksi dan koreksi dibagi panjang lintasan sejak koreksi sebelumnya (m per m) |
| **M4. Galat penutupan loop** | Jalan satu putaran yang kembali ke titik awal, koreksi di tengah dimatikan. Ulangi dengan koreksi aktif |
| **M5. Koreksi loop pasca-proses** | Sebar galat M4 secara linear terhadap jarak tempuh. **Bukan** optimasi pose graph penuh. Sebutkan batas ini di laporan |
| **M6. Beban perangkat** | CPU dan memori ponsel dengan dan tanpa koreksi VPS |
| **M7. Latensi layanan** | Per tahap, kondisi hangat, median dan persentil 95 (lihat `docs/spike-plan.md`) |

**Protokol:**
- **Minimal 3 ulangan per titik uji.** Catat ponsel, pencahayaan, jam, dan keramaian.
- **Laporkan anggaran galat terpisah:** survei titik acuan, survei titik uji, galat pose VPS, dan
  drift VIO. Tanpa pemisahan ini, angka akhir tidak bisa ditafsirkan.
- **Jangan membakar set uji.** Titik untuk menyetel parameter (resolusi, k, interval koreksi) harus
  berbeda dengan titik untuk melaporkan akurasi. Set uji yang dipakai untuk menambal kegagalan tidak
  lagi sah sebagai ukuran.
- **Input yang bisa diulang:** ARCore Recording & Playback memungkinkan beberapa strategi koreksi
  dibandingkan pada rekaman yang sama. ⚠️ Ketersediaannya di Unity belum dicek.
- **Pembanding:** ARCore tanpa koreksi pada lintasan yang sama. VPS komersial hanya kalau disetujui
  pembimbing, dan hanya sebagai pembanding pengujian.

## 6. Kontrak API layanan (usulan)

```text
POST /localize
  masukan : 1 foto (JPEG) + intrinsik kamera (fx, fy, cx, cy) + opsional: lantai
  keluaran: posisi (x, y, z) dan rotasi dalam koordinat GEDUNG,
            jumlah inlier, status (ok / gagal), waktu proses per tahap

GET /health
  status layanan dan versi peta yang termuat
```

- **Intrinsik dikirim klien.** ARCore menyediakan intrinsik kamera per frame.
- **Model dimuat sekali saat server menyala**, supaya setiap permintaan memakai model yang hangat.
- **Jumlah inlier dikembalikan**, supaya klien bisa menolak koreksi yang meragukan.
