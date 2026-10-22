# Spesifikasi: area walkable (kuas), panah rute di AR, dan penanda POI melayang

Tanggal: 2026-10-21. Status: draf untuk ditinjau Bagus. Belum ada yang dibangun.
Repo: `RockHead07/eutopos-vps` (server dan dashboard) dan `RockHead07/eutopos-mobile` (aplikasi ponsel).
Dasar: uji lapangan 21 Okt sore di TECNO KL7 (log sesi 17.08 yang dibaca ulang lewat aturan rute server),
usulan Bagus ("area walkable seperti NavMesh, diblok dengan kuas lebar"), dan permintaan "bentuk panah" serta
"objek melayang penanda POI".
Melanjutkan: `2026-10-21-dashboard-rute-otomatis-design.md`. Dua hal di spesifikasi itu **dicabut** oleh dokumen
ini: sumber rute berpindah dari graf titik ke area walkable, dan aplikasi ponsel **boleh diubah** (sebelumnya
bukan tujuan).

## 1. Maksud dan alasan

Uji lapangan membuktikan alur ujung ke ujung jalan: ruangan dibuat di dashboard, diterbitkan, dan aplikasi
membawa pengguna sampai banner "Sampai". Dua kekurangan terlihat.

**Rute berangkat ke arah yang salah.** Aturan rute sekarang (`NavGraph.Plan`, dan port Python-nya) menarik posisi
pengguna ke garis graf terdekat, lalu mengikuti titik graf. Posisi pengguna dari log sesi 17.08 saya jalankan ulang
lewat aturan itu (10 hitungan ulang): di semuanya, rute menuju dulu ke garis graf, lalu ke pojok graf di sisi
kanan, baru naik ke Kamar Tidur, padahal Kamar Tidur hampir lurus ke depan. Contoh: dari posisi (2,21, -1,01) rute
sepanjang 2,52 satuan, jarak lurusnya 1,96. Pada empat hitungan pertama titik awalnya juga pindah-pindah
(E18b, N6, N7), yang paling mungkin tampak sebagai pita yang bersilang di AR. Memotong jalan lewat titik
proyeksi tidak menyembuhkan ini: graf titik tidak tahu apakah jalan pintas itu menembus meja. Yang tahu hanya
data **area yang boleh dilewati**.

**Tampilan AR belum menyampaikan tujuan.** Pita lebar sulit dibaca arahnya, dan tidak ada penanda di dunia nyata
yang menunjukkan di mana tujuannya.

Prinsip dari proyek ini berlaku di sini: satu pemilik data, sisanya diturunkan. **Area walkable menjadi satu-satunya
pemilik data "di mana boleh berjalan".** Rute, peta kecil, dan pesan "ruangan di luar jangkauan" diturunkan darinya.
Tidak ada salinan yang di-maintain manual.

## 2. Tujuan, bukan tujuan, anti-tujuan

**Tujuan (sebelum sempro 15 Desember)**
- Dashboard punya mode **Walkable**: area awal dicat otomatis dari jalur scan, lalu staf menambah dengan kuas dan
  menghapus dengan penghapus. Hasilnya langsung terlihat di peta 2D.
- Rute dihitung di atas area itu, berangkat langsung dari posisi pengguna ke tujuan, dan **diluruskan** (tidak
  mengikuti garis scan).
- Aplikasi menggambar rute sebagai **deretan panah chevron di lantai** yang tetap diam di dunia dan bergerak
  menuju tujuan.
- Aplikasi menampilkan **penanda POI melayang** (pin dengan nama dan jarak) di lokasi tujuan yang dipilih.
- Setelah Publish, aplikasi mengambil rute baru saat Lokalisasi, tanpa harus ditutup dan dibuka lagi.
- Uji rute di dashboard memakai aturan yang sama persis dengan aplikasi (kasus uji bersama dua bahasa).

**Bukan tujuan**
- Meningkatkan akurasi lokalisasi. Tidak bisa diperbaiki sebelum diukur; protokol pengukuran dengan meteran
  adalah pekerjaan terpisah (bagian 8).
