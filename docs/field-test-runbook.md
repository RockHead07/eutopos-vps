# Runbook: Uji Lapangan Lantai 10

Panduan kerja lapangan untuk uji coba awal di area lab lantai 10 gedung PENS pusat (ruang terbuka di
depan lab dan lorong yang tersambung), **Selasa 29 September 2026**. Dasarnya `docs/spike-plan.md`
(bagian 4.1, aturan memotret, dan protokol titik acuan). Kalau ada yang bertentangan,
`spike-plan.md` yang berlaku.

**Keluaran hari ini:** 2 video peta per area, 40 foto uji di 20 titik terukur, dan `reference_points.csv`.
Semuanya disimpan di luar git.

**Keputusan yang dipakai (2026-09-28):**
- Video peta pagi, foto uji siang atau sore **di hari yang sama**, supaya pencahayaannya berbeda.
- **Satu ponsel** untuk peta dan foto uji. Uji lintas ponsel dilakukan belakangan.
- Meteran pita ditambah satu teman. Pakai meteran laser kalau lab punya.
- Data disimpan di laptop, PC lab, dan folder Google Drive pribadi yang tidak dibagikan.
- Peta direkam sebagai **video dengan jalur berkelok seperti ular, dua arah**, mengikuti pola panduan
  capture MultiSet. Foto satu per satu hanya cadangan.

## H-1 (Senin): persiapan

- [ ] Ajak **satu teman** untuk pagi (memegang ujung meteran dan mencatat). Sore bisa sendiri.
- [ ] Tanyakan ke lab apakah ada **meteran laser**. Kalau tidak ada, bawa meteran pita ≥ 5 m.
- [ ] Minta **denah lantai 10** ke pengelola gedung atau lab (dipakai untuk anchoring dan penyelarasan peta, prosesnya lama).
- [ ] Ponsel:
  - [ ] Baterai penuh, bawa powerbank. Kosongkan memori untuk beberapa video 4K dan ±60 foto.
  - [ ] **Video:** stabilisasi video **dimatikan**, HDR video mati, 1080p atau 4K, 30 fps, lensa 1x.
  - [ ] **Foto:** format JPEG (iPhone: Pengaturan, Kamera, Format, "Most Compatible"). Matikan Live
        Photo, mode malam, mode potret, dan kontrol makro (iPhone). Lensa **1x**.
  - [ ] Catat merek, tipe ponsel, dan pengaturan kamera. Masuk ke laporan.
- [ ] Siapkan: selotip kertas, spidol, 20 label kertas `P01` sampai `P20`, dan formulir di bagian
      akhir dokumen ini (cetak atau salin ke catatan ponsel).

## Pagi (±07.00 sampai 09.30, area sepi)

### 1. Titik asal dan sumbu (10 menit)

1. Pilih **titik asal** yang mudah ditemukan lagi, misalnya sudut kusen pintu lab.
2. **Sumbu x** sepanjang satu dinding, **sumbu y** sepanjang dinding yang tegak lurus dengannya.
3. Kalau lantainya keramik berukuran seragam, **ukur satu keramik dengan teliti**. Posisi titik bisa
   dihitung dari jumlah keramik, lebih cepat daripada menarik meteran ke tengah ruangan.
4. Catat deskripsi titik asal, arah sumbu, dan ukuran keramik di formulir.

### 2. Menandai dan mengukur 20 titik (30 sampai 45 menit)

1. **Ruang terbuka:** sebar titik merata di seluruh ruangan, termasuk dekat pintu lab dan setiap
   jalan masuk. **Lorong:** tempel zig-zag, bergantian dekat kedua dinding (±0,4 m dari dinding),
   berjarak ±1,5 sampai 2 m. **Jangan di satu garis lurus.**
2. Tempel label `P01` sampai `P20` di samping titik, bukan menutupi titiknya.
3. Ukur `x` dan `y` dari titik asal. Teman membaca, kamu mencatat, lalu **baca ulang sekali** untuk
   mencegah salah tulis.
4. Satuan meter, dua desimal. Catat alat ukur yang dipakai.

### 3. Rekam video peta (±15 sampai 30 menit)

**Pola yang terbukti paling baik (uji 2026-10-01): keliling, menghadap ke dalam.** Satu video,
berjalan pelan mengelilingi tepi area sampai kembali ke titik awal, **punggung ke dinding dan kamera
menghadap ke tengah ruangan**. Di lantai 10 pola ini menghasilkan satu peta utuh (401/402 frame)
dan 78% foto uji dari hari lain diterima, dibanding peta pecah 3 dengan jalur ular di bawah.
Rinciannya di `docs/spike-plan.md`, "Uji video lantai 10, percobaan kedua". Aturan belok di bawah
tetap berlaku di sudut ruangan. Kalau ada tujuan penting di dinding belakang (misalnya pintu lab),
tambahkan rekaman pendek menghadap tujuan itu.

