# Konteks Proyek Akhir (PA)

Ringkasan hasil brainstorming dan keputusan PA yang melahirkan eutopos-vps. Dibaca supaya sesi baru
tidak kehilangan konteks: **apa judulnya, kenapa begitu, apa yang sudah diputuskan, dan apa yang
masih terbuka.**

> **Sumber kebenaran.** Untuk isi PA (judul, arah, keputusan teknis, isu proposal, pelajaran),
> **berkas ini yang berlaku**. Catatan administrasi dan hal internal disimpan terpisah di repo privat
> pemilik. Arahan pembimbing ditulis sebagai parafrase, bukan kutipan percakapan.

## 1. Identitas

| Hal | Isi |
|---|---|
| Program | D3 Teknik Informatika, PENS PSDKU Lamongan, kelas D3 IT-A |
| Pembimbing 1 | Sritrusta Sukaridhoto |
| Pembimbing 2 | Evianita Dewi Fajrianti |
| Lokasi uji | Gedung PENS pusat, Surabaya |
| Pengajuan judul | Diunggah ke MIS sebelum tenggat 18 September 2026. **Menunggu ACC** |
| Seminar proposal | 15 Desember 2026. **Proposal PA adalah dokumen terpisah** dari pengajuan judul |

## 2. Judul final (dikunci 15 September 2026)

> **Platform *Indoor Navigation* Terintegrasi *AI Avatar Assistant* Berbasis *Retrieval-Augmented Generation***

Disetujui kedua pembimbing. Versi teks polos untuk MIS:

```text
Platform Indoor Navigation Terintegrasi AI Avatar Assistant Berbasis Retrieval-Augmented Generation
```

**Aturan penulisan:**
- RAG **ditulis lengkap** di judul. Di dalam dokumen boleh disingkat setelah penyebutan pertama.
- Pakai **tanda hubung** (*Retrieval-Augmented Generation*), mengikuti paper Lewis dkk. (2020).
- Istilah asing **boleh**, asal dicetak miring. Pedoman PA PENS meminta istilah Indonesia sedapat
  mungkin, dan istilah asing ditulis miring. Ini aturan penulisan, bukan larangan.

**Kenapa judul ini kuat:**
- **Platform jadi kepala judul**, menjawab kritik bahwa judul lama terlalu parsial.
- **Unsur integrasi ada** dalam satu kata.
- **Tidak mengunci teknologi.** Tidak menyebut VPS, hloc, perangkat, atau fully local. Kalau spike
  gagal dan metode harus berganti, judul tetap berlaku.

**Yang sengaja tidak masuk judul:** seamless indoor-outdoor, Mixed Reality, loop closure, akurasi
lokalisasi, studi kasus gedung, avatar dan TTS. Semuanya tetap boleh jadi fitur atau bahan validasi.

## 3. Riwayat judul

| Tanggal | Judul atau kejadian |
|---|---|
| 6 Sep | *Rancang Bangun Asisten Navigasi Indoor Augmented Reality Berbasis RAG dan Analisis Sentimen untuk Perutean Adaptif*. Disetujui, lalu pembimbing menambahkan seamless indoor-outdoor dan deploy MR |
| 6 Sep | **Lokasi dipindah** dari rumah sakit ke gedung PENS pusat. Akses data rumah sakit berisiko (misalnya saat akreditasi), dan gedung PSDKU dinilai terlalu kecil |
| 12 Sep | **Analisis sentimen dicabut** kedua pembimbing. Porsi pemrosesan bahasa sudah ditanggung RAG |
| 13 Sep | *Rancang Bangun Asisten Navigasi Seamless Indoor-Outdoor Berbasis Mixed Reality dengan Retrieval-Augmented Generation* |
| 14 Sep | **Arahan baru pembimbing 1:** judul terlalu parsial, harus berbentuk **platform**. Fully local, tanpa VPS komersial (tidak lokal, berbayar, terbatas) |
| 15 Sep | **Judul final** (bagian 2) |
| 18 Sep | Pengajuan diunggah. **Fokus mobile dulu**, MR di luar cakupan |

### Pelajaran dari gugurnya analisis sentimen

> **Jangan menaruh sumber data di judul. Taruh kontribusinya.** Sumber data bisa ditolak, diganti,
> atau ternyata tidak ada. Judul sempat berubah dua kali dalam seminggu karena ini.

Lima alasan analisis sentimen tidak cocok:
1. **Mubazir.** Sentimen dan RAG sama-sama pemrosesan bahasa.
2. **Terlalu mudah.** Sudah tugas selesai dengan model siap pakai.
3. **Datanya tidak ada.** Tidak ada kumpulan keluhan per koridor. Ulasan publik membicarakan
   institusi, bukan ruas rute.
