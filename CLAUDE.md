# CLAUDE.md — eutopos-vps

Baca berkas ini lebih dulu di setiap sesi baru. Setelah itu baca `docs/pa-context.md` (judul,
riwayat, arahan pembimbing, keputusan), lalu `docs/spike-plan.md`, `docs/design-notes.md`, dan
`docs/research-paper.md`. Jangan mengandalkan ingatan dari sesi lain: keputusan di sini bisa berubah
karena arahan pembimbing datang bertahap.

## Apa ini

**eutopos-vps** adalah layanan **Visual Positioning System (VPS) lokal**: ponsel mengirim satu foto
kamera, server mengembalikan posisi dan orientasi kamera (pose 6-DoF) dalam koordinat gedung.
Tanpa QR code, tanpa penanda fisik, tanpa layanan cloud pihak ketiga.

Nama: Yunani *eu* (baik) + *topos* (tempat), "tempat yang baik". Diambil dari makna nama pembuatnya,
*Bagus*.

Repo ini bagian dari **Proyek Akhir (PA) D3 Teknik Informatika, PENS PSDKU Lamongan**, berjudul
*Platform Indoor Navigation Terintegrasi AI Avatar Assistant Berbasis Retrieval-Augmented
Generation*. Pembimbing: Sritrusta Sukaridhoto dan Evianita Dewi Fajrianti. Lokasi uji: gedung PENS
pusat, Surabaya.

## Status

🔒 **Tahap perencanaan. Tidak ada pengembangan sebelum judul PA di-ACC.** Keputusan pemilik repo.
Pengajuan judul sudah diunggah, menunggu keputusan. Sampai ACC, yang boleh dilakukan hanya menyusun
dokumen, bertanya ke pembimbing, dan mengurus izin lokasi.

**Langkah pertama setelah ACC: spike satu koridor** (`docs/spike-plan.md`). Spike menjawab dua hal:
apakah akurasi ≤ 1,0 m pada ≥ 70% foto uji, dan berapa latensi per lokalisasi di server tanpa GPU.
Semua pekerjaan lain menunggu jawaban itu.

## Posisi dalam platform PA

```text
[Ponsel Android, Unity + ARCore]                   [Server instansi]
 ARCore melacak gerak terus-menerus  --1 foto-->   eutopos-vps: hloc + LightGlue + PnP
 koreksi posisi berkala              <--pose 6-DoF--  peta 3D (COLMAP), koordinat gedung
 NavMesh menghitung rute di aplikasi
```

VPS **bukan** pelacak terus-menerus. VPS memberi **koreksi berkala** atas drift ARCore. Pola ini
sudah dipublikasikan (VIO-APR, MobileARLoc, lihat `docs/research-paper.md`).

Komponen PA lain (aplikasi Unity, AI avatar, RAG, anchoring tool) **tidak** ada di repo ini.

## Arah yang mengikat

1. **Fully local.** Semua layanan berjalan di infrastruktur instansi. Tidak ada VPS komersial
   berbasis cloud (MultiSet, Immersal, Google), tidak ada Cloud Anchors atau Geospatial API.
2. **ARCore boleh, fitur on-device saja** (motion tracking).
3. **Mobile (Android) dulu.** Mixed Reality di luar cakupan PA.
4. **Klaim "tanpa GPU" hanya sah kalau diukur di perangkat tanpa GPU.** Hasil dari PC dengan GPU
   adalah pembanding pengembangan, bukan bukti untuk server.

## Stack yang diincar

| Lapisan | Pilihan | Status |
|---|---|---|
| Bahasa | Python 3.12 | ✅ |
| Pipeline | hloc (Apache-2.0) | ✅ |
| Peta 3D | pycolmap / COLMAP (BSD) | ✅ |
| Fitur + pencocok | `aliked+lightglue`, pembanding `disk+lightglue` | ⚠️ ditentukan spike |
| Retrieval global | MegaLoc (kode MIT), pembanding NetVLAD | ⚠️ lisensi bobot belum dicek |
| Penyelarasan ke denah | `pycolmap.estimate_sim3d_robust` + titik acuan terukur | ✅ |
| API | FastAPI | ✅ |
| Deploy | Docker, PyTorch CPU | ⚠️ tergantung latensi |

## Jebakan yang sudah ditemukan

- 🚨 **Lisensi SuperPoint dan SuperGlue non-komersial.** Hampir semua tutorial hloc memakainya.
  Pakai ALIKED atau DISK + LightGlue.
- 🚨 **ACE, GLACE, Reloc3r, Map-free: lisensi non-komersial.** F³Loc: repo tanpa berkas lisensi.
  Jangan dipakai di platform tanpa keputusan pembimbing.
- **XFeat tidak punya konfigurasi bawaan di hloc**, perlu integrasi manual.
- **Peta dari foto satu kamera tidak punya skala meter.** Titik acuan terukur wajib ada.
- **Video GoPro MAX berformat `.360` (proyeksi EAC)**, bukan equirectangular. Harus diekspor dulu.
- **Latensi hloc di CPU belum pernah diukur** di sumber mana pun. Jangan mengutip angka tanpa sumber.

## Aturan repo publik

Repo ini **publik** dan berlisensi **AGPL-3.0**.

- **Jangan pernah commit:** NRP atau data pribadi, foto gedung dan data lapangan, nama server
  internal, alamat IP, endpoint, kunci API, atau kredensial.
- `data/`, `outputs/`, dan `docs/papers/` sudah di-gitignore. Simpan PDF paper di `docs/papers/`
  secara lokal saja.
- Koordinat titik acuan gedung ditanyakan dulu ke pembimbing sebelum dipublikasikan.

## Aturan git

- Commit hanya kalau pemilik repo memintanya. Push hanya dengan perintah terpisah.
- **Jangan pernah mencantumkan atribusi AI** di commit atau PR: tanpa `Co-Authored-By`, tanpa footer
  "Generated with", tanpa tautan sesi. Author dan committer selalu pemilik repo.

## Cara kerja yang diharapkan

- **Verifikasi ke sumber primer** (paper, repo resmi, dokumentasi) sebelum menulis klaim. Tandai ⚠️
  yang belum terverifikasi.
- **Sebutkan best practice lebih dulu**, baru komprominya.
- **Jangan membangun ulang yang sudah ada.** COLMAP dan hloc mengerjakan SfM dan lokalisasi. Repo ini
  hanya merangkai, mengukur, dan melayankan.
- **Tanpa em dash** di teks untuk pemilik repo.

## Peta dokumen

| Berkas | Isi |
|---|---|
| `docs/pa-context.md` | Konteks PA: judul final dan riwayatnya, arahan pembimbing, isi dokumen pengajuan, isu Proposal PA, keputusan, pelajaran, dan yang masih terbuka |
| `docs/spike-plan.md` | Rencana spike: data, varian, perangkat, ambang keputusan, pertanyaan untuk pembimbing |
| `docs/design-notes.md` | Desain: dua lapis posisi, rumus penyelarasan ARCore ke gedung, sistem koordinat, model data, rute, metrik evaluasi, kontrak API |
| `docs/research-paper.md` | Semua rujukan penelitian beserta tautan, perannya di proyek, lisensi, status verifikasi, dan kandidat cadangan |
| `docs/figures/` | Gambar 1 (arsitektur) dan Gambar 2 (alur) dokumen pengajuan |
