# Penyelarasan cepat: skala dari jarak diketahui (desain)

Status: draf, menunggu persetujuan Bagus. Tanggal: 2026-11-19. Belum dikerjakan.

Latar: `docs/map-quality-verification-research.md` (bagian skala). Keputusan Bagus 2026-11-19: developer cukup
merekam dengan sedikit penyesuaian dan navigasi tampil berjalan; titik meteran hanya untuk laporan PA.

## 1. Masalah

Peta baru tidak bisa dipakai navigasi tanpa penyelarasan (`align.json` atau baris `alignment` applied). Satu-satunya
jalur sekarang adalah kalibrasi titik (`server/calibration.py`, dashboard kalibrasi, `spike/eval_meter.py`): minimal
4 titik acuan yang diukur di lantai, tidak segaris, ditambah foto yang dilokalisasi di tiap titik. Itu beban terbesar
developer, dan menjadi syarat keras di `alignment.validate_align` (`reference_points >= 4`).

Vendor (MultiSet) cukup memakai satu panjang yang diketahui untuk skala. Arah gravitasi bisa diperkirakan dari
orientasi kamera. Arah utara dan titik asal boleh bebas untuk satu area.

## 2. Tujuan, bukan tujuan, anti-tujuan

Tujuan:
1. Satu versi peta bisa menjadi siap navigasi dengan **satu jarak yang diketahui** (dua jarak dianjurkan).
2. Kerangka hasilnya sama dengan kalibrasi titik: meter, sumbu Z ke atas, lantai di z=0, `phone_height_m` 1,3. Jadi
   Localizer, aplikasi, editor area, dan graf rute tidak berubah.
3. Kalibrasi titik (metode `survey`) tetap ada dan tetap menuntut minimal 4 titik, untuk laporan PA.
4. Dashboard menampilkan metode dan kualitas penyelarasan apa adanya, supaya peta "cepat" tidak terlihat setara
   dengan peta yang diukur.

Bukan tujuan:
- Penyelarasan ke denah gedung atau koordinat bersama antar-area (butuh titik acuan; tetap lewat `survey`).
- Skala dari pose ARCore (irisan 2 aplikasi capture, menunggu spike).
- Mengubah gerbang publish otomatis.

Anti-tujuan:
- Peta dengan skala salah besar tampil "siap navigasi" tanpa peringatan.
- Dua implementasi Sim3 atau dua format `align.json`.
- Metode cepat diam-diam menggantikan penyelarasan `survey` yang sudah diterapkan.

## 3. Cara developer memakainya

1. Saat merekam: di lorong lurus, **berhenti sekitar 2 detik** di titik A, jalan lurus, berhenti lagi di titik B.
   Jarak A ke B diketahui dari hitung ubin, meteran, atau laser. Makin panjang makin baik (anjuran minimal 10 m).
2. Di dashboard, halaman versi peta, bagian Penyelarasan, pilih "Jarak diketahui":
   - pilih frame A dan frame B dari deretan foto kecil (thumbnail frame yang sudah ada),
   - isi jaraknya dalam meter,
   - opsional: pasangan kedua (C ke D) untuk memeriksa drift skala.
3. Tekan Hitung: tampil skala, sudut kemiringan sisa, dan (bila dua pasangan) selisih skala antar-pasangan.
4. Tekan Terapkan: tersimpan sebagai baris `alignment` applied, berlaku tanpa restart (jalur `DbAlign` yang ada).

## 4. Perhitungan (fungsi murni, satu tempat)

Masukan: pusat kamera dan orientasi semua frame terdaftar di model SfM, dan satu atau dua pasangan
`(frame_a, frame_b, jarak_m)`.

1. **Gravitasi.** Arah atas dunia ditaksir dari orientasi kamera: rata-rata vektor "atas gambar" (-y kamera COLMAP)
   semua frame terdaftar, dengan asumsi ponsel dipegang tegak. Catat sebaran sudutnya sebagai kualitas.
   Ini setara metode `IMAGE-ORIENTATION` COLMAP (`model_orientation_aligner`), ditulis ulang karena tidak terekspos
   di pycolmap.
2. **Skala.** `s = jarak_m / jarak_horizontal_model(A, B)`, jarak diukur pada bidang tegak lurus gravitasi.
   Bila dua pasangan: skala akhir rata-rata keduanya, dan selisihnya dilaporkan.
3. **Arah dan asal.** Sumbu x mengikuti arah utama lintasan kamera (komponen utama posisi kamera di bidang lantai),
   asal di proyeksi lantai frame terdaftar pertama. Ketinggian: median tinggi kamera di atas lantai = 1,3 m.
4. Hasilnya `meter_from_model` (skala, rotasi, translasi) yang sama bentuknya dengan kalibrasi titik.

### 4b. Metode `arcore_pose` (ditambahkan 2026-11-19, setelah spike sesi 1)

Untuk peta dari aplikasi capture, setiap foto membawa pose ARCore dalam meter (`frames.jsonl`). Spike sesi 1 (job 23,
`spike-arcore`) menunjukkan pose ARCore cocok dengan pusat kamera SfM sampai median sekitar 10 cm setelah Sim3.

