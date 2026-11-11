# Spesifikasi: tahap splat otomatis setelah peta jadi

Tanggal: 2026-11-09. Status: **diimplementasikan di cabang `feat/splat-convert` dan terbukti ujung ke ujung di PC lab
(10 dan 11 Nov 2026). Belum digabung ke `main` dan belum diaktifkan di produksi.** Bagian 10 dan 11 di bawah
mencatat keputusan akhir dan angka terukur; bagian 1 sampai 9 adalah rancangan awal (9 Nov).
Repo: `RockHead07/eutopos-vps`. Dasar: halaman viewer `/splat/` (PR 101), pemangkas `spike/splat_prune.py`,
rencana `docs/plans/2026-11-01-gaussian-splat-lantai-10.md`, catatan spike Task 0 dan 1 (di `D:\wt\splat-spike`,
belum masuk `main`).

## 1. Maksud

Sekarang viewer 3D hanya terbukti dengan data tiruan: tidak ada versi peta di server yang punya
`<versi>/splat/scene.sog`, jadi `has_splat` bernilai false di mana-mana. Splat lorong dibuat tangan lewat SSH,
Docker, dan beberapa perintah. Spesifikasi ini membuat splat **dibangun otomatis di server** setelah sebuah versi
peta jadi, lalu muncul di dashboard (tombol "Lihat 3D") tanpa ada yang menjalankan perintah.

## 2. Fakta yang sudah terukur atau terbaca dari kode (bukan usulan)

- `server/worker.py` `process()`: tahap `extract`, `build`, `inspect`, `register`. Hasilnya versi peta berstatus
  `candidate`. `db.publish()` hanya membalik status `published` / `retired`; publish tidak membangun apa pun.
- `/localize` tidak membutuhkan splat. Splat tidak boleh menghalangi publish.
- Image worker (`deploy/Dockerfile`): Python 3.12, torch 2.14.0 (cu130 pada `compose.gpu.yaml`), tahap `runtime`,
  tanpa `nvcc`. Image pelatihan splat yang sudah terbukti di PC lab: `eutopos-splat:local`, 24,3 GB, PyTorch 2.4.0
  CUDA 12.1 **devel**, `gsplat` 1.5.3 dengan JIT CUDA sudah dipanggang (kompilasi butuh `nvcc`).
- Pelatihan 30.000 langkah pada 401 frame lorong: 939 detik (`ellipse_time`), 973 detik per container, di RTX 3070
  8 GB yang dipakai bersama layanan `/localize` (sekitar 1,8 GB). 901.798 Gaussian, PLY 212.825.805 B.
- Konversi PLY ke `.sog` dengan `splat-transform` 3.10.3 (MIT, Node 22 atau lebih baru) dan `-H 0` selesai 2,5 detik
  di CPU. Tanpa `-H 0` (dengan pita SH) lebih dari 4 jam di CPU tanpa hasil.
- Pemangkas `spike/splat_prune.py` (cabang ini): `scene-asli.sog` 10.314.918 B menjadi 8.041.393 B pada bawaan L1
  (opasitas < 0,02), data yang dipertahankan identik bit demi bit.
- Alat siap pakai di `D:\wt\splat-spike` (belum di `main`): `splat_prepare.py` (undistort ke PINHOLE),
  `splat_check_frame.py` (memeriksa kerangka splat sama dengan kerangka model, lolos bila rasio < 0,02).

## 3. Tujuan, bukan tujuan

**Tujuan**
- Setelah `register` berhasil, splat dibangun otomatis untuk versi itu dan ditulis atomik ke
  `<versi.path>/splat/scene.sog`.
- Kegagalan splat tidak mengubah status job peta maupun versi peta, dan tidak menghalangi publish.
- Staf melihat status splat (antre, berjalan, selesai, gagal dengan alasan) dan bisa membangun ulang.
- Tidak ada akses Docker dari dalam container aplikasi.

