# Spesifikasi: Aplikasi Capture dan Pipeline Peta

**Status:** rancangan, hasil brainstorming 2026-09-29. Pengembangan boleh dimulai sebelum ACC
(keputusan pemilik repo, 2026-09-29), dengan penghalang per pekerjaan di `CLAUDE.md` bagian Status:
bagian yang bergantung pada metode lokalisasi menunggu hasil spike (`docs/spike-plan.md`), dan
aplikasi capture menunggu keputusan terbuka nomor 1.

Rujukan: `docs/multi-map-localization-research.md` (pemilihan peta dan pengelolaan banyak peta),
`docs/design-notes.md` (koordinat, model data, kontrak API), `docs/pa-context.md` (arahan pembimbing).

## 1. Tujuan dan ukuran keberhasilan

**Tujuan:** peta VPS bisa dibuat dan diperbarui **terus-menerus oleh banyak orang**, tidak bergantung pada
pengembang. Pemeta utama: anggota lab dan dosen terdekat.

**Ukuran keberhasilan:** seorang anggota lab yang belum pernah memakai sistem ini bisa memetakan ulang
satu area sampai versi peta barunya terbit, **tanpa bantuan pengembang**.

**Di luar cakupan dokumen ini:** pelacakan posisi orang tanpa kamera (ide hackathon, bukan PA), dan
aplikasi navigasi selain bagian yang dipakai bersama.

## 2. Komponen

```text
[Aplikasi capture]            [Server eutopos]                               [Aplikasi navigasi]
pemeta, login          ──►    antrean (tabel PostgreSQL) ─► pekerja:           semua orang
foto kunci + pose ARCore      1. samarkan orang, buang data mentah
+ intrinsik, unggah           2. bangun peta area (SfM, GPU)
                              3. selaraskan ke kerangka gedung
                              4. cek kualitas otomatis
[Dashboard web]               5. menunggu persetujuan manusia ──► versi terbit
peninjau: setujui peta ─────► (tukar versi aktif, simpan versi lama)
anchoring: POI di denah                                                  │
                              Layanan /localize (CPU) ◄── foto + petunjuk ─┘
```

| Komponen | Pilihan | Alasan |
|---|---|---|
| Aplikasi navigasi dan capture | **Unity + AR Foundation + ARCore**, satu project, dua aplikasi (dua build) | Industri VPS memisahkan aplikasi pemetaan dari aplikasi pengguna (Immersal Mapper, MultiSet). Satu project supaya kode ARCore, transformasi koordinat, dan klien API dipakai bersama |
| Cara merekam | **Foto kunci otomatis** tiap bergeser ±0,3 sampai 0,5 m atau berputar ±10°, resolusi CPU tertinggi yang didukung, dengan pose dan intrinsik ARCore | EIS ARCore hanya memengaruhi tampilan, bukan gambar CPU. Rekaman API ARCore bawaan hanya 640x480. Tanpa video, privasi lebih baik dan unggahan lebih kecil |
| API | **FastAPI** | Sudah direncanakan di `docs/design-notes.md` |
| Antrean pekerjaan | **Tabel PostgreSQL + `SELECT ... FOR UPDATE SKIP LOCKED`**, satu pekerja | Beban sedikit tapi berat (beberapa kali seminggu, menit sampai jam). Pola antrean ini disebut di dokumentasi resmi PostgreSQL. Procrastinate (MIT) jadi opsi kalau perlu retry otomatis |
| Metadata | **PostgreSQL** | Satu sumber kebenaran. Setujui dan aktifkan versi dalam satu transaksi |
| Foto dan paket peta | **Folder di disk**, lewat antarmuka simpan, ambil, hapus | Satu host. Object storage baru berguna kalau host lebih dari satu. Jangan MinIO (diarsipkan April 2026). Alternatif: SeaweedFS (Apache-2.0), Garage (AGPL-3.0) |
| Dashboard | **Next.js *static export* + Leaflet (`CRS.Simple`)**, disajikan FastAPI | Dokumentasi React menyarankan framework. *Static export* tanpa server Node. Leaflet punya mode peta non-geografis untuk denah |
| Deployment | **Docker Compose** (PostgreSQL, API, pekerja) di **Docker Engine dalam WSL2 Ubuntu**, sementara di PC lab | Mirip server Linux, mudah dipindah. CUDA di WSL2 didukung Windows 10 21H2 ke atas |

