# SIFT lawan ALIKED: cara kerja, perbedaan, dan hasil pada data lantai 10

Disusun 2026-10-05 atas permintaan pembimbing ("deep dive cara kerja ALIKED sama SIFT, perbedaannya apa,
pakai tabel"). Setiap angka berasal dari salah satu dari tiga sumber, dan ditandai:

- **[Lowe]** D. G. Lowe, "Distinctive image features from scale-invariant keypoints," *IJCV* 60(2), 2004
  (dibaca langsung dari PDF-nya).
- **[ALIKED]** X. Zhao dkk., "ALIKED: A lighter keypoint and descriptor extraction network via deformable
  transformation," *IEEE TIM* 72, 2023 (dibaca dari PDF-nya).
- **[LG]** P. Lindenberger dkk., "LightGlue: Local feature matching at light speed," *ICCV* 2023 (dibaca dari
  PDF-nya).
- **[data]** pengukuran kita di lorong lantai 10 (`docs/spike-plan.md`).

## 1. Jawaban singkat

1. **Dua metode yang berbeda cara kerjanya.** SIFT dirancang manual dengan rumus (deteksi lewat selisih
   Gaussian, deskriptor dari histogram arah gradien). ALIKED dipelajari jaringan saraf dari banyak pasangan
   gambar (deteksi lewat peta skor yang dapat dilatih, deskriptor dari titik-titik sampel yang bentuknya
   ikut dipelajari).
2. **Temuan penting dari data kita: pada lorong lantai 10, penentu hasilnya adalah pencocoknya, bukan
   fiturnya.** Dengan pencocok klasik (tetangga terdekat dengan uji rasio) baik SIFT maupun ALIKED gagal
   (peta pecah 6 potongan, 0 dari 46 foto uji). Dengan LightGlue keduanya berhasil sama persis (401 dari 402
   frame dalam satu peta, 36 dari 46 foto uji, dan **36 foto yang sama**).
3. **Yang membedakan ALIKED dari SIFT setelah pencocoknya sama** lebih halus: pada pasangan frame yang
   sudutnya sudah bergeser, ALIKED menemukan lebih banyak titik cocok, dan ekstraksinya jauh lebih cepat
   (dengan catatan di bagian 6). Pada data ini selisih itu belum cukup besar untuk mengubah hasil akhir.

## 2. Alur kerja fitur lokal (tiga tahap)

Semua metode fitur lokal melakukan tiga hal. Yang berbeda adalah cara tiap tahap dikerjakan.

| Tahap | Pertanyaan yang dijawab | Contoh di COLMAP + SIFT | Di pipeline eutopos |
|---|---|---|---|
| 1. Deteksi | Titik mana di gambar yang khas dan bisa ditemukan lagi? | Puncak selisih Gaussian | ALIKED (peta skor) |
| 2. Deskripsi | Bagaimana "sidik jari" tiap titik? | Histogram arah gradien, 128 angka | ALIKED (128 angka) |
| 3. Pencocokan | Titik mana di gambar A sama dengan titik mana di gambar B? | Tetangga terdekat + uji rasio | LightGlue |

Hasil pencocokan lalu dipakai COLMAP untuk membangun peta 3D (rekonstruksi) dan untuk menghitung posisi
foto uji (PnP).

## 3. SIFT, langkah demi langkah [Lowe]

| Langkah | Yang dilakukan | Angka dari makalah |
|---|---|---|
| 1. Ruang skala | Gambar diburamkan Gaussian bertahap, lalu gambar yang berdekatan dikurangkan (*difference of Gaussian*, DoG). Setiap oktaf mengecil setengah | Pengaburan awal σ = 1,6. Gambar masukan digandakan dulu. 3 skala per oktaf (k = 2^(1/3)) |
| 2. Mencari puncak | Titik dibandingkan dengan 26 tetangganya (8 di skala yang sama, 9 di atas, 9 di bawah). Hanya maksimum atau minimum yang lolos | 26 tetangga |
| 3. Menyaring | Posisi dihaluskan dengan fungsi kuadrat. Titik berkontras rendah dibuang (peka derau). Titik di sepanjang tepi dibuang (posisinya tidak pasti) | Kontras < 0,03 dibuang. Rasio lengkungan utama > 10 dibuang. Contoh di makalah: 832 titik menjadi 729, lalu 536 |
| 4. Arah | Histogram arah gradien di sekitar titik. Puncak tertinggi menjadi arah titik, supaya tahan terhadap putaran | 36 kotak (10° tiap kotak). Puncak lain yang mencapai 80% ikut jadi titik baru (sekitar 15% titik punya lebih dari satu arah) |
| 5. Deskriptor | Area 16 x 16 di sekitar titik (diputar sesuai arahnya) dibagi 4 x 4 sel, tiap sel punya histogram 8 arah | 4 x 4 x 8 = **128 angka**. Dinormalkan, nilai di atas 0,2 dipotong, lalu dinormalkan lagi (tahan terhadap perubahan cahaya) |
| 6. Pencocokan | Tiap titik dicari tetangga terdekat (jarak Euclid). Pasangan dibuang kalau jarak ke tetangga terdekat lebih dari 0,8 kali jarak ke tetangga kedua | Rasio 0,8 membuang 90% pasangan salah dan kurang dari 5% pasangan benar |

**Kelebihan SIFT:** terbukti puluhan tahun, tidak butuh data latih, perilakunya bisa dijelaskan rumus demi
rumus. **Batasnya yang diakui penulisnya:** tahan terhadap skala dan putaran, tetapi "tidak sepenuhnya
invarian afin". Pada permukaan datar yang dimiringkan, persentase titik yang deskriptornya masih menemukan pasangan
benar turun dari sekitar 85% (tanpa kemiringan) menjadi sekitar 50% pada kemiringan 50 derajat (dibaca dari
grafik Gambar 9 [Lowe], jadi angkanya perkiraan).

**SIFT di COLMAP (yang kita uji)**, dibaca dari pycolmap 4.2: gambar diperbesar dulu (`first_octave` = -1),
`peak_threshold` = 0,0067 (lebih longgar dari 0,01 bawaan hloc), `edge_threshold` = 10, 4 oktaf, 3 skala per
oktaf, hingga 2 arah per titik, maksimum 8.192 fitur, dan deskriptor **RootSIFT** (normalisasi `L1_ROOT`,
Arandjelović dan Zisserman, 2012).

## 4. ALIKED, langkah demi langkah [ALIKED]

ALIKED adalah jaringan saraf kecil dengan tiga bagian, lalu satu kepala khusus untuk deskriptor.

| Bagian | Yang dilakukan | Rincian dari makalah |
|---|---|---|
| 1. Pengkodean fitur | Empat blok konvolusi mengubah gambar menjadi fitur berbagai skala | Blok 1: dua konvolusi 3x3. Blok 2: pengecilan 2x2 + konvolusi. Blok 3 dan 4: pengecilan 4x4 + konvolusi **deformabel** 3x3. Aktivasi SELU |
| 2. Penggabungan | Fitur semua skala dibesarkan ke resolusi gambar lalu disatukan | Empat blok "ublock" (konvolusi 1x1 + pembesaran), lalu digabung |
| 3. Peta skor (SMH) | Menghasilkan peta yang nilainya menyatakan seberapa layak tiap piksel jadi titik | Konvolusi 1x1 ke 8 kanal, dua konvolusi 3x3, satu konvolusi 3x3 lagi, lalu sigmoid |
| 4. Deteksi titik (DKD) | Mengambil puncak peta skor | Penekanan non-maksimum radius 2 piksel, ambang skor, lalu *softargmax* pada tambalan lokal untuk posisi sub-piksel. Seluruhnya **dapat diturunkan (differentiable)**, jadi bisa dilatih langsung dari galat proyeksi |
| 5. Deskriptor (SDDH) | Untuk **tiap titik saja** (bukan seluruh gambar), jaringan memilih M posisi sampel yang bentuknya dipelajari, mengambil fitur di posisi itu, lalu menggabungkannya menjadi deskriptor | M posisi sampel. Deskriptor 128 angka pada varian Normal |

**Ide intinya.** SIFT memodelkan perubahan sudut pandang lokal dengan transformasi afin (6 derajat
kebebasan). ALIKED memodelkannya dengan **pergeseran bebas per piksel** di sekitar titik, yang derajat
kebebasannya sebanyak piksel di tambalan itu [ALIKED]. Posisi sampel yang bergeser menyesuaikan bentuk
lokal, dan perhitungan hanya dilakukan di titik yang terdeteksi sehingga hemat komputasi.

**Cara dilatih.** Dengan empat fungsi kerugian: galat proyeksi titik (titik harus jatuh di tempat yang benar
saat gambar dipetakan ke gambar lain), pemusatan puncak skor, kemiripan deskriptor titik yang sama
(*sparse neural reprojection error*), dan keandalan skor. Data latihnya pasangan gambar dari MegaDepth
(foto wisata dengan pose dari COLMAP) dan pasangan homografi sintetis, 100 ribu langkah.

**Arti nama varian.** `ALIKED-N(16)` = jaringan Normal (kanal 16, 32, 64, 128) dengan M = 16 posisi sampel.
Itu yang kita pakai (`aliked-n16` di hloc). Hasil di makalah (HPatches, 640 x 480, 1.000 titik, GPU RTX 2060):
0,677 juta parameter, 4,05 GFLOPs, 77 gambar per detik.

**Pengaturan kita:** ambang deteksi 0,2, NMS 2 piksel, maksimum 1.024 titik per gambar, gambar diperkecil ke
1.024 piksel sisi panjang. Rata-rata yang benar-benar muncul: 632 titik per gambar (data kita).

## 5. Pencocok: tetangga terdekat lawan LightGlue

| | Tetangga terdekat + uji rasio (`NN-ratio` hloc) | LightGlue [LG] |
|---|---|---|
| Cara kerja | Tiap titik dicocokkan sendiri-sendiri ke titik yang deskriptornya paling mirip, lalu diperiksa | Jaringan Transformer yang melihat **seluruh titik kedua gambar sekaligus** |
| Konteks | Tidak ada. Titik dinilai sendirian | Perhatian-diri (self-attention) dan perhatian-silang (cross-attention) antar titik, dengan penyandian posisi relatif |
| Penolakan | Uji rasio 0,8 + cek dua arah (pengaturan kita) | Tiap titik diberi skor "dapat dicocokkan"; titik tanpa pasangan dibuang |
| Pencocokan akhir | Pasangan yang lolos uji | Pasangan dengan skor tertinggi di barisnya dan di kolomnya, di atas ambang |
| Kecepatan | Sangat cepat | Menyesuaikan kesulitan: lapisan dihentikan lebih awal untuk pasangan mudah (*adaptive depth*), titik yang pasti tak cocok dibuang (*adaptive width*) |
| Latihan | Tanpa latihan | Praterlatih pada 1 juta gambar homografi sintetis, lalu disetel pada MegaDepth |
| Fitur yang didukung | Fitur apa pun | SuperPoint, DISK, ALIKED, SIFT (bobot terpisah per jenis) |

## 6. Hasil kita: fitur lawan pencocok (uji 2 x 2) [data]

Data: video keliling lorong lantai 10, 402 frame untuk peta, 46 foto uji dari hari lain. Semua tahap selain
fitur dan pencocok sama dengan layanan (pasangan MegaLoc 512 ditambah 10 frame berurutan). Fitur 1.024
titik pada 1.024 piksel. Dijalankan di PC lab.

| Fitur | Pencocok | Frame di peta utama | Titik 3D | Potongan peta | Foto uji diterima (>= 50 inlier) | Median inlier |
|---|---|---|---|---|---|---|
| SIFT | tetangga terdekat + rasio | 135 / 402 | 4.945 | 6 | **0 / 46** | 0 |
| ALIKED | tetangga terdekat + rasio | 131 / 402 | 3.088 | 6 | **0 / 46** | 0 |
| SIFT | LightGlue | **401 / 402** | 23.645 | **1** | **36 / 46** | 244 |
| ALIKED | LightGlue | **401 / 402** | 24.615 | **1** | **36 / 46** | 220 |

**Kesimpulan dari tabel:**
1. Mengganti pencocok klasik dengan LightGlue mengubah hasil dari gagal total menjadi 78% untuk **kedua**
   fitur, dan peta dari 6 potongan menjadi 1.
2. Dengan pencocok yang sama, SIFT dan ALIKED hasil akhirnya sama pada data ini, termasuk **36 foto uji
   yang sama persis**.

**Pasangan titik cocok antar-frame (median):**

| Fitur + pencocok | Frame berjarak 0,5 detik | Frame berjarak 5 detik | Pasangan 5 detik dengan < 15 cocok |
|---|---|---|---|
| SIFT + tetangga terdekat | 276 | 67 | 58 |
| ALIKED + tetangga terdekat | 251 | 43 | 89 |
| SIFT + LightGlue | 358 | 151 | 34 |
| ALIKED + LightGlue | 443 | 201 | 14 |

Pencocok klasik runtuh pada frame yang berjarak 5 detik (sudut pandang bergeser): pasangan di bawah 15
titik cocok mencapai 58 sampai 89 pasang. LightGlue menekannya menjadi 14 sampai 34, dan ALIKED + LightGlue
paling baik.

**Waktu (GPU PC lab):**

| Fitur | Ekstraksi 402 gambar peta | Catatan |
|---|---|---|
| ALIKED | 17 detik | Di GPU |
| SIFT (pycolmap) | 110 detik | **Di CPU**: pycolmap yang terpasang tidak punya CUDA (`has_cuda` = False) |

Jadi selisih waktu ini menggambarkan CPU lawan GPU pada instalasi kita, **bukan** perbedaan intrinsik kedua
metode. SIFT bisa dijalankan di GPU kalau pycolmap dibangun dengan CUDA, tetapi itu tidak kita uji.

## 7. Apa yang boleh dan tidak boleh disimpulkan

**Boleh:**
- Pada lorong ini, pilihan pencocok jauh lebih menentukan daripada pilihan fitur.
- ALIKED + LightGlue dan SIFT + LightGlue sama-sama membangun peta utuh dan menerima foto uji yang sama.
- ALIKED menemukan lebih banyak titik cocok pada pasangan dengan sudut yang bergeser (201 lawan 151 median),
  sejalan dengan batas SIFT yang diakui Lowe untuk perubahan sudut pandang.

**Tidak boleh:**
- "ALIKED lebih akurat daripada SIFT." Data ini tidak menunjukkannya. Akurasi dalam meter belum diukur.
- "SIFT tidak cocok untuk indoor." SIFT + LightGlue berhasil.
- Menggeneralisasi ke gedung lain. Ini satu lorong, satu ponsel, satu sesi rekam, dan satu kali jalan per
  varian (tanpa pengulangan).

**Penjelasan yang masih berupa dugaan (belum diuji):** pencocok klasik gagal karena lorong banyak
permukaan berulang dan mengkilap (ubin, kaca, pintu serupa), sehingga tetangga terdekat dan tetangga kedua
hampir sama dekatnya dan uji rasio membuang banyak pasangan yang sebenarnya benar. LightGlue memakai konteks
seluruh titik untuk memutuskan. Uji pembuktiannya: variasikan ambang rasio (misalnya 0,8 sampai 0,95) dan
lihat apakah hasil klasik membaik.

**Batas pengujian lain:**
- Ambang rasio 0,8 adalah bawaan untuk SIFT dan tidak disetel untuk ALIKED.
- Bobot LightGlue untuk SIFT dan untuk ALIKED dilatih oleh penulis yang sama, tetapi tidak kita latih ulang.
- Orientasi SIFT disimpan hloc dalam derajat, sedangkan bobot SIFT LightGlue dilatih dengan radian. Kode
  `spike/run.py` mengonversinya agar SIFT tidak dirugikan.
- Foto uji diterima kalau punya minimal 50 inlier. Itu pemeriksaan keberhasilan, bukan ukuran posisi benar.

## 8. Cara mengulang

```bash
python spike/run.py <dataset> --out <out> --features sift|aliked --matcher nn-ratio|lightglue \
  --max-kp 1024 --resize 1024 --global-resize 512 --seq 10 --exhaustive-max 0
```

Pasangan bawaan: `aliked` memakai `lightglue`, `sift` memakai `nn-ratio`. Hasil mentah pengukuran ini ada di
PC lab, `~/eutopos-data/work/experiments/sift-vs-aliked/` (tidak di repo karena ukurannya besar).