**Bukan tujuan (v1)**
- Splat tidak dipakai untuk lokalisasi atau navigasi (keputusan rencana 1 Nov).
- Mesh GLB, gizmo geser, dan tampilan awal tanpa `cam=` (urusan viewer, terpisah).
- Pita SH (view-dependent color). Dampaknya pada kualitas **tidak diukur**.

## 4. Pilihan arsitektur

| | Pilihan | Kelebihan | Kekurangan |
|---|---|---|---|
| **A (usulan)** | Layanan compose baru `splat-worker`, image sendiri, antrean lewat tabel DB | Tidak ada `docker.sock`; image worker dan api tidak berubah; kegagalan terisolasi; pola sama dengan `worker` | Satu image 20 GB lebih untuk dikelola dan dibangun di PC lab |
| B | `worker` menjalankan `docker run` lewat `docker.sock` | Tanpa layanan baru | `docker.sock` setara akses root ke host; worker sengaja tidak punya itu |
| C | gsplat dipasang di image worker | Satu image | Tanpa `nvcc`; torch 2.14 vs 2.4 (gsplat 1.5.3 hanya terbukti di 2.4.0); berisiko merusak jalur peta yang sudah jalan |
| D | Tetap manual lewat SSH | Tanpa kode | Tidak memenuhi tujuan |

Usulan: **A**. B dan C ditolak dengan alasan di tabel.

## 5. Rancangan A

**Layanan `splat-worker`** (`deploy/compose.gpu.yaml` menambah reservasi GPU; `compose.yaml` mendefinisikannya).
Image `deploy/Dockerfile.splat`: basis CUDA devel, `gsplat` 1.5.3 pin, `pycolmap`, `numpy`, `Pillow`, Node 22 dengan
`@playcanvas/splat-transform` 3.10.3 pin. Mount `/maps` dan `/data` baca tulis (bind mount tidak bisa sebagian; folder kerja ada di `/data/jobs/<id>/splat/`).
Perintah `python -m server.splat_worker`, memakai `DATABASE_URL` yang sama.

**Tabel baru `splat_job`** (migrasi Alembic `0007`): `id`, `map_version_id` (FK, unik), `status`
(`queued`, `running`, `done`, `failed`), `stage`, `params` (JSON: `steps`, `min_opacity`), `summary` (JSON),
`error`, `created_at`, `started_at`, `finished_at`. Tabel terpisah dari `map_job` supaya kegagalan splat tidak
mencemari status peta.

**Pemicu.** Di `worker.process`, setelah `jobs.finish`, satu baris `splat_job` berstatus `queued` dimasukkan dalam
sesi yang sama (bukan memanggil apa pun). Kegagalan memasukkan baris itu tidak boleh menggagalkan job peta.

**Tahap `splat-worker`** (fungsi murni pembuat perintah + `runner` yang bisa diganti di tes, pola `worker.py`):
1. `prepare`: `splat_prepare` (undistort, model PINHOLE) dari `sfm/` dan akar `dataset/` (nama gambar di model COLMAP berawalan `mapping/`).
2. `train`: `simple_trainer.py default` dengan `--disable-viewer`, `--data-factor 1`, `--no-normalize-world-space`,
   `--save-ply`, 30.000 langkah (flag tyro memakai tanda hubung; terbukti dari pelatihan nyata di PC lab). Normalisasi dimatikan supaya splat tetap di kerangka COLMAP (terbukti perlu).
3. `check`: `splat_check_frame`; **gagal bila rasio >= 0,02** (splat di kerangka salah membuat overlay bergeser diam-diam).
4. `convert`: `splat-transform ... -H 0` menjadi `.sog`.
5. `prune`: `splat_prune.prune_sog` dengan `min_opacity` dari `params` (bawaan 0,02).
6. `place`: `os.replace` ke `<versi.path>/splat/scene.sog` dan `splat/report.json`. `has_splat` baru benar setelah ini.