**Cara A, video jalur ular (pola awal).** Dua video per area.

**Video 1**
1. Berdiri di jalan masuk. Pegang ponsel **mendatar** dengan dua tangan, setinggi dada, kamera ke
   depan dan sedikit menunduk dari garis horizon.
2. Tekan rekam, lalu jalan pelan (±setengah kecepatan jalan biasa) **berkelok seperti ular**: ke ujung
   ruangan, geser ±2 langkah (1,5 sampai 2 m), balik arah, geser lagi, sampai seluruh area terlewati.
3. Kamera **selalu menghadap ke arah jalan**. Di belokan, putar badan pelan-pelan bersama ponsel,
   jangan hanya pergelangan tangan.
4. Sampai di ujung, berhenti merekam.

**Aturan belok dan putar balik** (dari uji 2026-09-30: peta pecah jadi 3 potongan tepat di titik-titik
ini, rincian di `docs/spike-plan.md`):
- **Putar balik 2 sampai 3 m sebelum dinding.** Jangan berjalan sampai dekat tembok. Berputar sambil
  kamera tetap menghadap ruangan.
- **Belok pelan:** sekitar 90° dalam 3 sampai 4 detik. Kalau terasa terlalu lambat, berarti sudah benar.
- **Jangan arahkan kamera ke dinding polos** lebih dari sekejap. Frame dinding putih tidak punya fitur,
  dan peta putus di sana. Arahkan ke bagian yang ada pintu, papan, lift, atau panel.
- **Masuk atau keluar area jendela kaca: diam 1 sampai 2 detik** supaya eksposur kamera sempat
  menyesuaikan. Tanpa jeda, frame di perpindahan terang-gelap jadi gelap atau buram.

**Video 2**
1. Dari tempat Video 1 berakhir, tekan rekam.
2. **Ulangi jalur yang sama ke arah sebaliknya** sampai kembali ke jalan masuk, lalu berhenti.

**Lorong** diperlakukan sama: Video 1 pergi di satu sisi lorong, Video 2 pulang di sisi lain. Di
lorong, Video 2 **wajib**, karena tanpa itu lorong hanya terlihat dari satu arah.

Frame dipilih nanti oleh `spike/extract_frames.py` (±2 frame per detik, yang paling tajam).

**Cara B, foto satu per satu (cadangan).** Dipakai kalau video bermasalah, misalnya stabilisasi tidak
bisa dimatikan atau gladi kamar dengan video gagal. Jalurnya sama, tapi **satu foto setiap satu
langkah** (±0,5 m), lanskap, jangan berputar di tempat.

**Untuk kedua cara:**
- **Tunggu orang lewat.** Kalau ada orang di tengah bingkai, ulangi bagian itu.
- Selotip titik boleh terlihat, tidak masalah.

### 4. Cek cepat sebelum pulang (5 menit)

- [ ] Kedua video terekam utuh. Putar acak beberapa detik: tidak buram, tidak gelap.
- [ ] Putar bagian belokan dan putar balik: tidak ada detik yang hanya berisi dinding polos.
- [ ] **Selotip jangan dicopot**, masih dipakai sore.

## Siang atau sore (±13.00 sampai 15.00): foto uji

Minimal 4 jam setelah video peta, supaya cahaya berbeda. Pakai **mode foto biasa**.

1. Di setiap titik, berdiri dengan **ujung kaki di titik**, ponsel setinggi dada.
2. Sebelum memotret, **foto label titiknya** sekali (penanda urutan, dibuang nanti).
3. Ambil **2 foto ke arah berbeda**: `a` mendatar (lanskap), `b` tegak (potret). Arahkan ke area
   ruangan, jangan ke dinding polos dari dekat.
4. Catat nomor file pertama di formulir (misalnya `IMG_4521`), supaya penamaan ulang nanti
   tidak tertukar.
5. Setelah P20 selesai, **copot semua selotip**, lalu periksa lantainya bersih.

Total: 20 titik x 2 = **40 foto uji**.

## Setelah dari lapangan

1. **Salin semua video dan foto** ke laptop dan buat cadangan ke folder Google Drive pribadi.
   **Salin, jangan pindahkan (cut):** video mentah di laptop dipakai lagi kalau frame perlu
   diekstrak ulang dengan setelan lain (2026-09-30: video hilang dari laptop, ekstraksi 4 fps batal).
