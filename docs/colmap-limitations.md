# Limitasi COLMAP (dan pipeline peta) untuk eutopos

Disusun 2026-10-04 atas permintaan pembimbing ("cek dulu limitasinya sampai mana"). Setiap limitasi diberi
**status bukti**: terbukti di data kita sendiri, atau baru dari literatur dan belum kita uji. Rujukan
dicocokkan ke Crossref (metadata) dan abstrak (isi klaim). Hal yang belum punya sumber ditandai ⚠️.

**Konteks singkat.** COLMAP di sini hanya bagian **rekonstruksi** (Structure-from-Motion inkremental
[1]). Fitur diekstrak ALIKED dan dicocokkan LightGlue lewat hloc, bukan fitur SIFT bawaan COLMAP. Jadi
sebagian limitasi di bawah milik SfM secara umum, sebagian milik cara kita merekam.

## Ringkasan

| # | Limitasi | Status | Dampak untuk PA | Penanganan |
|---|---|---|---|---|
| 1 | Permukaan tanpa tekstur (dinding polos) | **Terbukti** (uji 30 Sep) | Peta pecah, area tidak terlokalisasi | Aturan rekam: jangan menghadap dinding polos dari dekat |
| 2 | Blur karena gerakan cepat | **Terbukti** (uji 30 Sep) | Peta putus di belokan | Belok pelan; frame buram terdeteksi dari ketajaman |
| 3 | Perubahan cahaya tiba-tiba (lorong ke jendela) | **Terbukti** (uji 30 Sep) | Peta putus | Rekam dengan eksposur stabil, beri waktu kamera menyesuaikan |
| 4 | Cakupan sudut pandang peta | **Terbukti sebagian** (uji 1 Okt) | Foto dari arah yang tidak terekam bisa gagal | Pola keliling + rekaman tambahan menghadap tujuan penting |
| 5 | Peta tidak punya satuan meter | **Terbukti** (sifat SfM monokular [2]) | Posisi belum dalam koordinat gedung | Penyelarasan ke titik acuan terukur |
| 6 | Struktur berulang (lorong mirip, antar lantai) | Literatur [3], **belum diuji** | Lokalisasi ke lantai atau lorong yang salah | Uji lantai kedua; pertimbangkan deteksi lantai |
| 7 | Perubahan kondisi (siang dan malam, tata ruang) | Literatur [4][5][6], **belum diuji** | Akurasi turun seiring waktu | Uji di jam berbeda; prosedur pemetaan ulang |
| 8 | Waktu bangun peta membesar dengan jumlah gambar | **Terukur sebagian**, literatur [7] | Pemetaan satu gedung bisa lama | Pasangan berurutan, bukan semua-lawan-semua; GLOMAP sebagai cadangan |
| 9 | Orang lewat, kaca dan pantulan | ⚠️ Dugaan dari data, **belum ada sumber** | Fitur palsu atau hilang | Catat kondisi saat rekam; uji terpisah |
| 10 | Ukuran database dan jumlah gambar yang bisa direkonstruksi | **Batas format terverifikasi** [8][9], ukuran **terukur** di 402 frame, batas praktis **belum diuji** | Menentukan apakah satu gedung muat | Uji skala bertahap (bagian 10) |

Tidak ada pose salah yang lolos di kedua uji: semua pose yang meloncat jauh punya 3 sampai 9 inlier dan
ditolak ambang 50 inlier. Itu pemeriksaan konsistensi, **belum akurasi meter**.

## 1-3. Tekstur, blur, cahaya (terbukti)

Uji jalur ular lantai 10 (2026-09-30, `docs/spike-plan.md`): peta dari 181 frame **pecah menjadi 3
potongan** (87, 63, 25 frame), dan hanya 20 dari 46 foto uji diterima (43%). Frame di setiap titik putus
dibuka satu per satu:

| Titik putus | Penyebab | Bukti |
|---|---|---|
| Belok lorong ke lobi lift | Putaran cepat, lalu cahaya berubah ke jendela kaca terang | Ketajaman frame 15 sampai 37 (frame baik > 100) |
| Berbalik dari jendela ke aula | Eksposur masih menyesuaikan, frame gelap lalu buram | Frame 97-99 |
| Putar balik jalur ular | **Kamera menghadap dinding putih polos dari dekat ±5 detik** | Ketajaman 5 sampai 11, tidak ada fitur |

Limitasi ini sejalan dengan literatur lokalisasi dalam ruangan: InLoc [5] memakai pencocokan rapat,
bukan fitur lokal, justru karena adegan dalam ruangan banyak yang tanpa tekstur.