4. **Cara pakainya melawan.** Orang tidak mengetik keluhan sambil mencari ruangan.
5. **Salah menamai mata rantai.** Bagian tersulit ada di penarikan lokasi, model biaya, dan kebijakan
   pengalihan rute, bukan di klasifikasi sentimennya.

**Perutean adaptif ikut keluar**, karena sentimen adalah sumber sinyalnya. Alternatif kalau diminta
kembali: waktu tempuh nyata per koridor dari pengguna, digabung prediksi dari jadwal perkuliahan.

Tiga pertanyaan wajib sebelum mengusulkan komponen serupa: **datanya dari mana, cara pakainya masuk
akal atau tidak, dan bagian mana yang sebenarnya sulit.**

## 4. Arahan pembimbing yang mengikat (parafrase)

1. **Fully local.** Semua layanan berada dalam kendali instansi. Jangan memakai teknologi luar yang
   tidak bisa masuk ke instansi.
2. **Prinsip Platform as a Service.** Dibaca sebagai: instansi meng-host platformnya sendiri lalu
   melayankannya ke pengguna. Konsekuensinya, pengelola harus bisa memperbarui isi tanpa menunggu
   pengembang. ⚠️ Pembacaan, belum dikonfirmasi eksplisit.
3. **Tanpa VPS komersial** (MultiSet dan sejenisnya).
4. **Berkelanjutan.** Bisa dipakai terus oleh instansi.
5. **Urutan kerja:** (1) lokalisasi yang berjalan lokal, (2) anchoring tool untuk titik tujuan,
   (3) seamless indoor-outdoor **hanya kalau waktu cukup**.
6. **Improvement mendalam di sisi navigasi**, dengan validasi akurasi lokalisasi.
7. **AI assistant berwujud karakter 3D** yang memandu dan menjelaskan titik tujuan lewat suara.
8. **ARCore boleh**, fitur on-device saja (motion tracking). Cloud Anchors dan Geospatial API tidak
   boleh karena lewat cloud. ⚠️ Penilaian pemilik repo, belum dikonfirmasi eksplisit.

**Target publikasi** yang pernah disebut pembimbing: jurnal Q2 ScienceDirect, contohnya *Computers
and Education* dan *International Journal of Human-Computer Studies*. Keduanya berpusat pada
manusia, jadi butuh **studi pengguna dengan pembanding, instrumen baku (SUS, NASA-TLX), dan
statistik**, bukan sekadar metrik sistem. Studi pengguna menuntut sistem stabil lebih awal.

## 5. Platform yang dibangun

```text
[Ponsel Android: Unity + ARCore]
  ├─ ARCore melacak gerak ──── 1 foto berkala ───► [eutopos-vps] hloc + LightGlue + PnP
  │                        ◄──── pose 6-DoF ─────    peta 3D COLMAP, koordinat gedung
  ├─ NavMesh menghitung rute ke titik tujuan (POI)
  ├─ Avatar 3D (UniVRM + lip sync)
  └─ Mikrofon ──► [Layanan AI] speech-to-text ► RAG (pgvector) ► model bahasa ► TTS (sherpa-onnx)
                                                         └─► ID POI tujuan ► basis data POI
[Anchoring tool] dashboard web untuk menandai POI di denah
```

| Bagian | Asal | Catatan |
|---|---|---|
| **Layanan VPS (repo ini)** | **Baru** | Risiko tertinggi, dibuktikan lewat spike |
| Koreksi posisi di Unity | Baru | Transformasi koordinat sesi ARCore ke koordinat gedung |
| Anchoring tool | Baru | Dijanjikan di dokumen pengajuan |
| Speech-to-text lokal | Baru | Proyek sebelumnya memakai pengenal suara Android yang lewat cloud |
| Korpus pengetahuan kampus | Baru | |
| Avatar, lip sync, TTS, backend RAG | Diturunkan dari proyek navigasi AR tim sebelumnya (repo privat) | Disalin, bukan fork. **Tanpa VPS komersial** |
| Model bahasa | Gateway LLM milik lab dengan GPU | **Tanpa fallback ke layanan cloud.** ⚠️ Apakah lab itu dihitung "instansi" perlu dikonfirmasi |

## 6. Isi dokumen pengajuan yang diunggah