Folder kerja `/data/jobs/<id>/splat/` dihapus bila sukses (PLY 213 MB tidak disimpan); dibiarkan bila gagal untuk
diagnosis dan dihapus saat versi dibangun ulang.

**GPU dibagi.** RTX 3070 8 GB dipakai `/localize` (sekitar 1,8 GB), `worker` (hloc), dan pelatihan. Berbagi GPU
lewat time-slicing **tidak memberi isolasi memori** (sumber di bagian 10), jadi satu proses yang membengkak bisa
menjatuhkan proses lain. Tiga lapis pengaman v1:
1. **Kunci bersama, bukan pemeriksaan status.** `worker` (saat membangun peta) dan `splat-worker` (saat melatih)
   sama-sama memegang `pg_advisory_lock` dengan kunci yang sama selama memakai GPU. Memeriksa "tidak ada `map_job`
   running" lalu mulai itu berlomba (job peta bisa diambil sesaat setelah pemeriksaan); kunci bersama tidak.
   Konsekuensi: `worker.process` ikut diubah sedikit (ambil kunci di awal, lepas di akhir). **Tidak ada penyelaan:**
   job peta yang datang saat pelatihan sudah berjalan menunggu sampai pelatihan selesai (sekitar 16 menit), dan
   dashboard menampilkan tahap "menunggu GPU". Peta hanya didahulukan sebelum pelatihan dimulai (`splat-worker`
   tidak mengambil `splat_job` bila ada `map_job` queued).
2. **Pemeriksaan VRAM bebas sebelum melatih**, dan **batas memori proses** untuk pelatihan. Ambang dan cara
   membatasi (mis. `torch.cuda.set_per_process_memory_fraction` lewat pembungkus pelatih) **belum diverifikasi**
   dan harus diukur di PC lab sebelum dikunci.
3. **Batas waktu per tahap**, syarat disk bebas 20 GB seperti worker, dan satu `splat_job` berjalan sekaligus.
Saat `splat-worker` mati di tengah pekerjaan, pekerjaan `running` ditandai gagal saat layanan mulai lagi (pola
`jobs.recover_stale`, sah karena hanya ada satu instance).

**API dan dashboard.** `VersionOut` mendapat `splat_status` (null bila tanpa baris). `has_splat` tetap berbasis berkas.
`POST /api/versions/{id}/splat/rebuild` mengantre ulang (hanya bila `failed` atau `done`; menolak saat `running`).
Dashboard: lencana status di baris versi dan tombol bangun ulang; teks galat jujur dari `error`.

## 6. Pengujian

- Pure: pembuat perintah, urutan tahap, aturan "gagal bila rasio >= 0,02", penulisan atomik, penghapusan folder kerja.
- `splat_worker.process` dengan `runner` palsu (seperti tes `worker`): tiap tahap gagal menghasilkan `failed` dengan
  tahap yang benar, dan **map_job dan map_version tidak berubah**.
- Migrasi `0007` naik dan turun. Aturan "tidak ambil saat ada map_job running".
- Bagian GPU (pelatihan nyata, konversi di Node) diverifikasi di PC lab dengan izin Bagus per langkah, bukan di CI.

## 7. Risiko dan hal yang belum diketahui

1. **VRAM dan waktu pada gedung besar tidak diukur.** (Sejak 10 dan 11 Nov ada dua angka pada 401 frame, lihat
   bagian 11; gedung besar tetap belum diukur.) Angka awal: 401 frame, 939 detik. Lantai dengan ribuan frame
   bisa OOM; `packed` atau batas frame mungkin perlu.
2. **Image 20 GB+ dan build di jaringan lab lambat.** Build pertama `eutopos-splat` pernah gagal (galat containerd)
   lalu berhasil pada percobaan ulang; penyebabnya belum terbukti.
3. **Pemangkasan L1 diukur hanya pada tujuh pose latih** di render perangkat lunak; efek pada GPU nyata dan pose
   di luar jalur latih belum diukur.