**Bukti perbaikannya:** dengan pola rekam keliling (punggung ke dinding, kamera ke tengah ruangan, jalur
tertutup) pada area yang sama, 401 dari 402 frame masuk **satu peta utuh** dan 36 dari 46 foto uji dari
hari lain diterima (78%). Akar masalahnya ada di cara merekam, dan aturannya sudah masuk
`docs/field-test-runbook.md`.

## 4. Cakupan sudut pandang (terbukti sebagian)

Peta keliling hanya berisi pandangan ke tengah ruangan, sedangkan foto uji menghadap arah jalan (sekitar
90 derajat berbeda). 78% tetap diterima, jadi beda sudut ini lebih kecil pengaruhnya dari dugaan. Tetapi
dinding di belakang pemeta (termasuk pintu lab, tujuan penting) hanya terlihat dari seberang ruangan.
Foto uji 17-22 dan 39-42 ditolak di uji kedua; posisi mereka perlu dicek di laporan 3D.

**Rencana:** kalau foto di depan tujuan penting gagal, tambahkan rekaman pendek yang menghadap tujuan itu.

## 5. Tanpa satuan meter (terbukti)

Rekonstruksi dari kamera tunggal hanya benar sampai skala: posisi relatif antar kamera benar, tapi
satuannya bebas [2]. `/health` layanan saat ini menampilkan `"aligned": false`. Peta harus diselaraskan
ke koordinat gedung lewat titik acuan yang diukur dengan meteran (`docs/design-notes.md`), dan itu
sekaligus menjadi dasar uji akurasi meter, jalur kritis PA.

## 6. Struktur berulang (literatur, belum diuji)

Dua permukaan berbeda yang tampak mirip bisa membuat algoritma rekonstruksi 3D menghasilkan peta yang
salah [3]. Untuk gedung bertingkat, risikonya adalah lorong atau lobi lift yang mirip di lantai lain:
foto bisa dilokalisasi ke lantai yang salah dengan inlier yang tinggi, sehingga ambang inlier tidak
menolongnya.

**Rencana:** petakan lantai kedua dengan pola yang sama, lalu lokalisasikan foto lantai 10 ke peta
gabungan. Hitung berapa yang jatuh ke lantai yang salah. Kalau tinggi, batasi pencarian per lantai
(misalnya lantai dipilih pengguna atau dari barometer, `docs/research-paper.md` bagian 6).

## 7. Perubahan kondisi (literatur, belum diuji)

Lokalisasi jangka panjang dalam kondisi yang berubah (siang dan malam, cuaca, musim) masih jauh dari
selesai [4]. Di dalam ruangan, perubahan tata letak dan penghalang menjadi tantangan tersendiri [5], dan
LaMAR [6] menunjukkan bahwa benchmark lama tidak mewakili kondisi AR sebenarnya.

**Rencana:** ambil foto uji di jam berbeda (pagi, siang, malam dengan lampu) pada area yang sama dan
bandingkan tingkat penerimaannya. Pemetaan ulang setelah tata ruang berubah memakai pipeline pekerja yang
sudah ada (unggah video baru, bangun, terbitkan), dan batas ini diakui di laporan.

## 8. Waktu bangun peta (terukur sebagian)

| Peta | Frame | Waktu (GPU, PC lab) |
|---|---|---|
| Jalur ular | 181 | ±3,5 menit |
| Jalur keliling | 402 | ±6 menit (pencocokan 186 s, rekonstruksi 151 s) |

Pasangan gambar dibuat **berurutan** (setiap frame dengan 10 tetangganya), jadi waktu pencocokan tumbuh
kurang lebih sebanding jumlah frame, bukan kuadrat. Rekonstruksi inkremental COLMAP tetap paling lambat
untuk koleksi besar; SfM global seperti GLOMAP mengklaim hasil sebanding dengan COLMAP dan jauh lebih
cepat [7]. **Belum perlu** untuk satu lantai; dicatat sebagai cadangan kalau pemetaan satu gedung terlalu
lama.

## 9. Orang lewat, kaca, pantulan (⚠️ belum ada sumber)

Dugaan dari data: foto uji 17-22 lemah di kedua uji, di area dekat jendela kaca. Belum dibuktikan bahwa
kacalah penyebabnya. **Rencana:** catat kondisi (ramai atau sepi, cahaya dari jendela) di setiap sesi
rekam, dan cari sumber literatur sebelum menulisnya sebagai limitasi di proposal.

## 10. Ukuran database dan jumlah gambar (pertanyaan pembimbing, 4 Okt)

Pertanyaannya: COLMAP open source, tapi seberapa besar **database** untuk rekonstruksi 3D yang masih bisa
ditangani? Jawabannya ada tiga lapis, dan hanya lapis pertama yang punya angka resmi.

