# Runbook: Uji Lorong Lantai 10

Panduan kerja lapangan untuk uji coba awal di lorong lab lantai 10 gedung PENS pusat, **Selasa
29 September 2026**. Dasarnya `docs/spike-plan.md` (bagian 4.1, aturan memotret, dan protokol titik
acuan). Kalau ada yang bertentangan, `spike-plan.md` yang berlaku.

**Keluaran hari ini:** ±300 foto peta, 40 foto uji di 20 titik terukur, dan `titik.csv`. Semuanya
disimpan di luar git.

**Keputusan yang dipakai (2026-09-28):**
- Foto peta pagi, foto uji siang atau sore **di hari yang sama**, supaya pencahayaannya berbeda.
- **Satu ponsel** untuk peta dan foto uji. Uji lintas ponsel dilakukan belakangan.
- Meteran pita ditambah satu teman. Pakai meteran laser kalau lab punya.
- Foto disimpan di laptop, PC lab, dan folder Google Drive pribadi yang tidak dibagikan.

## H-1 (Senin): persiapan

- [ ] Ajak **satu teman** untuk pagi (memegang ujung meteran dan mencatat). Sore bisa sendiri.
- [ ] Tanyakan ke lab apakah ada **meteran laser**. Kalau tidak ada, bawa meteran pita ≥ 5 m.
- [ ] Minta **denah lantai 10** ke pengelola gedung atau lab (dipakai setelah ACC, tapi prosesnya lama).
- [ ] Ponsel:
  - [ ] Baterai penuh, bawa powerbank. Kosongkan memori untuk ±400 foto.
  - [ ] **Format JPEG.** iPhone: Pengaturan, Kamera, Format, "Most Compatible".
  - [ ] **Matikan:** Live Photo, mode malam, mode potret, HDR otomatis kalau bisa, penyesuaian
        adegan otomatis atau AI, dan kontrol makro (iPhone). Lensa **1x**, jangan ganti lensa.
  - [ ] Catat merek, tipe ponsel, dan pengaturan kamera. Masuk ke laporan.
- [ ] Siapkan: selotip kertas, spidol, 20 label kertas `P01` sampai `P20`, dan formulir di bagian
      akhir dokumen ini (cetak atau salin ke catatan ponsel).

## Pagi (±07.00 sampai 09.30, lorong sepi)

### 1. Titik asal dan sumbu (10 menit)

1. Pilih **titik asal** yang mudah ditemukan lagi, misalnya sudut kusen pintu lab di ujung lorong.
2. **Sumbu x** sepanjang lorong, **sumbu y** melintang, diukur dari **dinding kiri** (y = 0 di
   dinding kiri kalau menghadap arah x positif).
3. Catat deskripsi titik asal dan arah sumbu di formulir.

### 2. Menandai dan mengukur 20 titik (30 sampai 45 menit)

1. Tempel titik **zig-zag**: bergantian dekat dinding kiri (y ±0,4 m) dan dekat dinding kanan (lebar
   lorong dikurangi ±0,4 m), berjarak ±1,5 sampai 2 m sepanjang lorong. **Jangan di satu garis
   tengah.**
2. Tempel label `P01` sampai `P20` di samping titik, bukan menutupi titiknya.
3. Ukur `x` (dari titik asal sepanjang lorong) dan `y` (dari dinding kiri). Teman membaca, kamu
   mencatat, lalu **baca ulang sekali** untuk mencegah salah tulis.
4. Satuan meter, dua desimal. Catat alat ukur yang dipakai.

### 3. Foto peta (45 sampai 60 menit, ±300 foto)

Aturan: **semua lanskap**, lensa 1x, **melangkah setiap satu foto** (±0,5 m), jangan berputar di
tempat. Setiap benda harus terlihat di minimal 3 foto.

| Putaran | Posisi berjalan | Arah kamera |
|---|---|---|
| 1 | Sepertiga kiri lorong, dari titik asal ke ujung | Ke depan (searah jalan) |
| 2 | Sepertiga kanan lorong, kembali ke titik asal | Ke depan (searah jalan) |
| 3 | Tengah lorong, dari titik asal ke ujung | Serong ke dinding kiri (±45°) |
| 4 | Tengah lorong, kembali ke titik asal | Serong ke dinding kanan (±45°) |

- Di depan pintu, papan nama, atau belokan, ambil 2 sampai 3 foto tambahan dari posisi sedikit
  berbeda.
