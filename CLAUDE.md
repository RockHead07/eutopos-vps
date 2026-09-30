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

🔓 **Pengembangan boleh dimulai sebelum ACC** (keputusan pemilik repo, 2026-09-29). Alasannya: di PENS
judul biasanya di-ACC dengan sedikit penyesuaian arah, dan judul PA sengaja tidak mengunci teknologi.
Penghalang yang lebih penting adalah **hasil spike**, jadi setiap pekerjaan diberi penghalang sendiri:

| Pekerjaan | Mulai sekarang? | Alasan |
|---|---|---|
| Data lapangan untuk spike | ✅ Prioritas utama | Satu-satunya yang menjawab apakah VPS jalan di lorong PENS |
| Kerangka server (`server/`: FastAPI `/localize` dan `/health`, Docker Compose, PostgreSQL) | ✅ Ya | Kontrak API dan infrastruktur tetap dipakai apa pun metode lokalisasinya |
| Dashboard anchoring tool (POI di denah) | ✅ Ya | Dijanjikan di pengajuan, tidak bergantung hasil VPS |
| Aplikasi navigasi (`eutopos-mobile`, `Shared` dan `Navigation`) | 🟡 Bagian dasar | Sesi ARCore, klien API, POI. Loop koreksi VPS menunggu hasil spike |
| Aplikasi capture (eutopos Mapper) | ⏸️ Tunggu | Keputusan terbuka nomor 1 di spesifikasi: masuk cakupan PA atau tidak, diputuskan bersama pembimbing |

Riwayat: 2026-09-20 tidak ada pengembangan sebelum ACC; 2026-09-25 pengecualian uji coba awal di
lantai 10; 2026-09-29 dicabut dengan penghalang per pekerjaan di atas. Pengajuan judul masih menunggu
ACC. Kode uji coba ada di `spike/`, data di `data/` (tidak masuk git).

**Posisi terakhir (2026-09-28):** pipeline, pengukuran latensi hangat (`bench_localize.py`, CPU dan
GPU), dan penilai galat meter (`eval_meter.py`) sudah jalan di data contoh, di laptop dan PC lab.
Menunggu foto lorong lantai 10 beserta titik acuan. Rincian: `docs/spike-plan.md`, "Status terakhir"
dan bagian-bagian hasil sesudahnya.

**Prioritas tetap spike satu koridor** (`docs/spike-plan.md`). Spike menjawab dua hal: apakah akurasi
≤ 1,0 m pada ≥ 70% foto uji, dan berapa latensi per lokalisasi di server tanpa GPU. Pekerjaan yang
bergantung pada metode lokalisasi menunggu jawaban itu (tabel di atas).

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
- **`main` hanya lewat pull request** (keputusan pemilik repo, 2026-09-27). Ruleset `main-protection`
  menolak push langsung dari siapa pun dan mewajibkan check `Python lint and format` serta
  `Workflow security audit` lolos. Alurnya: branch, push, `gh pr create`, tunggu CI hijau, lalu
  `gh pr merge --rebase --delete-branch`. Tanpa reviewer wajib. Jangan menyalakan auto-merge.
- **Branch berumur pendek** (trunk-based development, keputusan pemilik repo, 2026-09-27). Satu unit
  kerja yang sudah terverifikasi = satu branch = satu PR, di-merge **hari itu juga**. Perbaikan kecil
  yang berkaitan digabung jadi satu unit. **Tidak ada branch jangka panjang** per fase atau per
  eksperimen. Dasar: [DORA](https://dora.dev/capabilities/trunk-based-development/) (merge ke trunk
  minimal sekali sehari, umur branch beberapa jam) dan
  [trunkbaseddevelopment.com](https://trunkbaseddevelopment.com/). PR dipertahankan walau pengembang
  tunggal karena beberapa sesi agen bekerja di repo yang sama. CI hanya menahan kesalahan lint,
  format, dan keamanan workflow (`ruff`, `zizmor`), **bukan kesalahan logika**. Perubahan kode tetap
  harus diverifikasi dengan menjalankannya sebelum PR dibuat.
- **Satu sesi, satu worktree.** Checkout utama dipakai beberapa sesi sekaligus, jadi **jangan
  berpindah branch di sana**: itu memindahkan branch sesi lain. Kerjakan setiap unit di
  [`git worktree`](https://git-scm.com/docs/git-worktree) sendiri dari `origin/main`, lalu hapus
  worktree-nya setelah PR di-merge. **Letakkan worktree di path pendek `D:/wt/<nama>`**: path berkas
  skill di `.claude/` sudah panjang, dan di bawah folder yang dalam (misalnya scratchpad) Windows
  menolak membuat maupun menghapusnya ("Filename too long").

  ```bash
  git fetch && git worktree add -b <branch> D:/wt/<nama> origin/main
  # ... kerjakan, commit, push, PR, merge ...
  git worktree remove D:/wt/<nama> && git branch -D <branch>
  ```
- **Kalau terpaksa bekerja di checkout utama:** sebelum staging, periksa `git diff <berkas>`.
  `git add <berkas>` ikut memasukkan perubahan sesi lain di berkas yang sama. Kalau ada perubahan
  yang bukan milikmu, jangan commit berkas itu dan tanyakan ke pemilik repo.
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
| `docs/field-test-runbook.md` | Panduan kerja lapangan uji lantai 10: persiapan, jadwal, cara merekam video peta (jalur ular dua arah), titik acuan, formulir, perintah setelahnya |
| `docs/design-notes.md` | Desain: dua lapis posisi, rumus penyelarasan ARCore ke gedung, sistem koordinat, model data, rute, metrik evaluasi, kontrak API |
| `docs/research-paper.md` | Semua rujukan penelitian beserta tautan, perannya di proyek, lisensi, status verifikasi, dan kandidat cadangan |
| `docs/multi-map-localization-research.md` | Riset memilih peta area untuk foto uji dan mengelola banyak peta area: praktik riset dan industri, prinsip, rekomendasi bertahap |
| `docs/specs/2026-09-29-capture-and-map-pipeline-design.md` | Spesifikasi aplikasi capture dan pipeline peta: komponen, tech stack, alur data, model peta, privasi, tahapan, hal yang harus dibuktikan, keputusan terbuka, struktur repo (`eutopos-vps` dan `eutopos-mobile`) |
| `docs/ci-cd.md` | CI yang berjalan sekarang, perintah pemeriksaan lokal, rencana build dan deployment, dan pengaturan GitHub yang wajib diaktifkan |
| `deploy/README.md` | Menyiapkan host (WSL2, Docker Engine, NVIDIA Container Toolkit) dan menjalankan layanan dengan Docker Compose |
| `docs/figures/` | Gambar 1 (arsitektur) dan Gambar 2 (alur) dokumen pengajuan |
