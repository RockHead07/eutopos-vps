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

**Posisi terakhir (2026-10-16):**
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
- **Dashboard dan API (2026-10-05 sampai 08, PR #46 sampai #61):** Tailwind v4 dan shadcn/ui resmi (aturan 6),
  kolom tanggal, filter dan sort, menu aksi per baris, dan menu akun di topbar. API: `GET /api/me`,
  `DELETE /api/jobs/{id}` dan `DELETE /api/versions/{id}` (khusus admin, api hanya menandai dan pekerja yang menghapus
  karena `/maps` hanya-baca di container api), `recorded_at` per video (dibaca dari isi video sebelum videonya
  dihapus), dan pratinjau frame pertama (`has_preview`, `GET /api/jobs/{id}/preview`).
  `EUTOPOS_ADMINS` di `deploy/.env` PC lab menentukan siapa admin (kosong = tidak ada yang boleh menghapus);
  sudah diisi 2026-10-06. Pratinjau job lama sudah diisi dengan `python -m server.manage previews`.
  **UI selesai dan ter-deploy (2026-10-07 sampai 08), semuanya dikerjakan agy dan diuji ulang di browser oleh Claude:**
  Properties berpadding dengan kartu terkelompok (#56), dropdown shadcn `Select` pengganti `<select>` bawaan (#56),
  lonceng notifikasi dari job nyata 7 hari terakhir dengan hitungan belum dibaca di `localStorage` (#56), sapaan
  Overview menurut jam (#56, lalu kumpulan 12 sampai 16 sapaan per waktu dan beberapa ekstra per hari, #61),
  kontrol Overview: pencarian, area, rentang tanggal yang memfilter kartu (#56), Delete dengan consent di Jobs dan Maps
  lewat satu `DeleteConsentDialog` (#57), thumbnail pratinjau dan kolom Recorded dan Uploaded (#57), sel Action yang
  menempel di kanan pada layar kecil (#57), tiga ikon `bell`, `search`, `calendar` (#58), `SearchBar` bergaya kaca
  dengan pintasan `/` dan Ctrl+/ serta `DateRangePicker` dengan seret-pilih (#59, menambah `react-day-picker` 10.0.2
  dan `date-fns` 4.4.0 dengan izin pemilik), dan perbaikan pita kalender, fokus search, dan sapaan (#61).
  **Belum:** lisensi per ikon di `web/public/icons/LICENSES.md`, teks dialog Delete untuk job gagal masih menyebut
  "rows of the job and version", klik pada rentang tanggal yang sudah lengkap memperluas tepi (bawaan
  react-day-picker, Clear untuk mulai ulang).
- **Arahan Pembimbing 2, 4 sampai 7 Okt:** limitasi COLMAP, kamera 360, SIFT vs ALIKED, lorong minim fitur, jumlah
  point cloud sebagai ukuran detail, lalu komparasi GPU dan CPU per konfigurasi (ringkasan di `docs/pa-context.md`
  bagian 4, catatan di `docs/supervision-plan.md` bagian 6). **Laporan seterusnya di grup Bimbingan PA.**
- **Pengukuran CPU dan GPU (2026-10-07, SELESAI):** `spike/bench_usage.py` (PR #54) dan
  `docs/specs/2026-10-07-cpu-gpu-usage-benchmark-design.md` (bagian 7 berisi hasilnya). Lima konfigurasi, GPU dan CPU,
  30 gambar dari 15 pasang frame lantai 10, tiga ulangan, lima variasi noise OpenCV. Ringkas: extraction ALIKED di GPU
  sekitar 17 kali lebih cepat (1,05 s dibanding 17,8 s untuk 30 gambar); SIFT hanya jalan di CPU; di CPU ALIKED
  dengan LightGlue memakai 110 core-seconds dan SIFT dengan LightGlue 33; inlier ALIKED + LightGlue tertinggi di
  antara setelan 1.024 keypoint dan SIFT bawaan COLMAP paling rapuh terhadap noise. **Laporan sudah terkirim ke grup
  Bimbingan PA pada 2026-10-08**; tiga tabel gambar (putih polos, berbahasa Inggris) ada di
  `outputs/usage/` (tidak masuk git, dibuat ulang oleh `outputs/usage/tables.py`).
- **Sejak 2026-10-08 (PR #62 sampai #68):**
  - **Dashboard operasional (#64, #65):** tahap pekerjaan (extract, build, inspect, register) dan panel kegagalan
    yang memisahkan ringkasan galat dari log pekerja, perbandingan dua versi peta dalam satu area, penanda versi yang
    dilayani `/localize`, chip peringatan disk, dan penanda koordinat peta (Metric atau Model) dari `GET /health`.
    Label menyebut "acceptance rate", **bukan akurasi lokalisasi** (belum diukur).
  - **Disk fisik di dashboard (#67):** container hanya melihat disk virtual WSL (batas 1 TB), padahal batas nyata
    adalah drive Windows di bawahnya (447 GB, sisa 132 GB saat itu; dashboard sempat menampilkan 904 GB). `deploy/autodeploy.sh`
    menulis `.host-disk.json` di samping peta tiap putaran timer; `GET /api/system` memuatnya sebagai `storage.host`
    (basi setelah 15 menit, bentuk tak masuk akal ditolak). Popover diagnostik memakai pengukur melingkar dan satu
    kalimat kesiapan membangun peta; `web/lib/storage.ts` memilih sisa ruang yang paling dekat ke batas kerasnya
    (20 GB untuk disk container sesuai `MIN_FREE_BYTES`, 30 GB untuk drive tuan rumah sesuai aturan proyek).
    Celah penjaga `server/worker.py` (hanya memeriksa disk virtual) ditutup di cabang
    `feat/worker-host-disk-guard` (PR terpisah, lihat butir 2026-10-14 sampai 16).
  - **Variasi luminance (#66, hasil di #68):** `spike/bench_usage.py` punya empat varian redup sintetis
    (`dim50`, `dim25`, `dim10`, `dim25-gauss10`; cahaya dikurangi pada cahaya linear, gamma 2,2) dan `prepare`
    mencatat kecerahan tiap varian di `manifest.json`. Hasil 2026-10-11 di `docs/specs/2026-10-07-cpu-gpu-usage-benchmark-design.md`
    bagian 7.6: urutan ketahanan sama di setiap tingkat redup (ALIKED + LightGlue 71% inlier tersisa pada cahaya 10%,
    SIFT bawaan COLMAP 46%); saat gelap ekstraktor yang paling menentukan (saat noise, matcher); gelap tidak mengubah
    kebutuhan sumber daya; **bukan akurasi lokalisasi, hanya rata-rata 15 pasang, redup sintetis bukan malam hari**.
    Tindak lanjut yang diusulkan: simpan inlier per pasang, rekaman sore dan malam asli.
  - **Stack avatar fully local (2026-10-11):** riset lisensi dan pengukuran di PC lab (STT, LLM, TTS, anggaran VRAM,
    uji RAG). Catatan lengkap ada di repo privat milik pemilik proyek, bukan di sini. Bahan uji ada di
    `~/avatar-bench` di PC lab (belum dibersihkan; volume Docker `avatar-bench-ollama` dan `avatar-bench-hf`, container
    `avatar-bench-py`). Avatar, TTS, dan RAG bukan kontribusi baru PA (diturunkan dari proyek tim).
- **2026-10-14 sampai 16:**
  - **#68 merged** (`f9afcc6`): hasil luminance di spesifikasi benchmark bagian 7.6.
  - **Arahan pembimbing 14 Okt:** buku PA menuntut **MVP indoor navigation yang berjalan** (lokalisasi di posisi 1
    dengan posisi dan arah hadap, set target posisi 2, uji navigasi); jurnal (yang direncanakan pembimbing) fokus
    **VPS dan lokalisasi**, data yang ada dianggap cukup; luminance butuh **data cahaya nyata** (lux) dan "mode
    switch"; tantangan berikutnya lokalisasi dan **barometer** (deteksi lantai, setelah satu lantai berjalan).
    Foto uji lantai 10 ternyata frame video tanpa EXIF, jadi terang adegan saat itu tidak bisa dihitung balik.
    Mode switch antar fitur butuh peta kedua per fitur (peta hanya bisa ditanya dengan fitur pembuatnya).
  - **Klien baru `eutopos-mobile`** (repo publik `RockHead07/eutopos-mobile`, AGPL-3.0): spesifikasi MVP
    navigasi satu lantai dan rencana implementasi ada di repo itu (`docs/specs/2026-10-15-mvp-navigasi-design.md`,
    `docs/plans/2026-10-15-mvp-navigasi.md`). Unity 6000.3.14f1, AR Foundation 6.3.4, ARCore 6.3.4, 4-DoF
    (yaw + XYZ), graf titik terukur + A*, service token Cloudflare Access. **Fase A (inti C#, 69 tes EditMode)
    merged** di repo itu; Fase B (aplikasi di ponsel) belum.
  - **Tambahan server untuk klien merged:** #69 (`3503b49`) `GET /navgraph` (graf per area di
    `<maps>/<area>/navgraph.json`, `server/navgraph.py`) dan `python -m server.manage align` (`server/alignment.py`,
    pasang `align.json` ke folder versi peta dan `navgraph.json` ke folder area, jalankan di container `worker`);
    #70 (`aa34918`) `python -m server.navgraph build` membuat `navgraph.json` dari `reference_points.csv`,
    `edges.csv`, `targets.csv`. Rencananya: `docs/plans/2026-10-15-navgraph-dan-align.md`.
  - **Service token Access `eutopos-mobile` aktif (diuji 2026-10-16):** dengan token `/health` 200 dan
    `/navgraph` 404 (graf belum dipasang); `/api/*` 403 dari `server/auth.py` (token tanpa email). Tanpa token
    semua 302. Nilainya hanya di `vps-token.local.json` proyek Unity (gitignored).
  - **Cabang kode yang sudah di-commit, PR terpisah:** `feat/bench-per-pair-inliers` (inlier per pasangan dan
    tabel pasangan di bawah 50 inlier), `feat/worker-host-disk-guard` (pekerja menolak job bila umpan drive host
    segar < 30 GB), `feat/heading-error` (`run.py` menulis `view_dir_model`; `eval_meter.py` menilai galat arah
    hadap dari foto berakhiran `_xp/_yp/_xn/_yn`; protokol di `docs/spike-plan.md`). Ketiganya menyentuh
    `server/` atau `spike/`: merge memicu autodeploy membuat ulang container.
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
- **Tailwind mengubah `_` di dalam varian arbitrer menjadi spasi.** `[&:not(.rdp-range_end)]` terkompilasi menjadi
  `:not(.rdp-range end)` (mencari tag `<end>`), jadi penjaga itu selalu benar. Pakai atribut data atau modifier
  komponen, bukan nama class bergaris bawah, dan periksa CSS terkompilasi di `web/out/_next/static/`.
- **Aturan CSS di luar `@layer` mengalahkan utilitas Tailwind.** `:focus-visible { outline: ... }` di `globals.css`
  harus berada di `@layer base`, kalau tidak `outline-none` pada komponen tidak berpengaruh dan muncul kotak fokus ganda.
- **Mengganti kelas bawaan komponen shadcn butuh awalan varian yang sama** (`data-[side=right]:w-full`), kalau tidak
  `tailwind-merge` menyimpan keduanya dan kelas bawaan menang (lebar Sheet jadi 384 px dan 3/4 layar).
- **Ikon yang baru ditambahkan bisa tampak kosong di browser yang pernah memintanya sebelum berkas ada** (404 tersimpan
  di cache). Server menyajikannya benar; buka URL ikon langsung lalu Ctrl+Shift+R.
- **WSL di PC lab bisa restart sendiri dan mematikan semua container**, termasuk pengukuran yang sedang jalan
  (2026-10-07 15:35). Berkas `.h5` fitur yang setengah tertulis lalu menggagalkan percobaan ulang
  (`file signature not found`). Skrip kini menghapus berkas `.h5` sisa di awal tiap ulangan (#66).
- **`bench_usage.py child` menghapus `results/<konfigurasi>-<perangkat>.jsonl` miliknya saat mulai.** Menjalankan
  sebagian varian di folder keluaran lama menghapus hasil sebelumnya; pakai folder `--out` baru dan sertakan `clean`.
- **Tahap `test` di `deploy/Dockerfile` hanya berisi `server/`, `spike/`, `web/`, `tests/`** (daftar putih di `.dockerignore`).
  Tes yang membaca berkas lain di repo gagal di CI dengan `FileNotFoundError` walau lulus di laptop; salin berkasnya
  hanya ke tahap `test` (contoh: `deploy/autodeploy.sh` untuk `tests/test_host_disk_feed.py`).
- **Di Windows, `bash` polos dalam `subprocess` jatuh ke peluncur WSL di System32**, yang bisa rusak. Pakai
  `shutil.which("bash")` dan jalankan tes shell dengan Git Bash di `PATH`.
- **Angka disk dari container menyesatkan di PC lab:** disk virtual WSL (1 TB) lebih besar daripada drive Windows
  di bawahnya. Pakai `storage.host` dan `web/lib/storage.ts`, jangan menjumlahkan `/maps` dan `/data`.
- **Beberapa komponen yang membutuhkan data status yang sama harus berbagi satu putaran polling** (`useSharedPoll`
  di `web/lib/usePoll.ts`), bukan memanggil `usePoll` masing-masing.
- **Unduhan dari PC lab lambat per koneksi** (sekitar 0,4 sampai 1,5 MiB/s); unduhan paralel menaikkan total sekitar
  lima kali. Image dan model besar butuh jam, bukan menit.
- **Rantai skrip jangan menilai selesai dari status keluar saja.** Satu langkah yang gagal sebelum perintah utamanya
  (misalnya berkas jalur pustaka tidak terbuat) membuat langkah berikutnya terlewat tanpa galat. Periksa berkas hasil.
- **`git push` bisa menggantung di Git Credential Manager.** Pakai
  `git -c credential.helper= -c "credential.helper=!gh auth git-credential" push`. GitHub kadang menjawab
  "Internal Server Error" sementara; ulangi.
- **Jangan menjalankan `docker compose config` di PC lab:** ia mencetak variabel yang sudah diperluas, termasuk
  kata sandi Postgres. Periksa GPU atau variabel lewat `docker compose exec`, dan jangan mencetak isi `deploy/.env`.

- **`align.json` ditulis di tempat yang tidak dibaca layanan.** `spike/eval_meter.py` menulisnya di samping
  `results.csv` (folder hasil uji), padahal `server/localizer.py` membacanya dari
  `<folder versi peta>/kp1024-r1024/align.json`. Pasang lewat `python -m server.manage align` di container `worker`; versi yang sedang aktif lalu
  perlu `docker compose restart api` (dashboard tidak punya tombol Publish untuk versi aktif).
- **Foto uji lantai 10 tanpa EXIF** (frame video `video2_LabHallDemo_*`): ISO, eksposur, dan terang adegan tidak
  bisa dihitung balik. Foto uji berikutnya wajib mode foto.
- **Di Windows, `tests/test_db.py::test_migration_cli_runs_like_the_container` gagal juga di `main`**
  (lingkungan lokal). CI di Docker yang menentukan.

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