- Kalibrasi skala ke meter (masih di-hold). Semua jarak di dokumen ini dalam satuan peta G.
- Penunjuk arah di tepi layar bila penanda POI di luar pandangan (cukup peta kecil untuk versi pertama).
- Banyak lantai, tangga, dan elevator. Satu area, satu lantai, seperti sekarang.
- Model 3D buatan. Panah dan pin dibuat dari mesh kode, tanpa aset (bagian 5E dan 5F).
- Tampilan 3D awan titik (.glb) di dashboard. Endpoint `/cloud.glb` sudah ada dan teruji, tetapi halaman area
  belum punya penampilnya. Statusnya tidak berubah dari spesifikasi sebelumnya (bagian 5g: prioritas terendah).
  Awan titik juga **tidak bisa dipakai** untuk menurunkan area walkable otomatis: pada peta hcm-lantai-10 hanya
  2 dari 38.744 titik yang berada di ketinggian lantai (kamera berada sekitar 1,33 dari lantai). Itu butuh mesh
  permukaan, yang di luar lingkup sempro.

**Anti-tujuan (gagal walaupun secara teknis jalan)**
- Dua sumber kebenaran untuk "boleh berjalan di mana" (misalnya graf yang disunting tangan di samping area).
- Rute yang menembus area yang sengaja dihapus staf.
- Dashboard dan aplikasi memberi rute berbeda untuk titik awal dan tujuan yang sama.
- Posisi atau penanda ditampilkan di luar sesi AR yang sudah dilokalisasi (ADR-007, ADR-011 repo DARSI, prinsip
  yang sama).

## 3. Keputusan