## 3. Alur data

1. **Merekam.** Pemeta login di aplikasi capture, memilih area, lalu berjalan dengan jalur ular dua
   arah. Aplikasi mengambil foto kunci otomatis, menolak foto buram, dan menunjukkan area yang belum
   terekam.
2. **Mengunggah.** Satu sesi unggah per rekaman. Foto dikirim satu per satu dan bisa dilanjutkan kalau
   koneksi putus (ratusan foto lewat Wi-Fi kampus).
3. **Memproses (pekerja):** samarkan orang, bangun peta area dengan GPU, selaraskan ke kerangka gedung
   dengan titik acuan, jalankan pemeriksaan kualitas dan set uji tertahan, hasilkan paket peta kandidat.
4. **Menyetujui.** Peninjau melihat hasil pemeriksaan di dashboard, membandingkan dengan versi aktif,
   lalu menyetujui atau menolak.
5. **Menerbitkan.** Penunjuk versi aktif area ditukar dalam satu transaksi. Versi lama disimpan untuk
   rollback.
6. **Melokalisasi.** `/localize` mengembalikan pose di kerangka gedung beserta `area_id`, `map_version`,
   jumlah inlier, dan status.

## 4. Model peta

- **Peta per area**, masing-masing dengan versi sendiri, semuanya di **satu kerangka gedung**. Memperbarui
  satu area tidak menggeser area lain.
- **Paket peta per versi:** `sfm/`, fitur lokal, deskriptor global, `align.json` (Sim3 ke kerangka gedung).
- **Pembaruan = versi baru**, bukan menambal versi aktif.
- **Tumpang tindih 5 sampai 10 m antar-area**, dan selisih posisi foto di zona itu menjadi syarat
  persetujuan.
- **Model data** (`docs/design-notes.md` bagian 3) ditambah: `area` (`id`, `floor_id`, `versi_aktif`),
  `map_version` (`id`, `area_id`, status: kandidat, terbit, ditolak, pensiun; hasil pemeriksaan;
  penyetuju), `capture_session` (`id`, `area_id`, pemeta, waktu, jumlah foto), `job` (antrean). Kolom
  `versi_peta` di `building` pindah ke tingkat area.

## 5. Pemilihan peta saat lokalisasi

Mengikuti `docs/multi-map-localization-research.md` bagian 5: persempit dengan petunjuk (lantai, posisi
terakhir dari ARCore), retrieval dan voting per area, PnP di area teratas, lalu **gagal terbuka** ke semua
area. **Untuk PA (satu area) tidak dibangun**, cukup `area_id` dan `map_version` di respons.

**Jangan memakai `hloc.localize_sfm.main()`** di layanan: saat PnP gagal, fungsi itu menulis pose foto
peta teratas, bukan melaporkan gagal (hloc `c13273b`, baris 205 sampai 207).

## 6. Privasi dan keamanan

- **Orang disamarkan otomatis** di server sebelum siapa pun, termasuk peninjau, melihat foto. Data
  sebelum penyamaran dihapus. Foto kunci yang sudah disamarkan disimpan permanen untuk membangun ulang
  peta. Aturan merekam saat sepi tetap berlaku.
- **Akun dan peran:** pemeta (merekam), peninjau (menyetujui), admin. Unggahan dan dashboard wajib login.
  Aplikasi navigasi tanpa login.
