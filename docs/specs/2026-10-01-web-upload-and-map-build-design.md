# Spesifikasi: Website Unggah Video dan Pembangunan Peta

**Status:** rancangan, hasil brainstorming 2026-10-01. Riset pendukung: `docs/web-upload-research.md`.
Melengkapi `docs/specs/2026-09-29-capture-and-map-pipeline-design.md` untuk **jalur video** (Tahap 0
dan PA opsi a: kamera bawaan + `extract_frames.py`). Aplikasi capture dengan foto kunci dan pose ARCore
tetap rencana terpisah di spesifikasi itu.

**Prasyarat:** branch `feat/video-map-diagnostics` (`run.py --seq`, `spike/inspect_map.py`) sudah masuk
`main`. Pekerja di sini memanggil kedua alat itu.

## 1. Tujuan dan ukuran berhasil

Dari mana saja lewat internet, pemilik dan beberapa orang yang diizinkan bisa mengunggah video capture,
melihat peta dibangun otomatis di PC lab, meninjau hasilnya, lalu menerbitkannya ke `/localize`.

**Berhasil kalau:** satu sesi lantai 10 (dua video ±540 MB) berjalan dari unggah sampai peta aktif
**tanpa membuka RustDesk, Drive, atau terminal**, dan unggahan yang putus di tengah bisa dilanjutkan.

## 2. Batasan (keputusan brainstorming)

| Hal | Keputusan |
|---|---|
| Asal unggahan | Dari mana saja lewat internet |
| Pengguna | Pemilik + beberapa orang tertentu (anggota lab, pembimbing). Daftar email, tanpa akun lokal |
| Jaringan | Cloudflare Tunnel + Cloudflare Access di `rockhead07.tech`. **Tidak ada port yang dibuka** |
| Host | PC lab (hak pemilik, boleh memasang perangkat lunak), Docker Engine di WSL2, RTX 3070 |
| Cakupan v1 | Unggah, bangun peta, laporan + tampilan 3D, **Terbitkan** (versi dan rollback). Uji lokalisasi dari browser menyusul |
| Stack terkunci | FastAPI, PostgreSQL (antrean `SKIP LOCKED`), folder disk, Next.js static export |

## 3. Arsitektur

```text
Browser (Uppy) ──HTTPS──► Cloudflare (Access: email + kode) ──Tunnel──► PC lab, jaringan internal Compose
                                                                   │
                         cloudflared ──┬── /files/*    ──► tusd    (potongan unggahan ke /data/uploads)
                                       ├── /internal/* ──► ditolak 404 (hanya untuk hook dari tusd)
                                       └── selainnya   ──► api     (dashboard statis + /api/* + /localize)
                         tusd ──hook pre-create, pre-finish──► api /internal/tus-hook
                         api ──baris pekerjaan──► db (PostgreSQL) ◄──SKIP LOCKED── worker (GPU)
                         worker: ekstrak frame ► run.py --seq ► inspect_map --html ► daftarkan versi kandidat
```

| Layanan | Isi | Baru? |
|---|---|---|
| `db` | PostgreSQL 17 | Ada |
| `api` | FastAPI: `/localize`, `/health`, API dashboard, hook tusd, berkas statis dashboard | Diperluas |
| `worker` | Proses Python di image yang sama dengan `api`, varian GPU, satu instans | Baru |
| `tusd` | Server tus resmi (MIT), `-base-path /files/`, `-behind-proxy`, `-disable-download`, `-max-size` 2 GB, hook HTTP `pre-create,pre-finish` | Baru |
| `cloudflared` | Tunnel bernama, aturan ingress per path, `originRequest.access` wajib | Baru |

**Satu hostname:** `eutopos.rockhead07.tech`. Dashboard, API, dan tusd berada di asal yang sama, jadi
tanpa CORS dan cookie Access ikut terkirim. `ports` di `api` dihapus setelah Tunnel jalan.

