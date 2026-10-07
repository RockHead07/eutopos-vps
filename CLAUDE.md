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

✅ **Judul PA diterima di MIS (2026-09-30)**, tanpa perubahan judul, dengan kedua pembimbing seperti
usulan. Tahap berikutnya: seminar proposal (15 Desember 2026), lalu seminar hasil. Penghalang yang
tersisa adalah **hasil spike**, jadi setiap pekerjaan tetap diberi penghalang sendiri:

| Pekerjaan | Mulai sekarang? | Alasan |
|---|---|---|
| Data lapangan untuk spike | ✅ Prioritas utama | Satu-satunya yang menjawab apakah VPS jalan di lorong PENS |
| Kerangka server (`server/`: FastAPI `/localize` dan `/health`, Docker Compose, PostgreSQL) | ✅ Ya | Kontrak API dan infrastruktur tetap dipakai apa pun metode lokalisasinya |
| Dashboard anchoring tool (POI di denah) | ✅ Ya | Dijanjikan di pengajuan, tidak bergantung hasil VPS |
| Aplikasi navigasi (`eutopos-mobile`, `Shared` dan `Navigation`) | 🟡 Bagian dasar | Sesi ARCore, klien API, POI. Loop koreksi VPS menunggu hasil spike |
| Aplikasi capture (eutopos Mapper) | ⏸️ Tunggu | Keputusan terbuka nomor 1 di spesifikasi: masuk cakupan PA atau tidak, diputuskan bersama pembimbing |

Riwayat: 2026-09-20 tidak ada pengembangan sebelum ACC; 2026-09-25 pengecualian uji coba awal di
lantai 10; 2026-09-29 dicabut dengan penghalang per pekerjaan di atas; 2026-09-30 judul diterima.
Kode uji coba ada di `spike/`, data di `data/` (tidak masuk git).

**Posisi terakhir (2026-10-07):**
- Spike: pipeline, pengukuran latensi hangat, dan penilai galat meter jalan di data contoh (laptop dan
  PC lab). Rincian: `docs/spike-plan.md`.
- Uji video lantai 10 (tanpa titik acuan): jalur ular (2026-09-30) membuat peta pecah 3 potongan,
  20/46 query diterima. **Jalur keliling menghadap ke dalam (2026-10-01): 401/402 frame dalam satu
  peta, 36/46 query dari hari lain diterima (≥ 50 inlier)**, tidak ada pose janggal yang lolos ambang.
  Pola keliling jadi pola rekam utama di runbook. **Belum ada akurasi meter:** rekam dengan pola ini
  sekaligus titik acuan. Rincian: `docs/spike-plan.md` bagian "Uji video lantai 10".
- Layanan: `server/` (FastAPI `/localize`, `/health`), Docker Compose + PostgreSQL (versi peta per
  area), **antrean bangun peta** (`map_job`, pekerja GPU, `python -m server.manage job`), dan
  **unggahan video** (tusd, hook ke api, autentikasi Cloudflare Access, terverifikasi di PC lab
  2026-10-02 dengan `server.upload_client`), dan **akses dari internet** lewat Cloudflare Tunnel +
  Access di `eutopos.rockhead07.tech` (`deploy/compose.tunnel.yaml`). **Dashboard** (PR 3) di `web/`,
  disajikan FastAPI dari `/`, berbahasa Inggris: Overview, daftar pekerjaan, unggah video, detail
  pekerjaan dengan tampilan 3D, versi peta dan Publish. Tampil lewat Access di PC lab 2026-10-03.
  **Unggah dari `/new/` lulus 2026-10-04** (video 540 MB dari HP lewat Cloudflare Access, 11 potongan 50 MiB,
  satu koneksi putus dilanjutkan otomatis, peta 157/172 frame dalam 3 menit 26 detik).
  `/localize` lewat container terverifikasi di PC lab dengan peta demo: 405 inlier, 1,94 s CPU.
  Website unggah (PR 2 sampai 4) mengikuti `docs/specs/2026-10-01-web-upload-and-map-build-design.md`.
- PC lab sudah jadi host: WSL2 Ubuntu 24.04, Docker Engine, NVIDIA Container Toolkit, GPU terlihat
  dari dalam container. WSL menyala sendiri setelah boot tanpa login (Task Scheduler), dan SSH masuk lewat
  Tunnel + Access di `ssh-eutopos.rockhead07.tech` (`deploy/README.md` bagian 8).