**Lapis 1: batas format (terverifikasi).** Database COLMAP adalah file SQLite. Dokumentasi resmi COLMAP
menyebut `image_id` harus lebih kecil dari 2147483647, sehingga jumlah gambar per database dibatasi
2147483647 [8]. SQLite sendiri membatasi file sampai sekitar 281 TB [9]. Dua batas ini jauh di atas kebutuhan
satu gedung.

**Lapis 2: ukuran file di data kita (terukur).** Database dari eksperimen SIFT vs ALIKED di PC lab, 402 frame,
1024 keypoint per frame:

| Feature | Matcher | Ukuran `database.db` | Per frame |
|---|---|---|---|
| SIFT | NN + ratio | 17,4 MB | 43 KB |
| ALIKED | NN + ratio | 14,5 MB | 36 KB |
| SIFT | LightGlue | 28,4 MB | 71 KB |
| ALIKED | LightGlue | 35,2 MB | 88 KB |

Pipeline kita membuat pasangan dari tetangga retrieval (`--k-map 20`) ditambah tetangga berurutan, jadi
jumlah pasangan per frame kira-kira tetap dan ukuran database **diperkirakan tumbuh linear** terhadap jumlah
frame. Dengan angka terburuk (88 KB per frame): 5.000 frame sekitar 0,44 GB, 50.000 frame sekitar 4,4 GB.
Ini **perkiraan**, belum diuji di skala itu.

**Lapis 3: batas praktis (belum ada angka resmi).** FAQ COLMAP tidak memberi angka maksimum gambar atau
memori; yang disarankan hanya menghindari `exhaustive_matcher` dan memakai hierarchical mapper untuk
dataset sangat besar [10]. Jadi yang membatasi bukan ukuran database, tapi **RAM dan waktu rekonstruksi
inkremental** di mesin kita (PC lab: 15 GB RAM). Satu lantai (402 frame) selesai sekitar 6 menit.

⚠️ **Belum diketahui:** berapa frame yang masih muat di 15 GB RAM dan berapa lama waktunya. Angka itu
harus diukur, bukan ditebak.

**Rencana ukur (usulan, belum dijalankan):** bangun peta dari 100, 200, 402 frame (dan gabungan dua lantai
bila ada), catat ukuran database, waktu tiap tahap, dan memori puncak. Tiga sampai empat titik cukup untuk
melihat apakah pertumbuhannya linear dan memperkirakan batas satu gedung.

## Batas temuan ini

Semua bukti berasal dari **satu lantai, satu ponsel, dua sesi rekam**. Angka 43% dan 78% adalah tingkat
penerimaan foto, bukan akurasi posisi.

## Rujukan

[1] J. L. Schönberger and J.-M. Frahm, "Structure-from-motion revisited," in *Proc. IEEE CVPR*, 2016, pp. 4104–4113, doi: 10.1109/CVPR.2016.445.

[2] R. Hartley and A. Zisserman, *Multiple View Geometry in Computer Vision*, 2nd ed. Cambridge, U.K.: Cambridge Univ. Press, 2004, doi: 10.1017/CBO9780511811685.

[3] R. Cai, J. Tung, Q. Wang, H. Averbuch-Elor, B. Hariharan, and N. Snavely, "Doppelgangers: Learning to disambiguate images of similar structures," in *Proc. IEEE/CVF ICCV*, 2023, pp. 34–44, doi: 10.1109/ICCV51070.2023.00010.

[4] T. Sattler *et al.*, "Benchmarking 6DOF outdoor visual localization in changing conditions," in *Proc. IEEE/CVF CVPR*, 2018, pp. 8601–8610, doi: 10.1109/CVPR.2018.00897.

[5] H. Taira *et al.*, "InLoc: Indoor visual localization with dense matching and view synthesis," in *Proc. IEEE/CVF CVPR*, 2018, pp. 7199–7209, doi: 10.1109/CVPR.2018.00752.

[6] P.-E. Sarlin *et al.*, "LaMAR: Benchmarking localization and mapping for augmented reality," in *Proc. ECCV*, 2022, pp. 686–704, doi: 10.1007/978-3-031-20071-7_40.

[7] L. Pan, D. Baráth, M. Pollefeys, and J. L. Schönberger, "Global structure-from-motion revisited," in *Proc. ECCV*, 2024, pp. 58–77, doi: 10.1007/978-3-031-73661-2_4.

[8] COLMAP Developers, "Database format," *COLMAP documentation*. [Online]. Available: https://colmap.github.io/database.html (accessed Oct. 5, 2026).

[9] SQLite Consortium, "Limits in SQLite," Sec. 25, "Maximum database size." [Online]. Available: https://www.sqlite.org/limits.html (accessed Oct. 5, 2026).

[10] COLMAP Developers, "Frequently asked questions," *COLMAP documentation*. [Online]. Available: https://colmap.github.io/faq.html (accessed Oct. 5, 2026).