1. Cocokkan foto terdaftar di model utama dengan baris `frames.jsonl` lewat nama berkas.
2. Ubah posisi ARCore dari kerangka dunia Unity (kidal, Y ke atas) ke kerangka gedung (tangan kanan, Z ke atas):
   `(x_b, y_b, z_b) = (x_u, z_u, y_u)`. Lalu geser z supaya median tinggi kamera sama dengan `phone_height_m` (1,3),
   konvensi yang sama dengan kalibrasi titik.
3. `meter_from_model = sim3.fit(pusat kamera SfM, posisi ARCore di kerangka gedung, ransac)`. Gravitasi ikut benar
   karena ARCore mengukurnya; arah utara mengikuti yaw awal sesi ARCore (bebas per area).
4. Kualitas: jumlah foto yang cocok, residu median dan maksimum dalam meter.

Sumber galat yang harus ditampilkan, bukan disembunyikan:
- Pemilihan frame pada 2 fps meleset hingga sekitar 0,4 m per ujung saat berjalan. Karena itu developer diminta
  berhenti di A dan B; galat skala kira-kira (galat ujung) dibagi jarak.
- Ponsel yang tidak tegak menggeser gravitasi; sebaran sudut ditampilkan.

## 5. Format dan validasi

`align.json` dan `alignment.params` mendapat field `method`:
- `"survey"`: perilaku sekarang. Bila `method` tidak ada, dianggap `survey` (berkas lama tetap sah).
  Wajib `reference_points >= 4` dan `residual_median_m`.
- `"known_distance"`: wajib `known_distances` (1 atau 2 entri `{frame_a, frame_b, distance_m, model_distance}`),
  `gravity_spread_deg`, dan bila dua entri `scale_spread_percent`. Tidak wajib `reference_points`.
- `"arcore_pose"`: wajib `matched_frames` (bilangan bulat, minimal 10), `residual_median_m`, `residual_max_m`.
  Tidak wajib `reference_points`.

`validate_align` memeriksa per metode. `Localizer` hanya membaca `meter_from_model`, jadi tidak berubah.

Aturan penerapan: menerapkan `known_distance` pada versi yang sudah punya `survey` applied **ditolak** kecuali admin
mengonfirmasi eksplisit (supaya hasil ukur tidak tertimpa tanpa sengaja). Riwayat dan revert memakai tabel
`alignment` yang ada (`source = "known_distance"`).

## 6. Tampilan

- Lencana versi: "Siap navigasi" tetap diturunkan seperti sekarang, ditambah keterangan metode: "skala dari jarak
  diketahui" atau "diukur (N titik)".
- Kualitas yang ditampilkan: jarak yang dipakai, skala, sebaran gravitasi, selisih skala antar-pasangan.
- Peringatan (bukan penolakan) bila: hanya satu pasangan, jarak di bawah 10 m, sebaran gravitasi besar, atau
  selisih skala antar-pasangan besar. Ambang awal ditetapkan setelah dicoba pada data nyata, dicatat di rencana.

## 7. Pengujian

- Fungsi murni dengan data sintetis: lintasan dengan skala, rotasi, gravitasi miring, dan translasi diketahui harus
  kembali dengan galat mendekati nol; dua pasangan dengan skala berbeda melaporkan selisih yang benar.
- `validate_align`: berkas lama tanpa `method` tetap lolos; `known_distance` tanpa `known_distances` ditolak;
  `survey` dengan kurang dari 4 titik tetap ditolak.
- API: hitung tidak menyimpan; terapkan menyimpan satu baris applied; menimpa `survey` tanpa konfirmasi ditolak.
- Data nyata (PC lab, atas izin Bagus): job 22 `floor10-1080p` atau peta lain dengan dua frame yang jaraknya
  diketahui. Bila ada peta `survey` (misalnya `hcm-lantai-10` v1), bandingkan skala `known_distance` terhadap
  skala `survey` pada versi yang sama sebagai pembanding.

## 8. Keputusan Bagus

2026-11-19: Bagus meminta tiket untuk agen lain tanpa menjawab dua pertanyaan di bawah. Tiket memakai usulan
Claude sebagai bawaan; Bagus bisa membaliknya sebelum dikerjakan.

1. Cara memilih ujung jarak: **pilih dua frame dari rekaman** (bawaan tiket) atau klik dua titik di tampilan atas
   peta.
2. Menimpa penyelarasan `survey`: **ditolak kecuali konfirmasi eksplisit** (bawaan tiket: flag
   `--replace-survey` di CLI) atau dilarang sama sekali.

Urutan pengerjaan: tiket pertama hanya server dan CLI (fungsi murni, validator, perintah `manage`). Antarmuka
dashboard (pemilih frame, lencana metode) adalah tiket terpisah setelah angka nyata terlihat.

## 9. Pilihan Claude (tebakan, periksa)

- Gravitasi dari orientasi kamera dengan asumsi ponsel tegak.
- Sumbu x mengikuti arah utama lintasan; asal di frame pertama; tinggi kamera 1,3 m (sama dengan kalibrasi).
- Satu pasangan sudah cukup untuk terapkan; pasangan kedua hanya untuk peringatan drift.
- Tanpa migrasi Alembic (field baru ada di JSON `params`).