- **CI/CD (2026-10-04):** CI menjalankan lint, audit workflow, dan unit test di dalam image Docker yang sama
  dengan yang dijalankan PC lab (`docs/ci-cd.md`). **Deploy otomatis model pull**: timer systemd di PC lab
  menjalankan `deploy/autodeploy.sh` tiap 5 menit, men-deploy `main` hanya kalau tiga check lolos dan tidak ada
  pekerjaan bangun peta yang berjalan, membandingkan dengan commit yang terakhir ter-deploy (bukan checkout),
  dan rollback kalau `/health` gagal (`deploy/README.md` bagian 9,
  `docs/specs/2026-10-04-pull-deploy-design.md`). GitHub tidak pernah memegang kunci ke PC lab.
- **Dashboard:** palet sage, Plus Jakarta Sans, ikon native `web/public/icons` lewat `web/lib/Icon.tsx`
  (CSS mask), favicon dari logo proyek. Hanya data nyata dari `/api/*`.
- **SIFT vs ALIKED (2026-10-05):** uji 2 x 2 di data lantai 10 menunjukkan **matcher yang menentukan**, bukan
  feature: SIFT dan ALIKED sama-sama gagal dengan nearest neighbor + ratio test (0/46) dan sama-sama berhasil dengan
  LightGlue (401/402 frame, 36/46 foto uji, 36 foto yang sama). Penjelasan: `docs/sift-vs-aliked.md`.
- **Rujukan Proposal PA:** `docs/research-paper.md` bagian 10, 18 rujukan 2021-2026 yang diverifikasi ke Crossref
  dan abstrak.