4. **Gumpalan abu-abu dekat kamera 360** (floater berbahaya) belum ditangani; bukan bagian v1.
5. **Privasi.** Splat menanam orang yang tertangkap di frame. Hanya diakses lewat dashboard berautentikasi; tidak
   dibagikan keluar tanpa pemeriksaan visual. Rekaman yang memuat orang tetap menjadi tanggung jawab pengunggah.
6. **Asal numpy dan Pillow.** `uv.lock` tidak memuat keduanya (juga torch, hloc, opencv, pycolmap, scipy); repo
   membiarkan dependensi runtime berat dipasang oleh langkah 1 dan 2 `deploy/Dockerfile`. `numpy` datang dari
   hloc dan `Pillow` dari `matplotlib`. Keduanya TIDAK dideklarasikan di `pyproject.toml` (akan menggeser versi
   yang dipilih hloc); komentar di sana diperjelas, dan `Dockerfile.splat` memin versinya sendiri.

## 7b. Dasar praktik terbaik (diperiksa 9 Nov 2026)

Diverifikasi ke sumber primer: (a) dokumentasi PostgreSQL `SELECT`: `SKIP LOCKED` memang untuk "queue-like table"
dengan banyak konsumen, dan hasilnya sengaja tidak konsisten sehingga tidak untuk pekerjaan umum; repo ini sudah
memakainya di `jobs.claim_next`. (b) Dokumentasi Docker, "Docker daemon attack surface": daemon butuh root dan hanya
pengguna tepercaya yang boleh mengendalikannya, karena berbagi direktori host tanpa batas. Itu dasar menolak opsi B.

Dari sumber sekunder (blog, panduan vendor, kebanyakan untuk Kubernetes, bukan Compose satu mesin): time-slicing
GPU tanpa isolasi memori; MPS membatasi memori tetapi tanpa isolasi galat; hanya MIG (A100 ke atas) yang mengisolasi.
RTX 3070 tidak mendukung MIG.

**Yang TIDAK ditemukan:** tidak ada sumber yang menyatakan "worker GPU sebagai kontainer terpisah" sebagai standar
untuk gsplat. Memisahkan layanan di sini adalah kesimpulan teknik dari kendala (tanpa `nvcc` di image worker,
versi torch berbeda, menghindari `docker.sock`), bukan kutipan praktik baku. Tidak ada pembanding kinerja untuk
kasus kita. Dokumen PyTorch tentang batas memori per proses tidak berhasil diambil sehingga belum diverifikasi.

Alternatif antrean berbasis pustaka (Celery, RQ, procrastinate, pgqueuer) tidak dipakai: satu jenis pekerjaan dan
satu pekerja tidak membenarkan dependensi baru; tabel `splat_job` dengan pola `claim_next` yang sudah ada cukup.

## 8. Urutan PR (usulan, tiap PR bisa diuji sendiri)

1. Modul `splat_prune` + penjelasan asal `numpy`/`Pillow` di komentar `pyproject.toml` (cabang ini).
2. `splat_prepare` dan `splat_check_frame` dari `D:\wt\splat-spike` (+ tesnya).
3. Migrasi `0007` + model `SplatJob` + `splat_worker` (fungsi murni dan `process` dengan runner palsu), tanpa image.
4. `Dockerfile.splat`, compose, dan verifikasi di PC lab (izin per langkah).
5. API `splat_status` + `rebuild`, lencana di dashboard.
6. Menyambungkan pemicu di `worker.process`.

## 9. Pertanyaan untuk Bagus

1. Setujukah arsitektur **A** (layanan `splat-worker` tersendiri)?
2. Pemicu: otomatis setiap versi baru (usulan, dengan aturan GPU di atas) atau hanya tombol "Bangun 3D" di dashboard?
3. Folder kerja: hapus saat sukses (usulan) atau simpan PLY per versi (213 MB)?
4. Pelatihan 30.000 langkah tetap sebagai bawaan, dengan `steps` sebagai parameter?