## 4. Alur

1. **Masuk.** Cloudflare Access meminta email yang ada di daftar, lalu kode sekali pakai.
2. **Buat sesi.** Di halaman "Sesi peta baru", pengguna memilih area dan mendaftarkan video beserta
   perannya: `peta` atau `uji`. Bawaan: Video 1 `peta`, Video 2 `uji`, seperti uji 2026-09-30. Untuk
   peta produksi, keduanya `peta`. `POST /api/jobs` membuat pekerjaan berstatus `uploading`.
3. **Unggah.** Uppy mengirim tiap video lewat tus dengan potongan **50 MiB** (batas Cloudflare Free
   100 MB per permintaan). Metadata tus: `job_id`, `role`, nama berkas. Unggahan yang putus dilanjutkan
   dari offset terakhir.
4. **Hook `pre-create`:** API memvalidasi JWT Access dari header klien yang diteruskan tusd, memastikan
   pekerjaan ada, berstatus `uploading`, dan dibuat oleh email yang sama. Kalau tidak, unggahan ditolak.
5. **Hook `pre-finish`:** API mencatat berkas ke pekerjaan. Kalau semua video yang didaftarkan sudah
   lengkap, status menjadi `queued`. Klien baru diberi tahu selesai setelah baris ini tersimpan.
   `post-finish` tidak dipakai karena tidak diulang kalau gagal.
6. **Pekerja** mengambil satu pekerjaan `queued` dengan `FOR UPDATE SKIP LOCKED`, menandainya `running`,
   lalu menjalankan tahap berurutan dan mencatat tahap aktif:
   1. `extract`: `extract_frames.py` (video `peta` ke `mapping/` 2 fps, video `uji` ke `query/` 0,5 fps).
   2. **Video mentah dihapus** setelah ekstraksi berhasil (privasi, dan ketentuan Cloudflare soal video).
   3. `build`: `run.py --seq 10 --global-resize 512`.
   4. `inspect`: `inspect_map.py --html` dan ringkasan JSON.
   5. `register`: daftarkan versi kandidat (`server.db.register`) setelah `missing_files` kosong.
   Berhasil: `done` dengan `map_version_id`. Gagal: `failed` dengan tahap dan 50 baris log terakhir.
7. **Tinjau.** Halaman pekerjaan memperbarui status tiap 5 detik. Setelah `done`, tampil ringkasan
   (frame terdaftar, jumlah potongan, query diterima), tampilan 3D, dan perbandingan dengan versi aktif.
8. **Terbitkan.** `POST /api/versions/{id}/publish` memanggil `server.db.publish` (satu transaksi, versi
   lama `retired`). Rollback = menerbitkan versi lama. Lihat bagian 7 untuk pemuatan ulang.

## 5. Model data (migrasi Alembic baru)

`map_job`:

| Kolom | Isi |
|---|---|
| `id` | kunci utama |
| `area_id` | ke `area.id` (area dibuat kalau belum ada, seperti `register`) |
| `created_by` | email dari JWT Access |
| `status` | `uploading`, `queued`, `running`, `done`, `failed` |
| `stage` | tahap aktif atau tahap gagal |
| `videos` | JSON: daftar `{name, role, size, upload_id, path}` |
| `summary` | JSON ringkasan `inspect_map` (null sampai `done`) |
| `error` | potongan log kalau gagal |
| `map_version_id` | ke `map_version.id`, terisi saat `done` |
| `created_at`, `started_at`, `finished_at` | waktu |

`map_version` ditambah `published_by` (email, null untuk versi lama). Tidak ada tabel pengguna: hak akses
sepenuhnya dari daftar email di Cloudflare Access (keputusan terbuka nomor 4 terjawab untuk website).

## 6. Pekerja