2. **Susun folder** (di luar git):
   ```text
   data/floor10/
   ├── video1.mp4, video2.mp4   ← video peta (nama bebas)
   ├── mapping/                 ← dibiarkan kosong, diisi extract_frames.py
   ├── query/                   ← foto uji: P01_a.jpg, P01_b.jpg, ...; foto label dibuang
   └── reference_points.csv                ← dari formulir: point,x_m,y_m
   ```
3. Salin `data/floor10` ke PC lab, lalu jalankan di `C:\Users\<user>\eutopos-vps`:
   ```powershell
   git switch main; git pull
   .venv\Scripts\python.exe spike\extract_frames.py data\floor10\video1.mp4 data\floor10\video2.mp4 --out data\floor10\mapping
   .venv\Scripts\python.exe spike\fix_orientation.py data\floor10 data\floor10-upright
   .venv\Scripts\python.exe spike\run.py data\floor10-upright --out outputs\floor10 --global-resize 512
   .venv\Scripts\python.exe spike\inspect_map.py outputs\floor10\kp1024-r1024
   .venv\Scripts\python.exe spike\eval_meter.py outputs\floor10\kp1024-r1024\results.csv data\floor10-upright\reference_points.csv
   .venv\Scripts\python.exe spike\bench_localize.py data\floor10-upright --map outputs\floor10 --global-resize 512 --device cuda
   .venv\Scripts\python.exe spike\bench_localize.py data\floor10-upright --map outputs\floor10 --global-resize 512 --device cpu --threads 2
   ```
   Kalau memakai cara B (foto), lewati baris `extract_frames.py` dan taruh fotonya langsung di
   `mapping/`.
4. Tempel keluaran `extract_frames.py` dan ringkasan JSON dari keempat perintah terakhir ke sesi.
   Varian lain (keypoint 512, resize ALIKED lebih kecil) dijalankan setelah hasil pertama dibaca.

**Tanda hari ini berhasil** (bukan ambang spike, hanya tanda datanya layak dipakai):
- `map_registered` ≥ 90% dari jumlah frame peta.
- `inspect_map.py` hanya menampilkan potongan "utama". Potongan lain berarti peta putus: buka frame di
  nomor putusnya (nomor / 2 = detik ke-).
- `eval_meter.py` berjalan tanpa peringatan titik segaris.

## Kalau ada masalah di lapangan

| Masalah | Tindakan |
|---|---|
| Area ramai | Tunggu, atau kerjakan bagian yang sepi dulu. Jangan merekam dengan orang di tengah bingkai |
| Baterai atau memori hampir habis | Powerbank. Pindahkan video ke laptop di tengah sesi |
| Video buram di beberapa bagian | Rekam ulang video itu dengan jalan lebih pelan |
| Peta pecah jadi beberapa potongan | Biasanya belokan terlalu cepat atau kamera menghadap dinding polos. Rekam ulang bagian itu mengikuti aturan belok |
| Stabilisasi video tidak bisa dimatikan | Pakai cara B (foto satu per satu) |
| Salah catat ukuran | Ukur ulang titik itu. Selotip masih terpasang sampai sore |
| Lupa urutan foto uji | Foto label titik yang diambil sebelum tiap pasangan dipakai sebagai penanda |
| Waktu habis | Prioritas: titik acuan dan video peta lengkap. Foto uji bisa diambil hari lain (selotip dibiarkan hanya kalau diizinkan lab) |

## Privasi

- Video, foto gedung, `reference_points.csv`, dan koordinat titik **tidak pernah masuk git**. Folder `data/`
  sudah di-gitignore.
- Foto yang memuat wajah orang tidak dipakai di laporan tanpa disamarkan.

## Formulir lapangan

Ponsel: ______________ | Alat ukur: ______________ | Pencatat: ______________

Titik asal: ______________________________ | Arah x: ______________ | Ukuran keramik: ______ cm

| Titik | x_m | y_m | File foto uji pertama | Catatan |
|---|---|---|---|---|
| P01 | | | | |
| P02 | | | | |
| P03 | | | | |
| P04 | | | | |
| P05 | | | | |
| P06 | | | | |
| P07 | | | | |
| P08 | | | | |
| P09 | | | | |
| P10 | | | | |
| P11 | | | | |
| P12 | | | | |
| P13 | | | | |
| P14 | | | | |
| P15 | | | | |
| P16 | | | | |
| P17 | | | | |
| P18 | | | | |
| P19 | | | | |
| P20 | | | | |

Jam video peta: ______ sampai ______ | Jam foto uji: ______ sampai ______ | Cuaca/cahaya: ______
