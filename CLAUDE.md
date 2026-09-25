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

🔒 **Pengembangan penuh menunggu judul PA di-ACC.** Pengajuan sudah diunggah, menunggu keputusan.

🧪 **Pengecualian (keputusan pemilik repo, 2026-09-25): uji coba awal (dry run) boleh sebelum ACC**
di lorong lab **lantai 10 gedung PENS pusat**. Tujuannya membuktikan pipeline hloc bisa dipasang dan
berjalan, dan mengukur waktu lokalisasi di CPU. Hasilnya dilaporkan sebagai **uji coba awal**, bukan
hasil spike: belum mencakup area uji resmi, belum memakai titik acuan lengkap, dan diukur di laptop
(bukan server instansi). Kode uji coba ada di `spike/`, data di `data/` (tidak masuk git).

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
- **Sebelum commit, jalankan pemeriksaan CI secara lokal:** `uv run ruff check .` dan
  `uv run ruff format .` (rincian di `docs/ci-cd.md`).

## Skill proyek

Terpasang di `.claude/skills/`, sumbernya tercatat di `skills-lock.json` (perbarui dengan
`npx skills update -p`). Aturan di `CLAUDE.md` ini **selalu menang** kalau bertentangan dengan skill.

| Skill | Sumber | Pakai saat |
|---|---|---|
| `source-driven-development` | addyosmani/agent-skills | Menulis kode yang bergantung pada API hloc, pycolmap, FastAPI, atau PyTorch. Verifikasi ke dokumentasi resmi, lalu kutip |
| `fastapi` | fastapi/fastapi (resmi) | Membangun layanan `/localize` dan `/health` |
| `observability-and-instrumentation` | addyosmani/agent-skills | Mengukur latensi per tahap (metrik M7) dan mencatat kegagalan lokalisasi |
| `multi-stage-dockerfile` | github/awesome-copilot | Membuat image Docker PyTorch CPU untuk server instansi |
| `research-paper-writing` | Master-cai/Research-Paper-Writing-Skills | Menulis Proposal PA dan laporan: klaim harus punya bukti |

Skill global yang juga relevan: `ponytail` (anti over-engineering), `engineering:architecture` (ADR),
`superpowers:test-driven-development` dan `mattpocock-skills:tdd` (testing),
`mattpocock-skills:research` (riset ke sumber primer).

## Peta dokumen

| Berkas | Isi |
|---|---|
| `docs/pa-context.md` | Konteks PA: judul final dan riwayatnya, arahan pembimbing, isi dokumen pengajuan, isu Proposal PA, keputusan, pelajaran, dan yang masih terbuka |
| `docs/spike-plan.md` | Rencana spike: data, varian, perangkat, ambang keputusan, pertanyaan untuk pembimbing |
| `docs/design-notes.md` | Desain: dua lapis posisi, rumus penyelarasan ARCore ke gedung, sistem koordinat, model data, rute, metrik evaluasi, kontrak API |
| `docs/research-paper.md` | Semua rujukan penelitian beserta tautan, perannya di proyek, lisensi, status verifikasi, dan kandidat cadangan |
| `docs/ci-cd.md` | CI yang berjalan sekarang, perintah pemeriksaan lokal, rencana build dan deployment, dan pengaturan GitHub yang wajib diaktifkan |
| `docs/figures/` | Gambar 1 (arsitektur) dan Gambar 2 (alur) dokumen pengajuan |