Dijawab (9 sampai 11 Nov 2026): (1) arsitektur A disetujui Bagus 9 Nov. (2) Pemicu otomatis, dengan saklar
`EUTOPOS_SPLAT_AUTO` (bagian 10), ditambah tombol admin "Bangun ulang 3D" untuk versi yang sudah ada. (3) Folder
kerja dihapus saat sukses; metrik pelatih disalin ke `report.json` karena statistiknya ikut terhapus. (4) 30.000
langkah sebagai bawaan, `steps` dan `min_opacity` sebagai parameter. Aktivasi di produksi: secepatnya (Bagus 11 Nov),
setelah PR digabung (bagian 10, "Mengaktifkan").

## 10. Keputusan dan kenyataan implementasi (10 sampai 11 Nov 2026)

- **Arsitektur A seperti rancangan.** Layanan `splat-worker` tersendiri di `deploy/compose.yaml` dengan profil
  compose `splat` (opt-in: autodeploy menjalankan `docker compose build` dan `up` untuk semua layanan tanpa profil,
  jadi tanpa profil merge akan membangun image 24 GB dan menyalakannya). Pengguna kontainer uid 1000 (sama dengan
  `worker`, supaya `worker.purge` bisa menghapus folder `splat/`), RAM dibatasi 8 GB (`mem_limit`, `memswap_limit`).
- **Image `deploy/Dockerfile.splat` memuat dua environment Python**, karena versi yang dibutuhkan bertabrakan:
  pelatih gsplat di conda Python 3.11 dengan pycolmap fork (`SceneManager`, numpy di bawah 2), layanan dan alat di venv
  Python 3.12 (`/opt/venv`) dengan pycolmap resmi 4.2.1 (`Reconstruction`, `undistort_images`), numpy 2.5.2. Daftar
  paket apt pertama HARUS sama persis dengan Dockerfile terbukti (`git libgl1 libglib2.0-0`), kalau tidak cache semua
  lapisan pelatih batal (tes `test_trainer_layer_apt_packages_match_the_proven_image`). Bobot AlexNet untuk LPIPS
  diunduh saat build dengan cek sha256, jadi tidak ada unduhan saat runtime.
- **Pemicu.** `worker.queue_splat` mengantre satu `splat_job` setelah `jobs.finish`; kegagalan mengantre dicatat dan
  tidak pernah menggagalkan peta. **Bawaan MATI**, hidup dengan `EUTOPOS_SPLAT_AUTO=1` bersama profil `splat`:
  tanpa pekerja splat, antrean 3D menumpuk berstatus queued dan menahan penghapusan versi. Untuk versi yang sudah
  ada: tombol "Bangun ulang 3D" (hanya admin; urutan pemeriksaan 415, 403, 404, 409 job sedang dihapus, 409 tanpa
  frame, 409 sudah antre, 202). Rebuild admin-saja adalah keputusan Claude yang boleh dibalik Bagus.
- **Antrean dan GPU.** Tabel `splat_job` (migrasi 0007; FK ke `map_version` dengan `ON DELETE CASCADE`, unik per versi),
  `claim_next` dengan `FOR UPDATE SKIP LOCKED`, pemulihan `running` yang yatim saat pekerja mulai, satu pekerjaan
  sekaligus, pekerjaan peta didahulukan (pekerjaan 3D tidak diambil selama ada `map_job` queued atau running).
  `pg_advisory_lock` bersama `worker` dipegang hanya selama pelatihan; kunci berlaku per DATABASE, bukan per mesin.
  Tahap: `inputs`, `prepare`, `gpu_wait`, `train`, `check`, `convert`, `prune`, `place`.
- **Pemeriksaan VRAM bebas sebelum melatih: 4.096 MiB**, dua kali kebutuhan terukur (sekitar 2 GB di atas
  lokalisasi produksi pada 401 frame). Dibaca dengan `torch.cuda.mem_get_info()` lewat Python pelatih. Kurang dari
  ambang: gagal cepat dengan pesan jelas (tahap `gpu_wait`), coba lagi lewat "Bangun ulang 3D". Tidak terukur:
  tidak memblokir (pelatih sendiri gagal dengan galat jelas).
