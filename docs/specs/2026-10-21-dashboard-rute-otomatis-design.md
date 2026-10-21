# Spesifikasi: rute otomatis, ruangan, dan uji rute di dashboard web (lingkup sempro)

Tanggal: 2026-10-21. Status: draf untuk ditinjau Bagus.
Repo: `RockHead07/eutopos-vps` (publik, AGPL-3.0). Klien: `RockHead07/eutopos-mobile` (tidak diubah).
Dasar: bimbingan Bu Evi 21 Oktober 2026 dan jawabannya di WhatsApp ("semua perubahan dilakukan di dashboard web,
termasuk user scan dan menambah ruangan baru"), sesi brainstorming 21 Oktober, catatan
`pa-academic/notes/2026-10-21-arahan-bu-evi.md`.

## 1. Maksud dan alasan

Bu Evi meminta platform yang bisa dipakai orang yang tidak paham Unity, misalnya staf RSI. Semua perubahan
(scan, menambah ruangan, rute) dilakukan di dashboard web. Sampai sekarang rute dan tujuan masih ditulis tangan
di CSV dan dipasang lewat skrip di PC Lab, dan POI hanya bisa dilihat atau dites setelah build APK.

Bagus terbiasa menaruh POI di Scene view Unity dan menguji navigasi di Play mode. Dashboard ini harus
menggantikan dua kebiasaan itu: **melihat tempat, menaruh ruangan, dan menguji rute sebelum ke lokasi.**

Peta dibuat dari satu kali scan video (sudah terbukti: hcm-lantai-10, 431 dari 431 frame). Jalur kamera saat scan
adalah jalur yang benar-benar dilalui orang, jadi **rute dibuat otomatis dari jalur itu**.

## 2. Tujuan, bukan tujuan, anti-tujuan

**Tujuan (sebelum sempro 15 Desember)**
- Graf rute dibuat otomatis dari jalur kamera scan, tanpa CSV yang ditulis tangan.
- Dashboard menampilkan peta 2D per lantai yang dibuat otomatis dari scan, plus foto asli dari rekaman scan saat
  sebuah titik diklik.
- Ruangan ditaruh dengan klik di peta.
- Sambungan rute bisa diperbaiki di dashboard (hapus, tambah, geser).
- Uji rute di dashboard: pilih titik awal dan ruangan tujuan, jalur tergambar dan bisa disimulasikan berjalan.
- Rute dan ruangan diterbitkan dari dashboard dan langsung dipakai aplikasi ponsel yang sudah ada, sehingga indoor
  navigation bisa didemokan di aplikasi.

**Bukan tujuan (di-hold, keputusan Bagus 21 Okt)**
- Kalibrasi ke meter. Dipakai `align.json` yang sudah terpasang dari koordinat asumsi (20 Okt).
- Uji akurasi. Disarankan dijadwalkan sebelum sempro setelah navigasi jalan, tetapi di luar spesifikasi ini.
- Scan baru yang menyambung ke peta gedung, mode tamu (disepakati: kontribusi tamu harus disetujui staf), barometer
  dan lantai, IMU saja, mesh permukaan, dan "tambah ruangan di sini" dari ponsel.
- Mengubah aplikasi ponsel.

**Anti-tujuan (gagal walaupun secara teknis jalan)**
- Pengelola gedung harus membuka Unity atau mengetik koordinat untuk melakukan apa pun.
- Editan manual hilang saat graf dasar dibuat ulang.
- Uji rute di dashboard memakai aturan rute yang berbeda dari aplikasi, sehingga lolos di dashboard tidak
  membuktikan apa pun di ponsel.
- Jarak di dashboard atau aplikasi disajikan sebagai meter sungguhan selama skalanya masih dari koordinat asumsi.
- Foto, awan titik, koordinat gedung, atau berkas rute area nyata masuk repo publik.

## 3. Keputusan

| Keputusan | Pilihan | Diputuskan oleh |
|---|---|---|
| Tempat semua perubahan | Dashboard web (Next.js yang sudah ada), dibuka di laptop atau browser ponsel | Bu Evi, Bagus |
| Kanvas utama | Peta 2D tampak atas per lantai, otomatis dari scan; 3D .glb hanya pelengkap | Bagus (setelah membahas best practice: Situm dan OpenIndoorMaps berbasis peta 2D) |
| Foto asli | Wajib, frame scan terdekat dari titik yang diklik | Bagus |
| Sumber rute | Jalur kamera scan, dihaluskan dan disederhanakan; editan manual sebagai lapisan terpisah | Bagus menyetujui arah; rincian Claude |
| Aplikasi ponsel | Tetap Unity dengan graf A* di `main`; format `navgraph.json` tidak berubah | Claude (tafsiran jawaban Bu Evi = pilihan A) |
| NavMesh dan `/navcontent` (worktree `D:/wt/navmesh`, `D:/wt/navcontent`) | Tidak dipakai; disimpan, tidak dilanjutkan, tidak dihapus tanpa izin Bagus | Claude |
| `/mapcloud` (worktree `D:/wt/navcontent`) | Logika `to_building` dipakai ulang untuk peta 2D dan .glb | Claude |
| Lingkup lantai | Satu area = satu lantai (hcm-lantai-10); model gedung dan lantai belum dibuat | Claude |
| Radius Sampai | Tetap aturan aplikasi (< 1,0 unit kerangka G); toleransi 3 sampai 4 m Bu Evi belum diterapkan | Terbuka, lihat bagian 10 |

## 4. Data dan kerangka

- Kerangka G (meter menurut `align.json`, tangan kanan, z ke atas, lantai z = 0), sama dengan `navgraph.json`
  dan `pose_building`. Selama kalibrasi di-hold, "meter" ini berasal dari koordinat asumsi, sehingga setiap angka
  jarak di dashboard diberi label "skala belum dikalibrasi".
- Semua fitur di spesifikasi ini membutuhkan versi peta aktif yang sudah diselaraskan (`aligned: true`). Bila
  belum, dashboard menampilkan alasannya dan tidak menawarkan penyuntingan.
- Sumber data per versi peta: model SfM (`<map_dir>/<run>/sfm`), `align.json`, dan frame scan di
  `/data/jobs/<job_id>/dataset/mapping/` (tetap tersimpan setelah video dihapus; sudah diperiksa di
  `server/worker.py`).
- **Satu pemilik per data:**
  - graf dasar: diturunkan dari jalur kamera, tidak disimpan tangan;
  - editan sambungan dan ruangan: disimpan di database (PostgreSQL yang sudah ada), per area;
  - `navgraph.json` terbit: diturunkan dari graf dasar + editan + ruangan saat staf menekan Terbitkan.

**Keputusan Claude saat pemeriksaan pembangun (21 Okt):**
- Graf dasar, peta 2D, dan foto diambil dari **versi peta yang sedang terbit** untuk area itu.
- Bila sebuah job berisi beberapa video, jalur kamera **dipisah per video** (tidak disambung antarujung video);
  sambungan antarjalur muncul dari penggabungan simpul yang berdekatan.
- Ruangan dan editan disimpan di G. Bila `align.json` versi terbit berganti (misalnya setelah kalibrasi meter
  dilakukan nanti), ruangan dan editan **dipindahkan otomatis** dari G lama ke G baru lewat model SfM yang sama
  (G lama ke model ke G baru, dua Sim3 yang sudah diketahui). Untuk versi peta baru dari scan lain, perpindahan ini
  belum bisa dihitung sampai fitur sambung scan ada; dashboard memperingatkan sebelum versi seperti itu diterbitkan.
- Kasus uji aturan rute bersama dimiliki `eutopos-vps` (`tests/fixtures/route_cases.json`). `eutopos-mobile` menyimpan
  salinan dengan baris keterangan sumbernya. Ini satu-satunya salinan yang disengaja, karena dua repo tidak bisa
  saling membaca di CI.

## 5. Komponen

### 5a. Graf dasar dari jalur kamera (server)

- Masukan: pusat kamera semua frame peta dalam G, diurutkan menurut urutan frame (urutan waktu video).
- Proses: proyeksi ke bidang lantai (x, y), penghalusan, penyederhanaan garis, lalu penggabungan simpul yang
  berdekatan supaya jalur yang dilewati dua kali atau bersilangan menjadi satu persimpangan, bukan dua jalur
  sejajar. Hasilnya graf tak berarah dengan panjang sisi = jarak Euclid.
- Bukti awal (21 Okt, data hcm-lantai-10): jalur kamera menyusuri lorong di antara meja tetapi bergerigi dan
  bolak-balik, sehingga penghalusan dan penggabungan wajib.
- Nilai ambang (jendela penghalusan, toleransi penyederhanaan, jarak gabung) diserahkan ke pembangun, dengan
  syarat: tidak ada sisi yang memotong area yang tidak pernah dilalui kamera lebih dari ambang kecil.

### 5b. Editan dan ruangan (database + API dashboard)

- **Ruangan:** id stabil, area, nama, posisi (x, y di G). Dibuat, diganti nama, digeser, dihapus dari dashboard.
- **Editan sambungan:** tambah sambungan, hapus sambungan, geser simpul. Disimpan **dengan koordinat**, bukan id
  simpul graf dasar, supaya tetap berlaku saat graf dasar dibuat ulang dari scan lain di area yang sama. Editan
  yang tidak lagi cocok dengan graf dasar baru ditandai di dashboard, tidak dibuang diam-diam.
- Ruangan menjadi simpul graf yang disambung ke titik terdekat pada graf (proyeksi ke sisi terdekat). Id simpul
  ruangan diturunkan dari id ruangan, sehingga target di aplikasi tetap stabil.
- Hak: membaca untuk pengguna dashboard yang masuk; menulis dan menerbitkan hanya admin (`EUTOPOS_ADMINS`), sama
  dengan penerbitan versi peta sekarang.

### 5c. Peta 2D per lantai (server)

- Gambar tampak atas dari awan titik dalam G, hanya titik di ketinggian sekitar 0,2 sampai 2,2 m (dinding, meja,
  kursi), plus metadata asal dan resolusi supaya dashboard bisa mengubah piksel ke G dan sebaliknya.
- Dibuat sekali per versi peta dan dibuat ulang bila `align.json` berganti (gambar mengikuti kerangka G).
- Bukti awal (21 Okt): gambar dari hcm-lantai-10 (37.655 titik, sekitar 5,5 x 7,3 m) menampilkan blok meja dan
  lorong dengan jelas; Bagus menilai bisa langsung menunjuk tempat dari gambar itu.

### 5d. Foto asli (server)

- Dari titik (x, y) yang diklik: frame scan dengan pusat kamera terdekat, dikembalikan sebagai gambar kecil
  beserta arah hadapnya, supaya staf yakin tempatnya benar.
- Bila frame sudah tidak ada di disk: jawaban kosong yang jelas, peta tetap berfungsi.
- Hanya lewat `/api` (Cloudflare Access + JWT pengguna dashboard), tidak lewat jalur service token aplikasi.
- **Diubah saat menyusun rencana (21 Okt):** container `api` tidak memasang `/data/jobs`, jadi worker membuat foto
  kecil (tanpa EXIF) ke folder peta saat build, ditambah `manage thumbs` untuk peta yang sudah ada.

### 5e. Uji rute

- Staf memilih titik awal (klik di peta) dan ruangan tujuan. Jalur tergambar di peta beserta panjangnya, dan
  simulasi menggerakkan penanda di sepanjang jalur sampai masuk radius Sampai.
- **Aturan rute sama dengan aplikasi** (`NavGraph` C# di `eutopos-mobile` `main`: proyeksi posisi ke sisi
  terdekat, A* ke simpul target, Sampai bila jarak < 1,0). Dihitung di server dari graf yang sama dengan yang
  akan diterbitkan. Untuk mencegah dua implementasi menyimpang, kasus uji yang sama (berkas JSON berisi graf,
  titik awal, target, dan hasil yang diharapkan) dijalankan di pytest server dan di tes EditMode aplikasi.
- Uji rute bisa dijalankan pada graf yang belum diterbitkan (pratinjau).

### 5f. Terbitkan

- Tombol Terbitkan menyusun `navgraph.json` (graf dasar + editan + ruangan, format yang sama dengan sekarang:
  `frame`, `units`, `nodes`, `edges`, `targets`) dan memasangnya ke `<maps>/<area_id>/navgraph.json` secara atomik
  dengan validasi yang sudah ada (`server/navgraph.py`). `/navgraph` dan aplikasi memakainya tanpa restart dan tanpa
  build ulang APK. **Diubah saat menyusun rencana (21 Okt):** container `api` membaca `/maps` saja, jadi graf terbit
  disimpan di database dan `/navgraph` membacanya lebih dulu, dengan berkas sebagai cadangan.
- Peringatan sebelum terbit bila ada ruangan yang tidak terjangkau dari ruangan lain atau editan yang ditandai
  tidak cocok.

### 5g. Tampilan 3D pelengkap (prioritas terendah)

- Awan titik berwarna dalam .glb (primitif titik glTF 2.0, warna per titik), dikonversi dari G ke sumbu glTF
  (Y ke atas). Dibuka sebagai tampilan putar di dashboard, bukan tempat mengedit. Boleh dipotong bila waktu tidak
  cukup.

## 6. Dashboard (halaman)

Satu halaman area (dari daftar Peta) dengan peta 2D sebagai kanvas dan lapisan yang bisa dinyalakan: titik peta,
jalur scan, graf rute, ruangan. Mode:
1. **Lihat**: klik di mana saja menampilkan foto asli terdekat.
2. **Ruangan**: klik untuk menambah, seret untuk menggeser, panel daftar untuk mengganti nama atau menghapus.
3. **Rute**: hapus, tambah, atau geser sambungan; editan yang tidak cocok ditandai.
4. **Uji rute**: titik awal, tujuan, jalur, simulasi.
5. Tombol **Terbitkan** dengan ringkasan perubahan sejak terbitan terakhir.

Mockup percakapan 21 Okt (`.superpowers/brainstorm/`, gitignored) menjadi acuan susunan, bukan desain akhir. Gaya
mengikuti dashboard yang sudah ada (palet forest, sage, kartu krem; Tailwind v4 dengan token di `@theme`).

## 7. Keamanan dan data

- Peta 2D, foto, .glb, ruangan, dan editan hanya lewat `/api` dengan JWT Cloudflare Access; menulis hanya admin.
- Tidak ada data area nyata di repo atau di fixture tes; tes memakai jalur dan titik sintetis.
- Frame scan adalah foto interior gedung: gambar kecil saja, tanpa EXIF, tidak disimpan ulang di luar folder job.

## 8. Pengujian

- **Graf dasar (pytest, sintetis):** jalur berbentuk L dengan derau menghasilkan graf L yang halus; jalur yang
  melewati lorong yang sama dua kali menghasilkan satu jalur, bukan dua; jalur berputar menghasilkan persimpangan;
  tidak ada sisi yang memotong area kosong.
- **Editan:** penerapan tambah, hapus, geser; editan tetap berlaku pada graf dasar yang dibuat ulang dari jalur
  yang sedikit bergeser; editan yang tidak cocok ditandai.
- **Ruangan:** tersambung ke sisi terdekat; id simpul stabil; ruangan tak terjangkau memicu peringatan.
- **Aturan rute bersama:** berkas kasus JSON yang sama lolos di pytest dan di EditMode `eutopos-mobile`.
- **API:** hak baca dan tulis (admin), 404 dan 409 (belum diselaraskan), terbit atomik dan tervalidasi.
- **Dashboard:** typecheck dan build lolos; cek manual di browser dengan data hcm-lantai-10.
- **Demo sempro (penerimaan):** dari data hcm-lantai-10, graf dibuat otomatis, minimal satu ruangan ditaruh lewat
  klik, uji rute di dashboard menampilkan jalurnya, terbit, lalu aplikasi di TECNO KL7 bernavigasi ke ruangan itu
  dan banner Sampai muncul. Tanpa CSV, tanpa Unity, tanpa build ulang APK.

## 9. Risiko

| Hal | Mengapa penting | Cara cek |
|---|---|---|
| Jalur bergerigi dan bolak-balik | Graf penuh simpul kecil atau jalur sejajar | Tes sintetis + lihat hasil di data hcm-lantai-10 |
| Area yang tidak pernah dilalui saat scan | Tidak ada rute ke sana | Ditambah manual lewat editan; ke depan dari scan tambahan |
| Skala dari koordinat asumsi | Panjang rute dan radius Sampai bukan meter nyata | Label di dashboard; kalibrasi setelah hold dicabut |
| Dua implementasi aturan rute (Python dan C#) | Hasil uji di dashboard beda dengan ponsel | Kasus uji JSON bersama |
| Frame scan terhapus atau job lama | Foto asli tidak tersedia | Jawaban kosong yang jelas |
| Peta 2D berbintik (awan titik jarang) | Sulit dibaca | Foto asli sebagai pendamping; vektorisasi dinding nanti |

## 10. Pertanyaan terbuka

- **Radius Sampai:** tetap < 1,0 atau ikut toleransi 3 sampai 4 m dari Bu Evi (yang beliau sebut untuk galat
  posisi). Perlu keputusan Bagus atau Bu Evi; tidak memblokir pembangunan karena aplikasi sudah memakai < 1,0.

## 11. Urutan kerja (garis besar)

1. Graf dasar dari jalur kamera + tes sintetis; lihat hasilnya pada data hcm-lantai-10 sebelum lanjut.
2. Peta 2D dan foto asli (server) + halaman area dengan mode Lihat.
3. Ruangan dan editan (database, API, mode Ruangan dan Rute).
4. Uji rute + kasus uji bersama dengan `eutopos-mobile`.
5. Terbitkan + demo di ponsel.
6. Tampilan 3D .glb bila waktu cukup.

## 12. Yang diserahkan ke pembangun

Algoritma penghalusan, penyederhanaan, dan penggabungan beserta ambangnya (dengan syarat di 5a dan tes di 8),
skema tabel, nama endpoint, resolusi gambar, cara menggambar lapisan di browser (SVG atau canvas di atas gambar;
tanpa pustaka peta berat kecuali ada alasan), gaya simulasi, dan cara mencocokkan editan ke graf dasar baru.