- **PC lab (Windows 10, tanpa pembaruan keamanan, Wi-Fi):** hanya bisa diakses dari jaringan kampus.
  Akses dari luar lewat VPN atau tunnel berautentikasi, bukan membuka port. Cadangan rutin ke mesin lain.

## 7. Tahapan

| Tahap | Kapan | Isi |
|---|---|---|
| 0. Spike | Sekarang | Membuktikan VPS di lantai 10 dengan kamera bawaan ponsel + `extract_frames.py` |
| 1. PA | Mulai sekarang untuk bagian yang tidak bergantung hasil spike, sisanya setelah spike lolos | Layanan `/localize` satu area, aplikasi navigasi, anchoring tool. **Aplikasi capture: lihat keputusan terbuka nomor 1** |
| 2. Setelah PA | Kalau diteruskan | Aplikasi capture penuh, penyamaran otomatis, alur persetujuan, banyak area, pemilihan peta dengan petunjuk ARCore |
| 3. Skala gedung | Jangka panjang | Banyak lantai (barometer), filter Wi-Fi kalau terbukti perlu, pemetaan ulang dipicu laju gagal per area |

## 8. Hal yang harus dibuktikan sebelum implementasi

| # | Hal | Kenapa penting | Cara membuktikan |
|---|---|---|---|
| 1 | Resolusi CPU tertinggi ARCore di ponsel uji | Kalau hanya 640x480, peta memburuk. Jalur cadangan: aplikasi native Kotlin dengan Shared Camera API | Aplikasi Unity kecil yang mencetak daftar konfigurasi kamera |
| 2 | Drift skala pose ARCore sepanjang lorong | Menentukan seberapa banyak titik acuan masih dibutuhkan | Bandingkan jarak tempuh ARCore dengan meteran |
| 3 | **Orientasi pose dan intrinsik ARCore terhadap gambar CPU** | Gambar CPU berorientasi sensor, sedangkan pose yang dipakai untuk tampilan berorientasi layar. Ketidakcocokan menghasilkan pasangan pose dan foto yang salah, jenis kesalahan yang sama dengan rotasi EXIF di spike | Rekam foto kunci pada orientasi ponsel berbeda, cek dengan `bench_localize.py` |
| 4 | Cara memakai pose ARCore di SfM | `pairs_from_poses` hloc sudah bisa dipakai untuk memilih pasangan. `pycolmap.PosePrior` belum diuji dengan pose ARCore | Uji pada data gladi |
| 5 | Lisensi model penyamar orang | Harus bebas dari lisensi non-komersial, seperti SuperPoint dulu | Baca lisensi dari repo resmi |
| 6 | Lisensi Leaflet dan pembungkus React-nya | Syarat dependensi dashboard | Baca lisensi dari repo resmi |
| 7 | Dua build dari satu project Unity | Mekanisme build per aplikasi (scene dan ID berbeda) | Uji build di versi Unity yang dipakai |
| 8 | Next.js *static export* | Rute dinamis perlu `generateStaticParams` atau diganti parameter query. Fitur server Next.js tidak tersedia | Prototipe dashboard kecil |

## 9. Keputusan yang masih terbuka

1. **Apakah aplikasi capture masuk cakupan PA?** Pengajuan PA menjanjikan VPS, anchoring tool, AI avatar
   dengan RAG, dan aplikasi Android. Aplikasi capture dan pipeline pembaruan peta **tidak dijanjikan**, dan
   isu Proposal PA nomor 1 menyebut cakupan sudah terlalu besar untuk D3. Pilihan:
   - (a) PA memakai kamera bawaan + skrip (sudah jalan). Aplikasi capture setelah PA.
   - (b) PA membuat aplikasi capture versi minimal (rekam foto kunci dan unggah, tanpa penyamaran dan
     persetujuan).
   Rekomendasi: **(a)**, dengan dokumen ini sebagai rencana pengembangan lanjutan di laporan. Diputuskan
   bersama pembimbing.