- **Hasil.** `<versi>/splat/scene.sog` dan `report.json`, ditulis atomik (berkas sementara di folder tujuan yang sama,
  karena `/data` dan `/maps` dua bind mount berbeda): `report.json` dulu, `scene.sog` terakhir (`has_splat` benar begitu
  `scene.sog` ada). `report.json` memuat parameter, `check_ratio`, jumlah Gaussian dan byte sebelum dan sesudah
  pangkas, detik per tahap, `built_at`, `vram_free_mib`, dan `metrics` (`psnr`, `ssim`, `lpips`, `peak_mem_gb` dari
  statistik pelatih; `null` bila tidak terbaca).
- **Konversi dan pangkas.** `splat-transform` 3.10.3 dengan `-g cpu` (tanpa WebGPU) dan `-H 0` (tanpa pita SH);
  pangkas L1 dengan `min_opacity` 0,02 (`docs/splat-prune.md`). `--test-every` bawaan pelatih (8, sepertujuh frame
  jadi frame uji) dipertahankan.
- **Aktivasi di produksi (setelah PR digabung)**, dua saklar selalu bersamaan di `deploy/.env`: `COMPOSE_PROFILES=splat`
  dan `EUTOPOS_SPLAT_AUTO=1`, lalu `docker compose up -d --build`. Pemicu otomatis hanya berlaku untuk peta BARU;
  untuk versi yang sudah terbit admin menekan "Bangun ulang 3D" (butuh frame; versi dari CLI tanpa frame ditolak).

## 11. Hasil pengukuran (PC lab, RTX 3070 8 GB, 401 frame, 30.000 langkah)

Rinci di `docs/splat-pipeline-measurements.md`. Ringkas, dua latihan penuh lewat pipeline (10 dan 11 Nov 2026):
total 942 dan 966 detik (pelatihan 875 dan 868); VRAM tambahan di atas lokalisasi produksi 2.022 dan 1.946 MiB;
RAM sekitar 2 GB; Gaussian 863.092 dan 882.888 menjadi 657.978 dan 669.199 (turun 23,8% dan 24,2%); `scene.sog`
7,70 dan 7,85 MB (turun 22,0% dan 22,4%); PSNR 24,61 dB, SSIM 0,881, LPIPS 0,275 pada frame uji. Layanan produksi
tetap sehat (`/health` 200) pada semua cuplikan. Variasi antar-latihan (sekitar 2% Gaussian, 0,3 dB PSNR) adalah
sifat pelatihan yang tidak deterministik, bukan galat.

Konsekuensi operasional yang diketahui (audit 11 Nov 2026): (1) pekerjaan peta yang antre saat pelatihan splat
berjalan menunggu kunci GPU sampai pelatihan selesai (sekitar 16 menit pada 401 frame, lebih lama pada gedung
besar); aturan "peta didahulukan" hanya mencegah pekerjaan 3D BARU dimulai. (2) Pekerjaan 3D berstatus queued
tanpa pekerja splat menahan penghapusan versi itu (aturan sengaja konservatif); jangan menekan "Bangun ulang
3D" sebelum profil `splat` aktif. (3) Pekerjaan 3D yang gagal meninggalkan folder kerjanya (gambar tanpa
distorsi dan hasil pelatihan) sampai dibangun ulang atau versinya dihapus.

Yang TIDAK terukur dan tetap berlaku sebagai batas: gedung dengan ribuan frame (VRAM dan waktu), latensi
`/localize` selama pelatihan (hanya `/health` yang dipantau), pose di luar jalur latih, dan kemampuan `check_ratio`
(ambang 0,02, terukur 0,0002) mendeteksi splat yang salah posisi (belum ada kontrol negatif nyata). Splat TIDAK
menaikkan akurasi lokalisasi; ini pratinjau hasil scan.