**Tujuan:**
1. Membangun layanan VPS lokal di server instansi (Structure-from-Motion + local feature matching).
2. Galat posisi horizontal **≤ 1,0 m pada ≥ 70%** pengujian, terhadap titik acuan terukur.
3. **Mengukur latensi** di server tanpa GPU sebagai dasar interval koreksi berkala. Sengaja **tanpa
   angka** sampai spike berjalan.
4. Anchoring tool untuk **minimal 10 POI**.
5. AI avatar assistant berbasis RAG yang menentukan POI dari pertanyaan berbahasa Indonesia dengan
   **akurasi ≥ 80%**.
6. Aplikasi pada perangkat mobile Android berbasis ARCore.

**Kontribusi yang diklaim:** integrasi VPS lokal, RAG yang menghasilkan POI, dan anchoring tool dalam
satu platform, beserta evaluasi akurasi dan latensi VPS di server tanpa GPU.

**Evaluasi:**

| Aspek | Target |
|---|---|
| Akurasi penentuan posisi | ≤ 1,0 m pada ≥ 70% |
| Latensi | Terukur, jadi dasar interval koreksi |
| Koreksi berkala | Galat dengan koreksi VPS < ARCore tanpa koreksi, pada lintasan yang sama |
| Penentuan POI (RAG) | ≥ 80% dari 50 pertanyaan yang **disusun pihak selain pengembang** |
| Efektivitas navigasi | Waktu tugas, salah arah, dan NASA-TLX lebih rendah dari pembanding (denah dan papan petunjuk). SUS ≥ 68 |
| Anchoring tool | ≥ 10 POI tampil di aplikasi tanpa mengubah kode |
| Kelayakan perangkat | Aplikasi Android ≥ 30 FPS |

**Rujukan di dokumen pengajuan:** INSUS (2023), INSUS reset papan nama (2024), Brata dkk. (2024),
hloc (2019), COLMAP (2016), LightGlue (2023), RAG (2020). Rincian di `docs/research-paper.md`.

## 7. Isu untuk Proposal PA (belum ditagih di pengajuan judul)

1. **Cakupan terlalu besar untuk D3.** Tetapkan inti (VPS, navigasi, RAG ke POI) dan pendukung (avatar).
2. **Pisahkan kontribusi pribadi** dari proyek tim sebelumnya. Penguji akan bertanya apa yang baru.
3. **Jumlah responden** studi pengguna.
4. **Tempat model bahasa dijalankan** dan status "instansi"-nya.
5. **Prosedur pemetaan ulang** saat tata ruang berubah. Anchoring tool hanya memperbarui POI.
6. **Area uji, cara mengukur ground truth, dan lisensi bobot retrieval.**
7. **Speech-to-text lokal** adalah pekerjaan baru.
8. **Pembanding VPS komersial** (opsional): memakai VPS komersial hanya sebagai pembanding pengujian
   di titik yang sama, bukan di dalam platform. Tanyakan pembimbing.

Sisa perapian dokumen pengajuan yang mungkin terbawa: sisa kata MR di tabel dan Gambar 1, posisi
Gambar 2, dan istilah "(Spike Testing)". Rapikan di Proposal PA.

## 8. Keputusan teknis dan alasannya

| Keputusan | Alasan | Rincian |
|---|---|---|
| **hloc + COLMAP + ALIKED + LightGlue** | Satu-satunya yang lolos empat syarat: tanpa QR, fully local, lisensi bersih, bukti akurasi indoor | `docs/research-paper.md` |
| **Koreksi berkala, bukan pelacakan kontinu** | Pola terpublikasi (VIO-APR, MobileARLoc). Latensi beberapa detik masih bisa diterima | `docs/research-paper.md` |
| **Spike satu koridor lebih dulu** | Semua bagian lain bergantung pada VPS | `docs/spike-plan.md` |
| **Capture: ponsel + meteran untuk spike** | Kamera peta harus mirip kamera query. GoPro MAX dan iPhone LiDAR jadi pembanding opsional | `docs/spike-plan.md` bagian 4.5 |
| **Perangkat lunak yang dibangun: perangkai alur, bukan mesin SfM** | COLMAP dan hloc sudah ada | Bagian 9 |
| **Repo terpisah** | Stack beda, kontribusi pribadi jelas, dan proyek tim tetap memakai VPS komersial | Bagian 9 |

## 9. Hasil brainstorming lain

- **"CPU-only" sebenarnya tiga pertanyaan.** Membangun peta boleh di mesin lain (offline). Lokalisasi
  per query yang harus diukur di server. Model bahasa adalah bagian yang paling butuh GPU.