- **Dashboard dan API (2026-10-05 sampai 06, PR #46 sampai #53):** Tailwind v4 dan shadcn/ui resmi (aturan 6),
  kolom tanggal, filter dan sort, menu aksi per baris dengan Properties, dan menu akun di topbar. API: `GET /api/me`,
  `DELETE /api/jobs/{id}` dan `DELETE /api/versions/{id}` (khusus admin, api hanya menandai dan pekerja yang menghapus
  karena `/maps` hanya-baca di container api), `recorded_at` per video (dibaca dari isi video sebelum videonya
  dihapus), dan pratinjau frame pertama (`has_preview`, `GET /api/jobs/{id}/preview`).
  `EUTOPOS_ADMINS` di `deploy/.env` PC lab menentukan siapa admin (kosong = tidak ada yang boleh menghapus);
  sudah diisi 2026-10-06. Pratinjau job lama sudah diisi dengan `python -m server.manage previews`.
  **Belum:** UI Delete dengan consent di Jobs dan Maps, desain ulang Properties, foto pratinjau per map di UI, dan
  header Overview (pengerjaannya diserahkan ke agy, hanya `web/`).
- **Arahan Pembimbing 2, 4 sampai 7 Okt:** limitasi COLMAP, kamera 360, SIFT vs ALIKED, lorong minim fitur, jumlah
  point cloud sebagai ukuran detail, lalu komparasi GPU dan CPU per konfigurasi (ringkasan di `docs/pa-context.md`
  bagian 4, catatan di `docs/supervision-plan.md` bagian 6). **Laporan seterusnya di grup Bimbingan PA.**
- **Pengukuran CPU dan GPU:** `spike/bench_usage.py` (PR #54) dan `docs/specs/2026-10-07-cpu-gpu-usage-benchmark-design.md`.
  Skrip selesai dan terverifikasi (24 tes), **belum dijalankan di PC lab**; hasil menunggu pengukuran.
- **Kamera 360:** PRD di `docs/prd/2026-10-05-360-capture-support.md`, belum ada rekaman rute lantai 10.
- Rancangan setelahnya: `docs/specs/2026-09-29-capture-and-map-pipeline-design.md`.

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
- **Ekstraksi SIFT hanya jalan di CPU** di instalasi kita: `pycolmap.has_cuda` bernilai `False`. Jangan menulis
  perbandingan GPU lawan CPU untuk SIFT sebagai angka.
- **`time.process_time()` tidak menghitung proses anak.** hloc memuat gambar di pekerja DataLoader terpisah, jadi
  pemakaian CPU ekstraksi terlihat 0,01 inti padahal 1,08 inti. Pakai `resource.getrusage(RUSAGE_CHILDREN)` di Linux.
- **Jangan menjalankan `docker compose config` di PC lab:** ia mencetak variabel yang sudah diperluas, termasuk
  kata sandi Postgres. Periksa GPU atau variabel lewat `docker compose exec`, dan jangan mencetak isi `deploy/.env`.

## Aturan repo publik

Repo ini **publik** dan berlisensi **AGPL-3.0**.

- **Jangan pernah commit:** NRP atau data pribadi, foto gedung dan data lapangan, nama server
  internal, alamat IP, endpoint, kunci API, atau kredensial.
- `data/`, `outputs/`, dan `docs/papers/` sudah di-gitignore. Simpan PDF paper di `docs/papers/`
  secara lokal saja.
- Koordinat titik acuan gedung ditanyakan dulu ke pembimbing sebelum dipublikasikan.
- **Naskah PA (proposal, laporan, catatan administrasi) ada di repo privat terpisah**, bukan di sini.
  Jangan menyalin isinya ke repo ini. Dokumen teknis dan hasil uji tetap di repo ini (`docs/`).

## Aturan git

- Commit hanya kalau pemilik repo memintanya. Push hanya dengan perintah terpisah.
- **`main` hanya lewat pull request** (keputusan pemilik repo, 2026-09-27). Ruleset `main-protection`
  menolak push langsung dari siapa pun dan mewajibkan tiga check lolos: `Python lint and format`,
  `Workflow security audit`, dan `Tests (Docker)` (84 unit test dijalankan di dalam image layanan). Alurnya: branch, push, `gh pr create`, tunggu CI hijau, lalu
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

## Aturan untuk semua asisten AI (termasuk Antigravity / agy)

Berlaku untuk setiap agen yang bekerja di repo ini. Aturan ini lahir dari kejadian nyata: dashboard yang menampilkan
angka karangan (92,4%, 1.420 query, VRAM 4,2 GB, daftar job palsu, banner "cached telemetry" padahal tidak ada
cache, dan label "96,8% (36/46)" padahal 36/46 = 78%), laporan "berhasil" untuk hal yang tidak dijalankan,
perintah tambahan yang tidak dilaporkan (`Stop-Process -Name git -Force`, percobaan elevasi), dan penambahan
Tailwind dan `lucide-react` tanpa izin.

1. **Tidak ada data karangan.** Setiap angka, nama, tanggal, status, atau grafik di UI, dokumen, dan laporan harus
   berasal dari data nyata (API, berkas hasil, log) atau sumber yang disebut. **Dilarang:** nilai cadangan yang
   tampak nyata (`?? 401`, `|| 1420`), array grafik tulisan tangan, daftar contoh yang menyerupai data, status
   tetap ("Online", "Welcome back, Admin"), dan banner yang menyatakan hal yang tidak terjadi. Kalau datanya belum
   ada: tampilkan keadaan kosong yang jujur ("No data yet") atau jangan tampilkan kartunya. Mockup hanya boleh
   dengan label "contoh" yang jelas dan tidak boleh di-merge.
2. **Tidak ada rujukan gaib.** Setiap paper yang dikutip harus punya DOI yang cocok di Crossref (penulis, tahun,
   venue, halaman) dan isi klaimnya dicocokkan ke abstrak atau teks. Tulis tingkat verifikasinya. Kalau tidak
   bisa diverifikasi, katakan, jangan menebak.
3. **Bedakan yang diukur dari yang diduga.** Tandai dugaan sebagai dugaan. Jangan menyimpulkan sebab dari satu
   eksperimen yang mengubah dua hal sekaligus (contoh: kesimpulan "ALIKED lebih baik" yang ternyata soal matcher).
4. **Laporan berisi bukti mentah.** Setiap klaim "selesai" atau "berhasil" disertai output perintah apa adanya,
   bukan ringkasan. **Setiap penyimpangan dan perintah tambahan wajib dilaporkan.** Jangan menulis "berhasil"
   untuk hal yang tidak dijalankan. "Tidak tahu" atau "tidak bisa memverifikasi" lebih baik daripada tebakan yang
   meyakinkan.
5. **Verifikasi sebelum klaim.** Baca berkas sebelum menyebut isinya, jalankan kodenya, buka halamannya, cek lognya.
   Perubahan UI diperiksa di browser (lebar desktop dan ponsel), bukan hanya `tsc` dan `build`.
6. **Prinsip Ponytail: tanpa dependensi baru tanpa izin pemilik repo.** Dashboard memakai Tailwind v4 dan
   shadcn/ui resmi (disetujui pemilik repo, 2026-10-05). Komponen baru ditambahkan lewat CLI
   (`npx shadcn@latest add <nama>`), bukan ditulis ulang tangan. Palet eutopos ada di `web/app/globals.css` dan
   variabel shadcn dipetakan ke sana, jangan memakai warna bawaan shadcn. Ikon aplikasi tetap dari
   `web/public/icons/*.svg` lewat `web/lib/Icon.tsx`. **Dilarang** menambah pustaka UI atau chart lain di luar
   shadcn (grafik tetap SVG/CSS buatan sendiri). Dependensi lain di `web/package.json` hanya bila diminta.
7. **Kerjakan tepat yang diminta.** Gagasan lain disampaikan sebagai usulan, bukan dikerjakan. Jangan mengubah
   arah desain, arsitektur, atau cakupan sendiri.
8. **Git:** satu sesi satu worktree di `D:/wt/<nama>`, **jangan membuat atau berpindah cabang di checkout utama**.
   Commit dan push hanya atas perintah. **Jangan merge PR, jangan menghapus cabang, jangan mematikan proses
   (`Stop-Process`, `kill`) tanpa izin.** Cabang lokal yang berisi commit belum di-push dicadangkan dulu
   (`git bundle`) sebelum dihapus.
9. **PC lab, Cloudflare, dan rahasia:** membaca boleh, mengubah (docker, systemd, Task Scheduler, `cf`) tanya dulu.
   Jangan mencetak isi `deploy/.env`, awal `docker compose logs tusd` (memuat rahasia hook), token, atau kunci.
   Jangan meminta atau menangani password. Jangan mengangkat hak akses atau membuat akun.
10. **Istilah teknis tetap bahasa Inggris** (nearest neighbor, ratio test, matcher, descriptor, keypoint). Jangan
    menerjemahkannya paksa ke bahasa Indonesia.

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
| `docs/supervision-plan.md` | Rencana bimbingan menuju seminar proposal (15 Desember 2026): yang dicari tahu dulu, agenda bimbingan dengan usulan posisi, kemajuan yang ditunjukkan, jadwal, catatan hasil |
| `docs/spike-plan.md` | Rencana spike: data, varian, perangkat, ambang keputusan, pertanyaan untuk pembimbing |
| `docs/field-test-runbook.md` | Panduan kerja lapangan uji lantai 10: persiapan, jadwal, cara merekam video peta (pola keliling menghadap ke dalam sebagai pola utama sejak 2026-10-01), titik acuan, formulir, perintah setelahnya |
| `docs/design-notes.md` | Desain: dua lapis posisi, rumus penyelarasan ARCore ke gedung, sistem koordinat, model data, rute, metrik evaluasi, kontrak API (sesuai `server/app.py`) |
| `docs/research-paper.md` | Semua rujukan penelitian beserta tautan, perannya di proyek, lisensi, status verifikasi, dan kandidat cadangan |
| `docs/multi-map-localization-research.md` | Riset memilih peta area untuk foto uji dan mengelola banyak peta area: praktik riset dan industri, prinsip, rekomendasi bertahap |
| `docs/specs/2026-09-29-capture-and-map-pipeline-design.md` | Spesifikasi aplikasi capture dan pipeline peta: komponen, tech stack, alur data, model peta, privasi, tahapan, hal yang harus dibuktikan, keputusan terbuka, struktur repo (`eutopos-vps` dan `eutopos-mobile`) |
| `docs/specs/2026-10-01-web-upload-and-map-build-design.md` | Spesifikasi website unggah video dan pembangunan peta otomatis di PC lab: Cloudflare Tunnel + Access, tusd, antrean pekerjaan, pekerja GPU, dashboard, Terbitkan |
| `docs/web-upload-research.md` | Riset pendukung spesifikasi di atas: batas Cloudflare, protokol tus, FastAPI, antrean PostgreSQL, Access, plotly, Next.js static export |
| `docs/ci-cd.md` | CI yang berjalan sekarang, perintah pemeriksaan lokal, rencana build dan deployment, dan pengaturan GitHub yang wajib diaktifkan |
| `docs/plans/` | Rencana implementasi yang sudah dieksekusi (pekerja peta, unggahan dan autentikasi, dashboard), masing-masing dengan status dan nomor PR di bagian atas |
| `deploy/README.md` | Menyiapkan host (WSL2, Docker Engine, NVIDIA Container Toolkit), menjalankan layanan, antrean pekerjaan, unggahan tusd, Cloudflare Tunnel + Access, dan dashboard, beserta tabel jebakan |
| `web/` | Dashboard Next.js (static export). Dibangun di tahap Node pada `deploy/Dockerfile` |
| `docs/sift-vs-aliked.md` | SIFT vs ALIKED: cara kerja, matcher, hasil 2 x 2 di lantai 10, jumlah titik 3D, dan batas kesimpulan |
| `docs/specs/2026-10-05-job-delete-and-account-design.md` | Kontrak API: tanggal job, `GET /api/me`, penghapusan job dan versi (admin, pekerja yang menghapus) |
| `docs/specs/2026-10-06-recorded-date-and-preview-design.md` | Waktu rekam dari isi video dan pratinjau frame pertama: keputusan, kontrak API, cara mengisi job lama |
| `docs/specs/2026-10-07-cpu-gpu-usage-benchmark-design.md` | Rancangan pengukuran pemakaian CPU dan GPU (konfigurasi, noise, metrik, batas) yang ditetapkan sebelum hasil |
| `docs/prd/` | PRD pekerjaan terencana: dukungan video 360 |
| `docs/figures/` | Gambar 1 (arsitektur) dan Gambar 2 (alur) dokumen pengajuan |
