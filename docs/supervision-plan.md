# Rencana Bimbingan Menuju Seminar Proposal

> Dibuka di HP saat bimbingan. **Jangan dibaca urut seperti naskah.** Pelajari sebelumnya, lirik kalau
> buntu, dan tatap lawan bicara. Konteks lengkap: `docs/pa-context.md`.

**Posisi (2026-09-30):** judul diterima di MIS, tanpa perubahan judul, dengan kedua pembimbing sesuai
usulan. **Seminar proposal: 15 Desember 2026** (±11 minggu). Proposal PA adalah dokumen terpisah dari
pengajuan judul.

## 1. Dicari tahu sebelum bimbingan pertama

Belum tercatat di dokumen mana pun, dan menentukan bentuk proposal. Tanyakan ke prodi atau kakak
tingkat yang sudah seminar proposal.

- [ ] **Template dan persyaratan proposal PA** dari jurusan. Template resmi selalu menang atas struktur
      buatan sendiri.
- [ ] **Kartu atau log bimbingan:** wajib atau tidak, dan minimal berapa kali sebelum seminar.
- [ ] **Pembimbing di MIS sudah penetapan Kaprodi atau belum.** Pembimbing final ditetapkan Kaprodi
      setelah ACC, tidak otomatis mengikuti usulan.

## 2. Agenda bimbingan pertama setelah ACC

Urutan menurut seberapa banyak pekerjaan yang tertahan menunggu jawabannya. Kolom "usulan kita" adalah
posisi awal yang kita tawarkan, bukan keputusan. Isi kolom "keputusan" sesudah bimbingan.

| # | Topik | Pertanyaan | Usulan kita | Keputusan |
|---|---|---|---|---|
| 1 | **Cakupan PA** | Mana yang inti dan mana yang pendukung? Apakah aplikasi capture (pembaruan peta dari ponsel) masuk PA? | Inti: VPS lokal, navigasi dengan koreksi posisi, RAG yang menghasilkan POI, anchoring tool. Pendukung: avatar dan suara. Aplikasi capture **di luar PA**: peta dibuat dengan kamera bawaan + skrip, rancangan aplikasi capture masuk bab pengembangan lanjutan | |
| 2 | **Target evaluasi** | Target di pengajuan sudah pas? | Tetap: galat ≤ 1,0 m pada ≥ 70% pengujian, POI oleh RAG ≥ 80% dari 50 pertanyaan yang disusun pihak lain, SUS ≥ 68. Latensi diisi angka setelah spike | |
| 3 | **Infrastruktur** | Boleh memakai PC lab (GPU) untuk pengembangan dan sebagai host layanan? Batasan "server tanpa GPU" dipertahankan? | PC lab untuk membangun peta (butuh GPU, ±3,5 menit per area). Lokalisasi diukur di CPU dan GPU, keduanya dilaporkan | |
| 4 | **Izin lapangan** | Izin merekam di lantai 10, jam yang boleh, dan permintaan denah | Pagi sebelum ramai. Denah dipakai untuk anchoring dan penyelarasan peta | |
| 5 | **Model bahasa** | Gateway LLM milik lab dihitung "instansi"? | Ya, tanpa fallback ke layanan cloud | |
| 6 | **Administrasi** | Jadwal bimbingan rutin, kartu bimbingan, template proposal (kalau belum terjawab di bagian 1) | Bimbingan tiap 2 minggu | |

**Pertanyaan cadangan** (kalau waktu masih ada, dari `docs/spike-plan.md` bagian 9):
- Lisensi non-komersial (ACE, GLACE, Reloc3r) dianggap masalah untuk platform PA?
- "Bisa di mana saja" berarti titik mana pun, atau cukup titik yang punya penanda alami?
- Pembanding VPS komersial boleh dipakai hanya sebagai pembanding pengujian, bukan di dalam platform?

## 3. Kemajuan yang ditunjukkan

Tunjukkan yang sudah terbukti, sebut juga yang belum. Jangan melebih-lebihkan.

- **Layanan lokalisasi berjalan** di server lokal (container, PC lab): satu foto masuk, pose keluar
  dalam ±2 detik di CPU dan ±0,15 detik di GPU (data contoh).
- **Uji video pertama di lantai 10:** peta terbangun dari video dalam ±3,5 menit. Pose yang salah hanya
  punya 6 sampai 9 titik cocok, jauh di bawah ambang 50, jadi **tersaring dan tidak ditampilkan**.
- **Masalah yang ditemukan dan penyebabnya:** peta putus di belokan cepat dan saat kamera menghadap
  dinding polos. Cara merekam sudah diperbaiki di panduan lapangan.
- **Belum ada:** angka akurasi dalam meter. Butuh rekaman ulang dengan titik acuan terukur.

## 4. Rencana bimbingan sampai seminar (perkiraan)

| Bimbingan | Kapan | Bahan yang dibawa | Yang diminta dari pembimbing |
|---|---|---|---|
| 1 | Awal Oktober | Agenda bagian 2, kemajuan bagian 3 | Keputusan cakupan, target, izin |
| 2 | Pertengahan Oktober | Kerangka proposal sesuai template, draf bab pendahuluan | Arah rumusan masalah dan batasan |
| 3 | Akhir Oktober | Draf tinjauan pustaka, angka akurasi meter pertama | Tanggapan atas hasil awal: lanjut atau ubah metode |
| 4 | Pertengahan November | Draf metodologi dan perancangan, hasil awal | Kelengkapan metodologi dan rencana studi pengguna |
| 5 | ±23 November | **Draf proposal lengkap** | Revisi sebelum seminar (tiga minggu) |
| 6 | Awal Desember | Slide dan latihan presentasi | Pertanyaan yang kemungkinan muncul |

**Jalur kritis:** rekaman ulang lantai 10 **dengan titik acuan meter**. Tanpa itu bagian hasil awal
kosong. Jangan ditunda lebih dari 1 sampai 2 minggu.

## 5. Isu proposal yang perlu dijawab di dokumen

Dari `docs/pa-context.md` bagian 7. Penguji kemungkinan menanyakan ini:

1. Cakupan terlalu besar untuk D3 (dijawab lewat agenda nomor 1).
2. **Kontribusi pribadi dipisahkan** dari proyek tim sebelumnya: apa yang baru.
3. Jumlah responden studi pengguna.
4. Tempat model bahasa dijalankan dan status "instansi"-nya.
5. Prosedur pemetaan ulang saat tata ruang berubah.
6. Area uji, cara mengukur ground truth, dan lisensi bobot retrieval.
7. Speech-to-text lokal sebagai pekerjaan baru.

## 6. Catatan hasil bimbingan

Salin blok ini untuk setiap bimbingan. Tulis sebagai parafrase, bukan kutipan percakapan.

```text
Tanggal:
Pembimbing:
Keputusan:
-
Tugas sampai bimbingan berikutnya:
-
Pertanyaan yang belum terjawab:
-
```
