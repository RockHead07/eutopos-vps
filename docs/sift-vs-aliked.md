# SIFT vs ALIKED: cara kerja, perbedaan, dan hasil di data lantai 10

Disusun 2026-10-05 atas permintaan pembimbing ("deep dive cara kerja ALIKED sama SIFT perbedaannya apa, pakai
tabel"). Setiap angka berasal dari salah satu sumber ini:

- **[Lowe]** D. G. Lowe, "Distinctive image features from scale-invariant keypoints," *IJCV* 60(2), 2004
  (dibaca langsung dari PDF-nya).
- **[ALIKED]** X. Zhao dkk., "ALIKED: A lighter keypoint and descriptor extraction network via deformable
  transformation," *IEEE TIM* 72, 2023 (dibaca dari PDF-nya).
- **[LG]** P. Lindenberger dkk., "LightGlue: Local feature matching at light speed," *ICCV* 2023 (dibaca dari
  PDF-nya).
- **[data]** pengukuran kita di lorong lantai 10 (`docs/spike-plan.md`).

## 1. Jawaban singkat

1. **Cara kerjanya beda.** SIFT hand-crafted: dirancang manual dengan rumus (deteksi lewat Difference of Gaussian,
   descriptor dari histogram arah gradient). ALIKED learned: neural network yang dilatih dari banyak pasangan
   gambar (deteksi lewat score map yang bisa dilatih, descriptor dari titik-titik sampel yang posisinya ikut
   dipelajari).
2. **Temuan penting dari data kita: di lorong lantai 10, yang menentukan hasil adalah matcher-nya, bukan
   feature-nya.** Dengan nearest neighbor + ratio test, SIFT maupun ALIKED sama-sama gagal (peta pecah jadi 6
   bagian, 0 dari 46 foto uji). Dengan LightGlue keduanya berhasil sama persis (401 dari 402 frame masuk satu
   peta, 36 dari 46 foto uji, dan **36 foto yang sama**).
3. **Setelah matcher-nya disamakan**, bedanya ALIKED dari SIFT lebih halus: pada pasangan frame yang viewpoint-nya
   sudah bergeser, ALIKED menemukan lebih banyak match, dan extraction-nya jauh lebih cepat (dengan catatan di
   bagian 6). Di data ini selisih itu belum cukup besar untuk mengubah hasil akhir.

## 2. Alur feature matching (tiga tahap)

Semua metode local feature mengerjakan tiga hal. Yang berbeda adalah cara tiap tahap dikerjakan.

| Tahap | Pertanyaan yang dijawab | COLMAP + SIFT | Pipeline eutopos |
|---|---|---|---|
| 1. Detection | Titik mana di gambar yang khas dan bisa ditemukan lagi? | Puncak Difference of Gaussian | ALIKED (score map) |
| 2. Description | Seperti apa "sidik jari" tiap titik? | Histogram arah gradient, 128 angka | ALIKED (128 angka) |
| 3. Matching | Titik mana di gambar A sama dengan titik mana di gambar B? | Nearest neighbor + ratio test | LightGlue |

Hasil matching dipakai COLMAP untuk membangun peta 3D (reconstruction) dan untuk menghitung posisi foto uji (PnP).

## 3. SIFT, langkah demi langkah [Lowe]

| Langkah | Yang dilakukan | Angka dari makalah |
|---|---|---|
| 1. Scale space | Gambar di-blur Gaussian bertahap, lalu gambar yang berdekatan dikurangkan (Difference of Gaussian, DoG). Tiap octave ukurannya setengah dari sebelumnya | Blur awal sigma = 1,6. Gambar masukan digandakan dulu. 3 skala per octave (k = 2^(1/3)) |
| 2. Cari extrema | Tiap titik dibandingkan dengan 26 tetangganya (8 di skala yang sama, 9 di atas, 9 di bawah). Hanya maksimum atau minimum yang lolos | 26 tetangga |
| 3. Filtering | Posisi dihaluskan dengan fungsi kuadrat. Titik ber-contrast rendah dibuang (rentan noise). Titik di sepanjang edge dibuang (posisinya tidak pasti) | Contrast < 0,03 dibuang. Rasio principal curvature > 10 dibuang. Contoh di makalah: 832 titik jadi 729, lalu 536 |
| 4. Orientation | Orientation histogram dari arah gradient di sekitar titik. Puncak tertinggi jadi arah titik, supaya tahan terhadap rotasi | 36 bin (10 derajat per bin). Puncak lain yang mencapai 80% ikut jadi keypoint baru (sekitar 15% titik punya lebih dari satu orientation) |
| 5. Descriptor | Area 16 x 16 di sekitar titik (diputar sesuai orientation-nya) dibagi 4 x 4 sel, tiap sel punya histogram 8 arah | 4 x 4 x 8 = **128 angka**. Dinormalisasi, nilai di atas 0,2 di-clip, lalu dinormalisasi lagi (tahan terhadap perubahan cahaya) |
| 6. Matching | Tiap titik dicari nearest neighbor-nya (jarak Euclidean). Pasangan dibuang kalau jarak ke nearest neighbor lebih dari 0,8 kali jarak ke neighbor kedua (ratio test) | Rasio 0,8 membuang 90% pasangan salah dan kurang dari 5% pasangan benar |

**Kelebihan SIFT:** terbukti puluhan tahun, tidak butuh data latih, perilakunya bisa dijelaskan rumus demi rumus.
**Batas yang diakui penulisnya:** tahan terhadap skala dan rotasi, tapi "tidak sepenuhnya affine invariant". Pada
permukaan datar yang dimiringkan, persentase titik yang descriptor-nya masih menemukan pasangan benar turun dari
sekitar 85% (tanpa kemiringan) jadi sekitar 50% pada kemiringan 50 derajat (dibaca dari grafik Gambar 9 [Lowe],
jadi angkanya perkiraan).

**SIFT di COLMAP (yang kita uji)**, dibaca dari pycolmap 4.2: gambar diperbesar dulu (`first_octave` = -1),
`peak_threshold` = 0,0067 (lebih longgar dari 0,01 bawaan hloc), `edge_threshold` = 10, 4 octave, 3 skala per
octave, maksimum 2 orientation per titik, maksimum 8.192 fitur, dan descriptor **RootSIFT** (normalisasi
`L1_ROOT`, Arandjelović dan Zisserman, 2012).

## 4. ALIKED, langkah demi langkah [ALIKED]

ALIKED adalah neural network kecil dengan tiga bagian, ditambah satu head khusus untuk descriptor.

| Bagian | Yang dilakukan | Rincian dari makalah |
|---|---|---|
| 1. Feature encoding | Empat blok konvolusi mengubah gambar jadi feature di berbagai skala | Blok 1: dua konvolusi 3x3. Blok 2: pooling 2x2 + konvolusi. Blok 3 dan 4: pooling 4x4 + konvolusi **deformable** 3x3. Aktivasi SELU |
| 2. Feature aggregation | Feature semua skala di-upsample ke resolusi gambar lalu digabung | Empat blok "ublock" (konvolusi 1x1 + upsample), lalu di-concatenate |
| 3. Score Map Head (SMH) | Menghasilkan score map: seberapa layak tiap piksel jadi keypoint | Konvolusi 1x1 ke 8 channel, dua konvolusi 3x3, satu konvolusi 3x3 lagi, lalu sigmoid |
| 4. Differentiable Keypoint Detection (DKD) | Mengambil puncak dari score map | Non-maximum suppression (NMS) radius 2 piksel, threshold skor, lalu *softargmax* pada patch lokal untuk posisi sub-pixel. Seluruhnya **differentiable**, jadi bisa dilatih langsung dari reprojection error |
| 5. Sparse Deformable Descriptor Head (SDDH) | Untuk **tiap keypoint saja** (bukan seluruh gambar), network memilih M posisi sampel yang bentuknya dipelajari, mengambil feature di posisi itu, lalu menggabungkannya jadi descriptor | M posisi sampel. Descriptor 128 angka pada varian Normal |

**Ide intinya.** SIFT memodelkan perubahan viewpoint lokal dengan transformasi affine (6 degrees of freedom). ALIKED
memodelkannya dengan **offset bebas per piksel** di sekitar keypoint, yang degrees of freedom-nya sebanyak piksel di
patch itu [ALIKED]. Posisi sampel yang bergeser menyesuaikan bentuk lokal, dan komputasinya hanya di keypoint yang
terdeteksi sehingga hemat.

**Cara dilatih.** Dengan empat loss: reprojection loss (keypoint harus jatuh di tempat yang benar saat gambar
di-warp ke gambar lain), dispersity peak loss (memusatkan skor di puncak), sparse neural reprojection error loss
(descriptor titik yang sama harus mirip), dan reliable loss (keandalan skor). Data latihnya pasangan gambar dari
MegaDepth (foto wisata dengan pose dari COLMAP) dan pasangan homography sintetis, 100 ribu langkah.

**Arti nama varian.** `ALIKED-N(16)` = network Normal (channel 16, 32, 64, 128) dengan M = 16 posisi sampel. Itu yang
kita pakai (`aliked-n16` di hloc). Hasil di makalah (HPatches, 640 x 480, 1.000 keypoint, GPU RTX 2060):
0,677 juta parameter, 4,05 GFLOPs, 77 gambar per detik.

**Pengaturan kita:** detection threshold 0,2, NMS 2 piksel, maksimum 1.024 keypoint per gambar, gambar di-resize ke
1.024 piksel sisi panjang. Rata-rata yang benar-benar muncul: 632 keypoint per gambar (data kita).

## 5. Matcher: nearest neighbor vs LightGlue

| | Nearest neighbor + ratio test (`NN-ratio` di hloc) | LightGlue [LG] |
|---|---|---|
| Cara kerja | Tiap titik dicocokkan sendiri-sendiri ke titik yang descriptor-nya paling mirip, lalu dicek | Transformer yang melihat **semua keypoint di kedua gambar sekaligus** |
| Konteks | Tidak ada. Titik dinilai sendirian | Self-attention dan cross-attention antar titik, dengan rotary positional encoding (posisi relatif) |
| Penolakan | Ratio test 0,8 + mutual check (pengaturan kita) | Tiap titik dapat skor matchability; titik tanpa pasangan dibuang |
| Match akhir | Pasangan yang lolos pengecekan | Pasangan dengan skor tertinggi di barisnya dan di kolomnya, di atas threshold |
| Kecepatan | Sangat cepat | Adaptif: layer dihentikan lebih awal untuk pasangan yang mudah (adaptive depth), titik yang pasti tidak cocok dibuang (adaptive width) |
| Training | Tanpa training | Pre-train di 1 juta gambar homography sintetis, lalu fine-tune di MegaDepth |
| Feature yang didukung | Feature apa pun | SuperPoint, DISK, ALIKED, SIFT (bobot terpisah per jenis) |

## 6. Hasil kita: feature vs matcher (uji 2 x 2) [data]

Data: video keliling lorong lantai 10, 402 frame untuk peta, 46 foto uji dari hari lain. Semua tahap selain feature
dan matcher sama dengan layanan (pasangan MegaLoc 512 ditambah 10 frame berurutan). 1.024 keypoint pada 1.024 piksel.
Dijalankan di PC lab.

| Feature | Matcher | Frame di peta utama | Titik 3D | Bagian peta | Foto uji diterima (>= 50 inlier) | Median inlier |
|---|---|---|---|---|---|---|
| SIFT | nearest neighbor + ratio test | 135 / 402 | 4.945 | 6 | **0 / 46** | 0 |
| ALIKED | nearest neighbor + ratio test | 131 / 402 | 3.088 | 6 | **0 / 46** | 0 |
| SIFT | LightGlue | **401 / 402** | 23.645 | **1** | **36 / 46** | 244 |
| ALIKED | LightGlue | **401 / 402** | 24.615 | **1** | **36 / 46** | 220 |

**Kesimpulan dari tabel:**
1. Mengganti matcher dari nearest neighbor + ratio test ke LightGlue mengubah hasil dari gagal total jadi 78% untuk
   **kedua** feature, dan peta dari 6 bagian jadi 1.
2. Dengan matcher yang sama, SIFT dan ALIKED hasil akhirnya sama di data ini, termasuk **36 foto uji yang sama
   persis**.

**Jumlah match antar-frame (median):**

| Feature + matcher | Frame berjarak 0,5 detik | Frame berjarak 5 detik | Pasangan 5 detik dengan < 15 match |
|---|---|---|---|
| SIFT + nearest neighbor | 276 | 67 | 58 |
| ALIKED + nearest neighbor | 251 | 43 | 89 |
| SIFT + LightGlue | 358 | 151 | 34 |
| ALIKED + LightGlue | 443 | 201 | 14 |

Nearest neighbor + ratio test runtuh pada frame yang berjarak 5 detik (viewpoint sudah bergeser): pasangan di bawah
15 match mencapai 58 sampai 89. LightGlue menekannya jadi 14 sampai 34, dan ALIKED + LightGlue paling baik.

**Waktu (GPU PC lab):**

| Feature | Extraction 402 gambar peta | Catatan |
|---|---|---|
| ALIKED | 17 detik | Di GPU |
| SIFT (pycolmap) | 110 detik | **Di CPU**: pycolmap yang terpasang tidak punya CUDA (`has_cuda` = False) |

Jadi selisih waktu ini menggambarkan CPU vs GPU di instalasi kita, **bukan** perbedaan intrinsik kedua metode. SIFT
bisa dijalankan di GPU kalau pycolmap dibangun dengan CUDA, tapi itu tidak kita uji.

## 7. Apa yang boleh dan tidak boleh disimpulkan

**Boleh:**
- Di lorong ini, pilihan matcher jauh lebih menentukan daripada pilihan feature.
- ALIKED + LightGlue dan SIFT + LightGlue sama-sama membangun peta utuh dan menerima foto uji yang sama.
- ALIKED menemukan lebih banyak match pada pasangan dengan viewpoint yang bergeser (median 201 vs 151), sejalan dengan
  batas SIFT yang diakui Lowe untuk perubahan viewpoint.

**Tidak boleh:**
- "ALIKED lebih akurat daripada SIFT." Data ini tidak menunjukkannya. Akurasi dalam meter belum diukur.
- "SIFT tidak cocok untuk indoor." SIFT + LightGlue berhasil.
- Menggeneralisasi ke gedung lain. Ini satu lorong, satu ponsel, satu sesi rekam, dan satu kali jalan per varian
  (tanpa pengulangan).

**Penjelasan yang masih berupa dugaan (belum diuji):** nearest neighbor gagal karena lorong banyak permukaan
berulang dan mengkilap (ubin, kaca, pintu serupa), sehingga nearest neighbor dan neighbor kedua hampir sama
dekatnya dan ratio test membuang banyak pasangan yang sebenarnya benar. LightGlue memakai konteks seluruh keypoint
untuk memutuskan. Uji pembuktiannya: variasikan threshold ratio (misalnya 0,8 sampai 0,95) dan lihat apakah hasil
nearest neighbor membaik.

**Batas pengujian lain:**
- Ratio 0,8 adalah nilai bawaan untuk SIFT dan tidak di-tune untuk ALIKED.
- Bobot LightGlue untuk SIFT dan untuk ALIKED dilatih oleh penulis yang sama, tapi tidak kita latih ulang.
- hloc menyimpan orientation SIFT dalam derajat, sedangkan bobot SIFT milik LightGlue dilatih dengan radian. Kode
  `spike/run.py` mengonversinya supaya SIFT tidak dirugikan.
- Foto uji dianggap diterima kalau punya minimal 50 inlier. Itu pengecekan keberhasilan, bukan ukuran posisi benar.

## 8. Cara mengulang

```bash
python spike/run.py <dataset> --out <out> --features sift|aliked --matcher nn-ratio|lightglue \
  --max-kp 1024 --resize 1024 --global-resize 512 --seq 10 --exhaustive-max 0
```

Pasangan bawaan: `aliked` dengan `lightglue`, `sift` dengan `nn-ratio`. Hasil mentah pengukuran ini ada di PC lab,
`~/eutopos-data/work/experiments/sift-vs-aliked/` (tidak di repo karena ukurannya besar).