- **Tunggu orang lewat.** Kalau ada orang di foto, ulangi foto itu.
- Selotip titik boleh terlihat di foto peta, tidak masalah.

### 4. Cek cepat sebelum pulang (5 menit)

- [ ] Jumlah foto sesuai perkiraan. Buka acak 10 foto: tidak buram, tidak gelap.
- [ ] Format JPG (lihat info foto).
- [ ] **Selotip jangan dicopot**, masih dipakai sore.

## Siang atau sore (±13.00 sampai 15.00): foto uji

Minimal 4 jam setelah foto peta, supaya cahaya berbeda.

1. Di setiap titik, berdiri dengan **ujung kaki di titik**, ponsel setinggi dada.
2. Sebelum memotret, **foto label titiknya** sekali (penanda urutan, dibuang nanti).
3. Ambil **2 foto ke arah berbeda**: `a` lanskap, `b` potret. Arahkan ke area lorong, jangan ke
   dinding polos dari dekat.
4. Catat nomor file pertama di formulir (misalnya `IMG_4521`), supaya penamaan ulang nanti
   tidak tertukar.
5. Setelah P20 selesai, **copot semua selotip**, lalu periksa lantainya bersih.

Total: 20 titik x 2 = **40 foto uji**.

## Setelah dari lapangan

1. **Salin semua foto** ke laptop dan buat cadangan ke folder Google Drive pribadi.
2. **Susun folder** (di luar git):
   ```text
   data/lantai10/
   ├── mapping/    ← semua foto peta
   ├── query/      ← foto uji dengan nama P01_a.jpg, P01_b.jpg, ...; foto label dibuang
   └── titik.csv   ← dari formulir: titik,x_m,y_m
   ```
3. Salin `data/lantai10` ke PC lab, lalu jalankan di `C:\Users\<user>\eutopos-vps`:
   ```powershell
   git switch main; git pull
   .venv\Scripts\python.exe spike\tegakkan.py data\lantai10 data\lantai10-tegak
   .venv\Scripts\python.exe spike\run.py data\lantai10-tegak --out outputs\lantai10 --global-resize 512
   .venv\Scripts\python.exe spike\eval_meter.py outputs\lantai10\kp1024-r1024\results.csv data\lantai10-tegak\titik.csv
   .venv\Scripts\python.exe spike\bench_localize.py data\lantai10-tegak --map outputs\lantai10 --global-resize 512 --device cuda
   .venv\Scripts\python.exe spike\bench_localize.py data\lantai10-tegak --map outputs\lantai10 --global-resize 512 --device cpu --threads 2
   ```
4. Tempel ringkasan JSON dari keempat perintah terakhir ke sesi. Varian lain (keypoint 512, resize
   ALIKED lebih kecil) dijalankan setelah hasil pertama dibaca.

**Tanda hari ini berhasil** (bukan ambang spike, hanya tanda datanya layak dipakai):
- `map_registered` ≥ 90% dari jumlah foto peta.
- `eval_meter.py` berjalan tanpa peringatan titik segaris.

## Kalau ada masalah di lapangan

| Masalah | Tindakan |
|---|---|
| Lorong ramai | Tunggu, atau kerjakan bagian lorong yang sepi dulu. Jangan memotret dengan orang di tengah bingkai |
| Baterai atau memori hampir habis | Powerbank. Pindahkan foto ke laptop di tengah sesi |
| Salah catat ukuran | Ukur ulang titik itu. Selotip masih terpasang sampai sore |
| Lupa urutan foto uji | Foto label titik yang diambil sebelum tiap pasangan dipakai sebagai penanda |
| Waktu habis | Prioritas: titik acuan dan foto peta lengkap. Foto uji bisa diambil hari lain (selotip dibiarkan hanya kalau diizinkan lab) |

## Privasi

- Foto gedung, `titik.csv`, dan koordinat titik **tidak pernah masuk git**. Folder `data/` sudah
  di-gitignore.
- Foto yang memuat wajah orang tidak dipakai di laporan tanpa disamarkan.

## Formulir lapangan

Ponsel: ______________ | Alat ukur: ______________ | Pencatat: ______________

Titik asal: ______________________________ | Arah x: ______________ | Lebar lorong: ______ m

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

Jam foto peta: ______ sampai ______ | Jam foto uji: ______ sampai ______ | Cuaca/cahaya: ______