| # | Keputusan | Alasan |
|---|---|---|
| 1 | Area walkable disimpan sebagai **raster** (grid sel 0,10 satuan G), bukan poligon. | Kuas menghasilkan raster secara alami. Poligon butuh library boolean geometry (dependensi baru, dan hasilnya sulit dibuat identik di Python dan C#). |
| 2 | Yang disimpan di database adalah **goresan kuas** (bukan hasil raster), bersama jalur scan. Raster dihitung ulang dari keduanya. | Sama dengan pola `route_edit`: editan tetap berlaku bila graf dasar dibuat ulang, dan tidak ada raster salinan yang bisa melenceng. |
| 3 | Server menghitung **grid siap pakai** (sudah dierosi radius agen 0,2). Aplikasi tidak menghitung ulang, hanya merencanakan di atasnya. | Satu pemilik. Mengubah radius agen tidak perlu APK baru. |
| 4 | Perencana: A* delapan arah di grid, biaya bilangan bulat (10 dan 14), tanpa memotong sudut, lalu diluruskan dengan line-of-sight. Semua tie-break ditetapkan. | Bilangan bulat membuat hasil Python dan C# sama persis. Tanpa tie-break, dua implementasi memberi jalur berbeda yang sama panjang. |
| 5 | Titik awal di luar area diproyeksikan ke sel walkable terdekat. Ruangan juga diikat ke sel walkable terdekat, dengan peringatan bila lebih jauh dari 1,5 satuan. | Perilaku yang sama dengan `TryProject` hari ini, jadi pengguna yang melenceng sedikit tetap dapat rute. |
| 6 | Seed otomatis: sel dalam radius **0,5** dari jalur scan. | Jalur scan terbukti bisa dilewati. Radius 0,5 memberi lorong selebar kira-kira 1 satuan. Angka awal, bisa diubah. |
| 7 | Mode **Routes** disembunyikan dari dashboard. Endpoint editan graf dan tabel `route_edit` tetap sampai graf titik dipensiunkan. | Pencabutan data bukan urusan perubahan ini. |
| 8 | Selama masa transisi `/navgraph` **tetap mengirim `graph` lama** dan menambah `walkable`. APK lama jalan terus. Graf dipensiunkan sesudah APK baru terverifikasi di ponsel. | Tidak ada yang rusak bila APK dan server tidak diperbarui bersamaan. Biayanya dua bentuk data selama beberapa hari. |
| 9 | Penanda POI hanya untuk **target yang dipilih**, dan hanya saat `HasAlignment` dan tidak `needsRelocalize`. | Mengurangi kekacauan di layar, dan menghormati prinsip "posisi hanya valid setelah localize". |
| 10 | Panah ditempatkan dengan jarak dihitung **dari tujuan**, lalu digeser menurut fase animasi. | Supaya panah diam di dunia saat pengguna berjalan. Jika dihitung dari posisi pengguna, panah ikut bergerak bersamanya dan terlihat menempel. |
| 11 | Setelah Publish, aplikasi mengambil ulang graf saat tombol Lokalisasi **bila `revision` berubah**, dan tidak sedang navigasi. | Hari ini graf hanya diambil sekali per peluncuran (`EnsureNavGraph` berhenti bila `graph != null`). Teks "atau Lokalisasi" di dashboard salah. |

Keputusan 1, 3, 4, 8, 9, dan 10 adalah pilihan saya (Claude), bukan hasil percakapan. Tolong tinjau.

## 4. Data dan kerangka

Semua koordinat dalam kerangka G (tangan kanan, z ke atas, sama dengan `align.json` hari ini). Grid hanya 2D (x, y).

**Grid.** `origin` = sudut kiri bawah sel (0,0), `cell_m` = 0,10, `width`, `height`. Indeks `i = row * width + col`,
`col = floor((x - ox) / cell_m)`, `row = floor((y - oy) / cell_m)`. Baris naik searah y (peta PNG membaliknya
sendiri). Pusat sel adalah `(ox + (col + 0,5) * cell_m, oy + (row + 0,5) * cell_m)`. Luas grid = kotak pembatas
peta 2D (`plan` meta) ditambah margin 3 satuan; bila melebihi 400 ribu sel, `cell_m` dinaikkan ke 0,20.

**Penyusunan (server).**
1. Seed: sel yang pusatnya berjarak ≤ 0,5 dari ruas mana pun pada urutan kamera (ruas dari `split_sequences`).
2. Goresan, urut `id`: `paint` menyalakan sel dalam radius `r` dari polyline goresan, `erase` mematikannya.
3. Erosi radius agen 0,2: sel tetap walkable hanya bila semua sel berpusat dalam 0,2 darinya walkable (di luar
   grid dianggap tidak walkable).
Hasil langkah 3 adalah **grid rencana**. Dashboard menampilkan grid rencana (apa yang terlihat adalah yang dipakai
rute).

**Tabel baru `walkable_stroke`** (migrasi 0004): `id`, `area_id`, `mode` (`paint` atau `erase`), `radius`
(0,1 sampai 3), `points` (JSON `[[x, y], ...]`, maksimum 2000), `created_by`, `created_at`.
Kolom baru `walkable` (JSON, boleh kosong) di `published_graph`.

**Muatan `/navgraph`** (tambahan, `graph` tidak berubah):

```json
{ "area_id": "...", "map_version": 1, "revision": "<published_at ISO>",
  "graph": { "...": "bentuk lama, tidak berubah" },
  "walkable": {
    "frame": "building", "units": "m",
    "cell_m": 0.1, "origin": [ox, oy], "width": 0, "height": 0,
    "bits": "<base64, row-major, bit k dari byte b = sel 8b+k, LSB dulu>",
    "targets": [ { "id": "R2", "name": "Kamar Tidur", "x": 0.0, "y": 0.0 } ]
  } }
```

APK lama mengabaikan `walkable` dan `revision` (kunci tak dikenal), jadi tetap bisa memakai `graph`.

## 5. Komponen

### 5A. Server: `server/walkable.py` (modul baru)

Fungsi murni, tanpa database dan tanpa HTTP, supaya mudah diuji:
- `seed(sequences, bounds, cell_m, radius) -> Grid`
- `apply_strokes(grid, strokes) -> Grid`, `erode(grid, radius) -> Grid`
- `components(grid) -> list[int]` (label komponen terhubung delapan arah, tanpa memotong sudut)
- `anchor(grid, point) -> (index, distance)` (sel walkable terdekat; seri: indeks terkecil)
- `plan_route(grid, start, goal) -> {"points", "length_m"} | None`
- `encode(grid) -> dict`, `decode(dict) -> Grid` (bagian 4)

**Perencana (didefinisikan lengkap supaya C# bisa menirunya):**
1. `s = anchor(start)`, `g = anchor(goal)`. Bila grid tidak punya sel walkable, hasilnya `None`. Bila `g`
   tidak terjangkau dari `s`, daftar terbuka A* habis dan hasilnya juga `None` (tanpa pemeriksaan komponen
   terpisah; `components` hanya dipakai untuk peringatan Publish).
2. A*, delapan tetangga. Gerak lurus berbiaya 10, diagonal 14. Diagonal hanya boleh bila kedua sel orthogonal yang
   mengapitnya walkable. Heuristik oktil `10 * max(dx, dy) + 4 * min(dx, dy)`. Urutan prioritas: `f` terkecil,
   lalu `h` terkecil, lalu indeks terkecil. Semua bilangan bulat.
3. Peluruskan: mulai dari sel awal, cari sel terjauh pada jalur yang terlihat lewat line-of-sight (Bresenham
   bilangan bulat standar; semua sel yang dilalui walkable), lompat ke sana, ulangi sampai sel tujuan.
4. `points` = `[start persis, pusat sel hasil peluruskan, goal persis]`. Pusat sel pertama dibuang bila `start`
   berada di sel walkable, dan pusat sel terakhir dibuang bila `goal` berada di sel walkable (kalau tidak, rute
   berbelok ke pusat sel yang tidak perlu). Bila sel awal dan akhir sama dan keduanya walkable, tidak ada titik
   tengah. Bila `start` bukan sel walkable, segmen pertama dari `start` ke pusat sel jangkarnya lurus, tidak
   dicek.
5. `length_m` = jumlah jarak Euclid antar `points`.

**Peringatan Publish** (menggantikan "tidak ada ruas"): 409 bila tidak ada sel walkable, atau tidak ada ruangan;
peringatan (tidak menolak) untuk ruangan > 1,5 satuan dari sel walkable terdekat, dan ruangan yang tidak berada di
komponen terbesar.

### 5B. Server: API (`server/area_api.py`)

- `GET /api/areas/{id}/walkable`: `{cell_m, origin, width, height, bits, strokes: [...], warnings: [...]}`
- `POST /api/areas/{id}/strokes` (201): `{mode, radius, points}`. Hanya admin dan `application/json`. Angka harus
  hingga (`allow_inf_nan=False`), `radius` 0,1 sampai 3, titik 1 sampai 2000, selain itu 422.
- `DELETE /api/areas/{id}/strokes/{sid}` (204) dan `DELETE /api/areas/{id}/strokes` (204, kosongkan semua).
- `POST /api/areas/{id}/route` memakai `plan_route` di atas. Bentuk jawabannya:
  `{"status": "ok", "points": [...], "length_m": n}` atau `{"status": "unreachable"}`. Kunci `nodes` dihapus.
- `POST /publish-graph` menerbitkan `graph` (lama) dan `walkable` sekaligus. `GET /navgraph` menambah
  `walkable` dan `revision`.
- `GET /plan` tidak berubah. Cache grid dikunci per (area, align, jumlah image, id goresan terakhir).

### 5C. Dashboard (`web/app/area/page.tsx`, `web/components/AreaMap.tsx`)

- Mode baru **Walkable** menggantikan **Routes** di bilah mode: View, Walkable, Rooms, Test route.
- Alat: **Paint**, **Erase**, ukuran kuas (geser, 0,3 sampai 1,5 satuan radius), **Undo** (hapus goresan terakhir),
  **Reset to scan path** (hapus semua goresan, lewat panel konfirmasi di halaman, bukan `window.confirm`).
- Kursor berupa lingkaran SVG berukuran sesuai radius kuas. Saat menyeret, goresan digambar langsung sebagai
  polyline tebal. Saat pointer dilepas, satu `POST /strokes` dikirim, lalu `GET /walkable` mengisi ulang overlay.
- Overlay grid rencana: hijau transparan di atas peta, digambar di klien dari `bits` (tanpa gambar baru dari server).
- Test route memakai `points` dari server (garis oranye lurus). Simulasi berjalan di atas `points`.
- **Perbaikan kecil yang ikut:**
  - Hasil Publish tampil sebagai panel tetap di bawah bilah mode ("Published pukul 16.34. Aplikasi mengambil rute
    baru saat Lokalisasi berikutnya."), tidak hilang sendiri.
  - Label ruangan dikecilkan (huruf 1,8% dari sisi terpanjang peta, supaya ukurannya tidak bergantung pada resolusi) dan diberi halo putih.

### 5D. Aplikasi: perencana dan pengambilan ulang

- `Core/WalkableGrid.cs` (baru): `Parse(JObject)`, `Plan(from, to) -> Route`. Algoritma sama dengan 5A. Antrean
  prioritas dibuat sendiri (heap biner, kunci `int64`), karena `PriorityQueue<T>` tidak ada di target Unity ini.
- `Route`: `NodeIds` dikosongkan (tinggal `Points` dan `LengthM`). Log `route` mencatat `waypoints` dan `length_m`,
  bukan `nodes`.
- `AppController`: field `graph` menjadi `nav` (grid dan daftar target). `Arrived` memakai titik ruangan.
- Pengambilan ulang: `EnsureNavGraph` dipanggil juga saat tombol Lokalisasi. Bila `revision` berbeda dan tidak
  sedang navigasi, grid diganti dan target yang dipilih dipertahankan menurut `id`.
- `MiniMap`: memakai grid walkable sebagai tekstur latar menggantikan garis graf.

### 5E. Aplikasi: panah chevron (`App/RouteView.cs`, ditulis ulang)

- Pita `LineRenderer` dan segitiga arah diganti **kolam 12 objek chevron**: satu `Mesh` berbentuk V (enam
  verteks) dan satu material `Sprites/Default` yang dibagi bersama. Tanpa model 3D, tanpa aset baru.
- Parameter awal: jarak antar panah 0,9; panjang 0,5; lebar 0,55; tinggi 0,03 di atas lantai; warna biru yang
  sama dengan rute sekarang. Hanya 8 satuan rute di depan pengguna yang digambar, dan alfa memudar di 2 satuan
  terakhir.
- Panah ke-`k` berada pada jarak `k * 0,9 - fase` dari **tujuan** menurut panjang busur rute, dengan `fase`
  naik 0,6 satuan per detik lalu berulang tiap 0,9. Hasilnya panah diam di dunia (tidak menempel ke pengguna) dan
  mengalir menuju tujuan.
- Arah tiap panah = garis singgung rute pada posisinya. Posisi dihaluskan (lerp) saat rute dihitung ulang supaya
  tidak melompat. Keterbatasan jujur: bila bentuk rute berubah banyak, panah tetap bergeser sedikit.
- Logika penempatan (`ChevronPlacer.Place(points, spacing, fase, maxAhead)`) adalah fungsi murni di `Core` supaya
  bisa diuji di EditMode. Bagian Unity hanya memasang `Transform`.

### 5F. Aplikasi: penanda POI melayang (`App/PoiPin.cs`, baru)

- Pin untuk target yang dipilih: bola kecil oranye (#E07A2E, sama dengan dashboard) di ketinggian 1,5 pada
  `BuildingRoot`, dengan garis tipis tegak lurus ke lantai.
- Label di atas pin pada **World Space Canvas** dengan `Text` (pola `AppUi.Label`): nama ruangan dan jarak,
  misalnya "Kamar Tidur, 3,2 m". Selalu menghadap kamera (hanya yaw, tetap tegak). Skalanya mengikuti jarak
  (dibatasi minimum dan maksimum) supaya tetap terbaca dari jauh.
- Hanya terlihat saat `HasAlignment` dan tidak `needsRelocalize`. Bobbing kecil naik turun supaya mudah terlihat.
- Jika Bagus ingin pin dengan bentuk lebih bagus dari primitif, itu satu-satunya tempat aset 3D masuk akal
  (model pin atau marker). Jika tidak disediakan, primitif dipakai.

## 6. Pengujian

**Server (pytest).** `walkable.py`: seed, urutan goresan (paint lalu erase di tempat yang sama), erosi (lorong
dengan lebar kurang dari dua kali radius agen hilang), komponen, jangkar (seri), perencana (garis lurus di ruang
terbuka, memutar lewat celah, dua area terpisah tak terjangkau, titik awal di dalam tembok, sudut tidak dipotong),
`encode` lalu `decode` utuh. API: goresan non-admin 403, bukan JSON 415, angka NaN atau tak hingga 422, radius di
luar batas 422, undo, reset.

**Kasus uji bersama dua bahasa.** `tests/fixtures/walkable_cases.json` disalin ke
`eutopos-mobile/Assets/Eutopos/Tests/EditMode/`. Grid ditulis sebagai teks supaya terbaca (`#` tembok, `.`
walkable, baris paling atas = y tertinggi). Dibandingkan: `points` (toleransi 1e-3) dan `length_m` (toleransi
1e-3). Termasuk kasus yang menguji urutan bit `bits` (base64 sama persis di dua sisi).

**Aplikasi (EditMode).** Kasus bersama, `ChevronPlacer` (jumlah panah, jarak, arah, memudar), `PoiPin` tidak diuji
unit (murni visual).

**Dashboard.** `next build` lolos, lalu pratinjau lokal dengan data hcm-lantai-10 (alur yang sama seperti
verifikasi Task 5 sebelumnya): cat, hapus, undo, reset, Test route, Publish, `/navgraph` berisi `walkable`.

**Lapangan.** Bagus menerbitkan dari dashboard, menekan Lokalisasi tanpa menutup aplikasi, dan memeriksa tiga
hal: panah tidak berbalik arah di awal, rute lurus dan tidak menembus meja, pin muncul di lokasi tujuan.

## 7. Risiko

- **Lorong sempit hilang karena erosi.** Jalur scan yang rapat ke dinding menghasilkan seed selebar 1 satuan;
  erosi 0,2 membiarkannya. Goresan sempit (radius kurang dari 0,3) tidak diperbolehkan di UI untuk mencegah staf
  melukis jalur yang tidak akan terpakai.
- **Skala belum dikalibrasi.** Radius kuas, jarak panah, tinggi pin, dan radius Sampai semua dalam satuan G.
  Bila skala sebenarnya meleset, semuanya ikut meleset sebanding. Ini sudah diketahui dan menunggu kalibrasi.
- **Panah bergeser saat rute dihitung ulang.** Dihaluskan, tidak dihilangkan.
- **Grid besar.** Batas 400 ribu sel (sekitar 50 KB `bits` sebelum base64) cukup untuk satu lantai.
- **Dua staf menyunting bersamaan.** Goresan terakhir yang menang di tampilan; keduanya tersimpan. Publish terakhir
  yang menang.
- **Dua implementasi harus sama persis.** Dijaga oleh bilangan bulat, tie-break tertulis, dan kasus uji bersama.
  Tanpa kasus bersama yang lolos, perubahan tidak boleh digabung.

## 8. Pertanyaan terbuka

1. Radius seed 0,5 dan radius agen 0,2 hanya angka awal. Perlu dilihat di lapangan.
2. Radius "Sampai" (1 satuan atau 3 sampai 4 meter) masih terbuka dari spesifikasi sebelumnya. Sekarang ia berlaku
   terhadap titik ruangan, bukan simpul graf.
3. **Protokol pengukuran akurasi** (pekerjaan terpisah, belum dirancang): berdiri di beberapa titik yang jaraknya
   diukur dengan meteran, bandingkan dengan posisi menurut aplikasi. Ini syarat sebelum kita bisa mengatakan
   akurasi membaik. Perlu keputusan Bagus kapan hold dicabut.
4. Penanda POI untuk semua target atau hanya yang dipilih. Spesifikasi ini memilih yang dipilih (keputusan 9).

## 9. Urutan kerja (garis besar)

1. `server/walkable.py`, fixture bersama, dan tes (Python).
2. Migrasi 0004, API, Publish, `/navgraph` (dengan `revision`), dan tes API.
3. Dashboard: mode Walkable, overlay, Test route baru, panel Publish, label. Pratinjau lokal.
4. Aplikasi: `WalkableGrid.cs` dan kasus bersama, `Route`, pengambilan ulang, `MiniMap`.
5. Aplikasi: `ChevronPlacer` dan `RouteView` baru.
6. Aplikasi: `PoiPin`.
7. Merge, backfill (tidak perlu, foto kecil sudah ada), build APK, uji di TECNO KL7.

Tugas 1 sampai 3 di eutopos-vps; 4 sampai 6 di eutopos-mobile. APK baru dibangun hanya setelah tugas 4 sampai 6
selesai. Selama itu APK yang terpasang tetap jalan (keputusan 8).

## 10. Yang diserahkan ke pembangun

Nilai awal parameter (jarak panah, tinggi pin, kecepatan fase, radius kuas minimum), nama kelas dan berkas selain
yang disebut, tata letak panel di dashboard, dan bentuk persis chevron boleh ditentukan pembangun selama
perilaku di bagian 5 terpenuhi. Algoritma perencana di 5A **tidak** boleh diubah tanpa mengubah kasus bersama
(kedua bahasa harus tetap identik).