- **Server instansi hanya VM 2 vCPU dan RAM 7,8 GB.** Angka dari PC lab (i7-10700K, RTX 3070) adalah
  **batas atas**, bukan bukti untuk server. Karena itu pengukuran dibuat tiga tingkat: PC lab dengan
  GPU, PC lab tanpa GPU, dan server instansi.
- **PC lab** dipakai untuk pengembangan dan membangun peta. Menjadikannya host layanan mengubah klaim
  "tanpa GPU", jadi harus disetujui pembimbing.
- **Pemetaan ulang oleh pengelola non-teknis tidak dijanjikan.** Untuk D3 cukup skrip pemetaan ulang
  yang terdokumentasi, dan batasan ini diakui di laporan.
- **Paper sensor (Kim & Shin 2025)** hanya pelengkap: deteksi lantai lewat barometer mungkin bisa
  mempersempit kandidat retrieval.
- **Nama eutopos:** *eu* (baik) + *topos* (tempat), dari makna nama "Bagus". Kandidat lain yang sempat
  diusulkan: Ketitik (dari pepatah Jawa *becik ketitik*), Kalos, Bhadra, Bene.
- **Repo publik, AGPL-3.0.** Siapa pun yang menjalankan versi modifikasinya sebagai layanan wajib
  membuka kode sumbernya.

## 10. Pelajaran cara kerja

1. **Taruh kontribusi di judul**, bukan sumber data atau teknologinya.
2. **Jangan mengunci yang belum terbukti.** Target latensi sengaja tanpa angka sampai spike berjalan.
3. **Verifikasi klaim ke sumber primer** sebelum diteruskan, termasuk hasil agen riset.
4. **Slot di sebuah formulir bukan izin.** Yang berlaku aturan koordinator.
5. **Setelah judul atau cakupan berubah, telusuri semua turunannya.** Mengganti "MR" menjadi "Mobile"
   di satu kalimat meninggalkan MR di tabel dan gambar.
6. **Tanyakan hal milik pembimbing A ke A**, jangan meminta B menilai keputusan A.
7. **Periksa lisensi tiap model**, bukan hanya lisensi pustakanya.
8. **Kalibrasi review dengan tahap dokumen.** Pengajuan judul cukup meyakinkan bahwa judul layak.
9. **Janji "fully local" dicek per komponen**, termasuk yang tak terlihat (TTS dan pengenal suara
   bawaan bisa lewat cloud).
10. **Gambar dari model AI diedit manual, jangan diregenerasi.** Tulis setiap panah dengan asal dan
    tujuan eksplisit.
11. **Gambar dan tabel diletakkan tepat setelah kalimat yang merujuknya.** Keterangan gambar di
    bawah, keterangan tabel di atas.

## 11. Menulis dokumen PA

### Struktur dokumen pengajuan yang dipakai (dokumen Google, tampak seperti template)

1. Identitas dan judul
2. **Deskripsi Proyek Akhir**, berisi: latar belakang, permasalahan, tujuan, metode yang digunakan
   (tinjauan pustaka singkat), dan metode penelitian
3. Nama dosen pembimbing
4. Tempat, tanggal, tanda tangan
5. **Daftar Pustaka, setelah tanda tangan**

Tanpa Abstrak dan tanpa Batasan Masalah. ⚠️ Status resmi template belum dikonfirmasi. **Template resmi
jurusan selalu menang** atas struktur acuan di bawah.

### Struktur acuan (dipakai hanya untuk menambah bagian yang belum ada)

Identitas, Deskripsi Proyek Akhir (berperan sebagai abstrak), Latar Belakang, Permasalahan, Batasan
Masalah, Tujuan, Tinjauan Pustaka, Metode Penelitian, Daftar Pustaka, usulan pembimbing, tanda
tangan.

**Aturan per bagian:**
- **Deskripsi** harus bisa dibaca berdiri sendiri: masalah, sistem, teknologi inti, pengguna.
- **Batasan** cukup 4 sampai 5 baris: gedung, cakupan indoor atau outdoor, perangkat.
- **Tujuan wajib memuat angka terukur** (akurasi, latensi, jumlah POI). Kalau angkanya belum punya
  dasar, tulis bahwa angka ditetapkan setelah uji kelayakan, jangan mengarang.
- **Tinjauan Pustaka dan Metode Penelitian dipisah.** Tinjauan menjawab apa yang sudah dikerjakan
  orang lain dan di mana celahnya. Metode menjawab bagaimana mengerjakannya.