- `python -m server.worker`: loop polling tiap 5 detik. `LISTEN/NOTIFY` belum perlu.
- Satu pekerjaan dalam satu waktu (satu GPU). Saat mulai, pekerjaan yang tertinggal `running` ditandai
  `failed` dengan alasan "pekerja berhenti". Aman karena hanya ada satu pekerja.
- Alat spike dipanggil sebagai subprocess, log per pekerjaan ke `/data/jobs/<id>/log.txt`.
  `ponytail:` subprocess ke skrip spike; jadikan modul kalau alurnya stabil.
- Tata letak disk:
  - `/data/uploads/` milik tusd.
  - `/data/jobs/<id>/` berisi frame dan log.
  - `/maps/<area>/job-<id>/` berisi keluaran `run.py`, `report.html`, dan `inspect.json`.
    Nomor versi baru diketahui saat `register`, jadi folder dinamai menurut pekerjaan.
  - `api` memasang `/maps` baca saja, `worker` baca tulis.

## 7. Terbitkan dan pemuatan ulang `/localize`

Sekarang peta dimuat sekali saat `api` menyala. Setelah terbit, kalau area yang diterbitkan sama dengan
`EUTOPOS_AREA`, `api` memuat `Localizer` baru di thread terpisah, lalu menukarnya di bawah kunci yang
sudah ada. Selama memuat, permintaan `/localize` tetap memakai peta lama. Kalau gagal memuat, peta lama
tetap dipakai dan versi dikembalikan ke status sebelumnya. `ponytail:` satu area aktif per layanan;
muat banyak area saat area kedua datang (spesifikasi pipeline bagian 5).

## 8. Autentikasi dan keamanan

- **Tepi:** aplikasi Cloudflare Access untuk hostname, kebijakan Allow email tertentu, metode kode
  sekali pakai. Paket Zero Trust gratis cukup untuk beberapa orang.
- **Tunnel:** `originRequest.access.required: true` dengan `teamName` dan `audTag`, supaya salah
  konfigurasi di dashboard Cloudflare tidak membuka origin.
- **Origin:** satu dependency FastAPI memvalidasi `Cf-Access-Jwt-Assertion` (PyJWT, kunci dari endpoint
  `certs` tim, diperiksa `aud`). Dipakai oleh semua `/api/*` dan oleh hook `pre-create`.
  **Gagal tertutup per rute:** tanpa `CF_ACCESS_TEAM_DOMAIN` dan `CF_ACCESS_AUD`, `/api/*` dan hook
  `pre-create` menjawab 503, sementara `/localize` dan `/health` tetap jalan supaya layanan yang
  sudah berjalan tidak mati sebelum Tunnel ada. `EUTOPOS_DEV_NO_AUTH=1` hanya untuk uji lokal.
- `/internal/*` tidak dirutekan oleh cloudflared, jadi hanya bisa dipanggil dari jaringan internal.
- **`/localize` di v1 ikut di balik Access**, karena aplikasi navigasi belum ada. Saat aplikasi siap,
  `/localize` dibuka di hostname terpisah tanpa Access dengan pembatasan laju. Diputuskan saat itu.
- tusd `-disable-download`: video tidak bisa diambil kembali lewat Tunnel. Dashboard tidak pernah
  memutar video (ketentuan Cloudflare melarang menyajikan video di paket non-Enterprise).

## 9. Dashboard

Next.js static export, disajikan `api` dari folder `out/` (build Node di tahap terpisah Dockerfile).

| Halaman | Isi |
|---|---|
| `/` | Daftar pekerjaan terbaru: area, status, tahap, pengunggah, waktu |
| `/new` | Pilih area, tambah video dan perannya, unggah dengan Uppy (`@uppy/tus`, `chunkSize` 50 MiB), progress per berkas |
| `/job?id=` | Status (polling 5 detik), log kalau gagal, ringkasan, tampilan 3D (iframe `report.html`), tombol Terbitkan |
| `/maps` | Versi per area: aktif, kandidat, riwayat, tombol Terbitkan untuk rollback |

