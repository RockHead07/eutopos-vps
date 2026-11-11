# Pemangkasan SOG (Splat Prune)

Dokumen ini menjelaskan modul pemangkas SOG (`spike/splat_prune.py`) untuk memangkas Gaussian dari arsip SOG v2 tanpa kuantisasi ulang.

## 1. Metode

Modul ini memangkas Gaussian langsung dari berkas kontainer SOG v2 (zip) tanpa melakukan kuantisasi ulang:
- Data Gaussian yang dipertahankan disalin bit demi bit dari tekstur masukan (`means_l`, `means_u`, `quats`, `scales`, `sh0`).
- Urutan baris (row-major) tetap dipertahankan.
- Dimensi lebar tekstur tetap sama, tinggi baru dihitung menggunakan pembulatan ke atas: `ceil(n2 / width)`.
- Sisa piksel pada baris terakhir diisi dengan nilai nol (padding transparan).
- Metadata `meta.json` diperbarui nilai `count`-nya ke jumlah Gaussian yang bertahan (`n2`).
- Penulisan berkas dilakukan secara atomik: ditulis ke berkas sementara di folder tujuan, lalu diganti menggunakan `os.replace` agar berkas setengah jadi tidak pernah terlihat oleh proses lain.

## 2. Alasan Memilih Pasca-Pangkas pada SOG

Pendekatan pasca-pangkas pada berkas SOG dipilih dibandingkan filter `-V` pada `splat-transform`:
1. Data yang dipertahankan identik bit demi bit dengan hasil kompresi asli tanpa degradasi tambahan atau perubahan kuantisasi ulang.
2. Ambang batas `-V` opacity pada berkas PLY mentah tidak setara persis dengan `alpha-byte <= 5` pada tekstur WebP kuantisasi SOG, sehingga membutuhkan kalibrasi dan verifikasi tersendiri.
3. Operasi pemangkasan pada SOG sangat ringan dan cepat (hanya operasi larik numpy dan kompresi WebP lossless murni tanpa proses pelatihan atau konversi PLY berulang).

## 3. Hasil Pengukuran dan Penentuan Standar (L1)

Sumber data: diukur Claude 8 Nov 2026 pada `scene.sog` 901.798 Gaussian, tanpa SH, di PlayCanvas 2.23.3 pada tujuh pose latih; kriteria dikunci sebelum hasil.

| Varian | Aturan | Gaussian dibuang | Ukuran berkas | PSNR terburuk vs asli | Selisih vs foto (dB) | Kriteria terkunci |
|---|---|---|---|---|---|---|
| L0 | alpha == 0 | 10,6% | -8,6% | 99 (identik) | 0 | lulus |
| L1 | opasitas < 0,02 | 23,8% | -22,0% (10.314.918 menjadi 8.041.393 B) | 45,27 | -0,046 | lulus |
| L2 | opasitas < 0,05 | 31,4% | -30,1% | 34,32 | -0,303 | gagal |
| L3 | opasitas < 0,1 | 37,9% | -37,2% | 29,49 | -0,819 | gagal |

Berdasarkan keputusan Bagus (8 Nov 2026), L1 (`opasitas < 0.02` atau `alpha-byte <= 5`) dipilih sebagai nilai bawaan (`DEFAULT_MIN_OPACITY = 0.02`).

## 4. Batasan

Batasan yang diketahui dan harus diperhatikan:
- Hanya diuji pada tujuh pose latih (interpolasi, bersifat optimistis).
- Tanpa pita SH (hanya SH0 atau `-H 0`).
- Evaluasi menggunakan render perangkat lunak.
- FPS pada GPU nyata tidak diukur.
- Penilaian visual Bagus menyatakan L3 masih cukup bagus, tetapi L1 dipilih sebagai bawaan karena lulus kriteria toleransi PSNR dan selisih foto.