2. Tempat halaman persetujuan: bagian dashboard anchoring tool (usulan) atau terpisah.
3. Server permanen setelah PC lab.
4. Cara login: akun lokal sederhana atau SSO kampus.
5. **Visibilitas repo `eutopos-mobile`** (publik atau privat). Bergantung pada izin tim untuk kode
   turunan DARSI (avatar, lip sync, TTS, klien RAG), karena kode itu milik proyek tim dan sedang dalam
   proses paten. Nama repo sudah diputuskan (bagian 10).

## 10. Struktur repo

**Prinsip:** repo dipisah menurut satuan yang di-deploy dan batas kepemilikan atau lisensi, bukan menurut
bahasa pemrograman. Repo `eutopos-mobile` dibuat saat pekerjaan aplikasi dimulai.

| Repo | Isi | Visibilitas |
|---|---|---|
| `eutopos-vps` (sudah ada) | Server (API, pekerja, pipeline peta), dashboard web, dokumen | Publik, AGPL-3.0 |
| `eutopos-mobile` (baru) | Satu project Unity dengan dua aplikasi: **eutopos Mapper** (capture) dan aplikasi navigasi PA | Keputusan terbuka nomor 5 |

Nama `eutopos-mobile` dipilih supaya hubungannya dengan `eutopos-vps` langsung terbaca. Nama alternatif
yang sempat diusulkan: `hodos` (Yunani: jalan). Nama repo tidak menyebut DARSI.

**Dashboard tetap di `eutopos-vps`** karena ia antarmuka admin server itu sendiri: di-deploy bersama
(hasil *static export* disajikan FastAPI), kontraknya berubah bersama API dalam satu PR, dan tidak berisi
kode turunan DARSI.

### 10.1 `eutopos-vps`

```text
eutopos-vps/
├── server/               ← layanan Python (dibangun dari kode spike/)
│   ├── api/              ← rute FastAPI: /localize, /health, sesi capture dan unggah, peta, POI, akun
│   ├── pipeline/         ← langkah pekerja: samarkan, bangun peta, selaraskan, cek kualitas, terbitkan
│   ├── worker.py         ← pengambil pekerjaan dari tabel antrean (SKIP LOCKED)
│   ├── storage.py        ← antarmuka simpan, ambil, hapus (folder disk sekarang)
│   └── db/               ← model dan migrasi PostgreSQL
├── dashboard/            ← Next.js static export + Leaflet: persetujuan peta, anchoring POI
├── deploy/               ← docker-compose.yml dan Dockerfile (PostgreSQL, API, pekerja)
├── spike/                ← eksperimen spike, tetap disimpan sebagai rujukan pengukuran
├── tests/
└── docs/
```

### 10.2 `eutopos-mobile`

```text
eutopos-mobile/           ← satu project Unity
├── Assets/
│   ├── Shared/           ← sesi ARCore, kerangka koordinat (T_sesi←gedung), klien API eutopos, akun
│   ├── Capture/          ← eutopos Mapper: pemilih foto kunci, cek buram, peta cakupan, sesi unggah
│   └── Navigation/       ← aplikasi navigasi: loop lokalisasi berkala, rute, POI, avatar, klien RAG
├── Packages/
├── ProjectSettings/
├── docs/
└── .gitattributes        ← Git LFS untuk aset biner (model 3D, tekstur, audio)
```

**Batas antar-folder ditegakkan dengan Assembly Definition**, satu per folder: `Capture` dan `Navigation`
masing-masing hanya boleh bergantung pada `Shared`, tidak saling bergantung. Dengan begitu kedua aplikasi
tetap bisa dipisah menjadi dua project kalau suatu saat dibutuhkan, tanpa membongkar kode. Dua aplikasi
dibangun dari scene dan ID aplikasi berbeda (mekanisme build diverifikasi, bagian 8 nomor 7).