- **Daftar Pustaka** minimal 5 sampai 8 rujukan, mayoritas 5 tahun terakhir.
- **Tidak perlu:** abstrak terpisah, jadwal (itu isi proposal), dan target luaran sebagai bab sendiri.
- **Format:** semua bab utama memakai level heading yang sama. Istilah asing dicetak miring.

### Gaya penulisan akademik yang disepakati

- **Setiap klaim harus punya bukti** atau dilemahkan. Klaim yang belum diukur ditulis sebagai hal
  yang dibuktikan lewat uji kelayakan.
- **Jangan menjanjikan komponen yang belum punya jalan** (misalnya "sepenuhnya lokal" untuk bagian
  yang masih lewat cloud).
- **Kritik terhadap penelitian pembimbing dibingkai sebagai kelanjutan**, dan hanya menyebut
  keterbatasan teknis yang pasti benar dari cara kerjanya.
- **Nama server internal tidak ditulis** di dokumen formal. Tulis "server instansi".
- **Sesuaikan standar review dengan tahap dokumen.** Pengajuan judul cukup meyakinkan bahwa judul
  layak. Isu tingkat proposal disimpan untuk Proposal PA.

### Gambar di dokumen pengajuan

🚧 **Gambar final belum matang.** Sementara itu, versi **Mermaid** kedua gambar ada di
`docs/figures/README.md` sebagai acuan, dan GitHub merendernya langsung. Gambar final nanti
disimpan di folder yang sama.

**Gambar 1. Arsitektur platform indoor navigation terintegrasi AI avatar assistant berbasis RAG.**
Dua kontainer:
- **Perangkat Pengguna (Android):** ARCore Motion Tracking, Aplikasi Unity (NavMesh, AR Route
  Overlay), Input Mikrofon, Avatar 3D (UniVRM + Lip Sync).
- **Server Instansi (On-Premise):**
  - Layanan Navigasi: VPS Service (FastAPI, hloc + LightGlue + PnP), Peta 3D (COLMAP), Basis Data POI,
    Anchoring Tool (Dashboard Web).
  - Layanan AI: Speech-to-Text, Vector Database, Model Bahasa (LLM), Text-to-Speech (sherpa-onnx).

Panah: frame kamera (koreksi berkala) ke VPS, pose 6-DoF ke Unity, VPS ke Peta 3D, Anchoring Tool
ke Basis Data POI, koordinat POI ke Unity, audio pertanyaan ke STT, STT ke Vector Database ke LLM,
ID POI tujuan ke Basis Data POI, LLM ke TTS, dan audio jawaban ke Avatar.

**Jangan** menulis "tanpa GPU" di header server, karena LLM ada di kontainer itu. **Jangan** ada
garis dari Peta 3D ke Basis Data POI.

**Gambar 2. Alur pemrosesan pertanyaan pengguna hingga navigasi AR.** Dua kolom:
- **Tahap 1, Penentuan Tujuan:** Mulai → pertanyaan suara → STT → RAG → model bahasa menghasilkan
  jawaban dan ID POI → *POI ditemukan?* (Tidak: minta memperjelas, kembali ke pertanyaan) → avatar
  menyampaikan jawaban → ambil koordinat POI.
- **Tahap 2, Navigasi:** kirim satu frame ke VPS → estimasi pose 6-DoF → *lokalisasi berhasil?*
  (Tidak: pindai area lain, kembali) → selaraskan koordinat ARCore dengan gedung → NavMesh menghitung
  jalur → tampilkan jalur AR, ARCore melacak → *sampai tujuan?* (Ya: Selesai) → *waktunya koreksi
  berkala?* (Ya: kirim frame lagi, Tidak: lanjut tampilkan jalur).

**Pelajaran membuat gambar dengan model AI:** tulis setiap panah dengan asal dan tujuan eksplisit,
jangan ada judul di dalam gambar, lalu **edit manual**. Regenerasi memperbaiki sebagian dan merusak
bagian lain.

## 12. Yang masih terbuka

- [ ] Keputusan ACC judul.
- [ ] Gedung dan koridor uji, serta izin memotret.
- [ ] Pertanyaan untuk pembimbing (`docs/spike-plan.md` bagian 9).
- [ ] Makna "anchoring tool untuk titik tujuan". Tafsiran saat ini: dashboard web untuk menandai POI
      di denah.
- [ ] Apakah ada aturan HKI kampus atau rencana paten tim yang bertabrakan dengan lisensi terbuka.
- [ ] Status resmi template dokumen pengajuan (tanpa Abstrak, tanpa Batasan Masalah, Daftar Pustaka
      setelah tanda tangan).