Rute dinamis memakai parameter query karena static export. `plotly.min.js` disajikan sekali dari `api`
dan `report.html` merujuk ke sana (`include_plotlyjs` berupa URL), sehingga tiap laporan ±0,2 MB.

## 10. Penanganan galat

| Kejadian | Perilaku |
|---|---|
| Koneksi putus saat unggah | Uppy melanjutkan dari offset terakhir |
| Unggahan ditinggal | Pekerjaan `uploading` lebih dari 24 jam ditandai `failed`, berkas tusd dibersihkan |
| Berkas bukan video, atau rotasi EXIF | `extract` gagal dengan pesan jelas |
| Peta pecah atau sedikit frame terdaftar | Tetap `done`. Ringkasan menunjukkan potongan dan persen terdaftar, peninjau yang memutuskan |
| Pekerja mati di tengah | Saat mulai lagi, pekerjaan `running` jadi `failed` |
| Disk hampir penuh | `extract` menolak kalau ruang kosong kurang dari 20 GB |
| JWT tidak sah | 403. Hook `pre-create` menolak, unggahan tidak dimulai |

## 11. Pengujian

- **Unit (SQLite, seperti `tests/test_db.py`):** transisi status pekerjaan, pencatatan berkas di hook,
  status `queued` setelah video terakhir, pemulihan pekerjaan tertinggal.
- **Autentikasi:** JWT palsu dengan kunci RSA uji, endpoint `certs` diganti. Token salah `aud`,
  kedaluwarsa, atau tanpa header ditolak.
- **Migrasi:** model sama dengan migrasi (uji yang sudah ada diperluas).
- **Pekerja:** alur tahap dengan perintah subprocess palsu. Satu uji nyata di PC lab memakai frame
  `floor10-v1` yang sudah ada.
- **Ujung ke ujung (PC lab):** unggah dua video lewat `eutopos.rockhead07.tech` dari jaringan luar
  kampus, putuskan koneksi di tengah, lanjutkan, lalu terbitkan dan panggil `/localize`.

## 12. Di luar cakupan v1

Uji lokalisasi dari browser, peran pengguna, penyamaran orang otomatis, hostname publik `/localize`,
notifikasi, banyak pekerja, pemutaran video.

## 13. Urutan PR

1. **Pekerjaan dan pekerja:** tabel `map_job`, `server/worker.py`, perintah `python -m server.manage job`
   untuk membuat pekerjaan dari folder lokal. Sudah berguna tanpa website.
2. **Unggahan:** tusd di Compose, `POST /api/jobs`, hook, autentikasi JWT.
3. **Dashboard:** Next.js static export, Uppy, halaman bagian 9, Terbitkan dan pemuatan ulang.
4. **Tunnel:** cloudflared di Compose, aplikasi Access, `ports` dihapus, panduan di `deploy/README.md`.

**Status verifikasi (PC lab, Docker, RTX 3070):**
- ✅ PR 1 (2026-10-01): pekerjaan dari `manage job`, peta jalur keliling 401/402 frame dalam satu peta.
- ✅ PR 2 (2026-10-02): video uji 60 s (120 frame loop) diunggah lewat `server.upload_client`
  (protokol tus, potongan 50 MiB) ke tusd, hook `pre-create` dan `pre-finish` mengantrekan pekerjaan,
  pekerja membangun peta sampai `done` (versi id 3), folder `uploads/` kosong setelah ekstraksi.
  Tanpa `CF_ACCESS_*`: `POST /api/jobs` 503, hook tanpa rahasia 403, `/health` 200.
- ✅ PR 4 bagian akun (2026-10-02, `cf` CLI): tunnel `eutopos-pclab`, aplikasi Access (kode email,
  720 jam, daftar email), rute, pagar `originRequest.access`, DNS. Dari luar tanpa login: 302 ke
  halaman login Access. `cloudflared` di PC lab: lihat `deploy/README.md` bagian 6.
