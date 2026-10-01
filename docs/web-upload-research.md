# Riset: Unggah Video dan Pembangunan Peta lewat Website

Riset untuk satu pertanyaan desain eutopos: bagaimana pemilik repo dan beberapa orang yang diizinkan
(anggota lab, pembimbing) bisa **mengunggah video capture dari mana saja** ke PC lab, lalu server
membangun peta 3D di GPU secara otomatis, menampilkan laporan dan tampilan 3D, dan menyediakan tombol
"Terbitkan" yang mengaktifkan versi peta untuk `/localize`.

**Cara verifikasi.** Batas dan perilaku Cloudflare dibaca dari dokumentasi resmi
`developers.cloudflare.com` dan halaman ketentuan di `cloudflare.com`. Protokol tus dibaca dari
spesifikasi di `tus.io`. tus-js-client dan tusd dibaca dari sumber dokumentasinya di repo GitHub resmi
(`docs/api.md`, `docs/_advanced-topics/hooks.md`, `docs/_getting-started/configuration.md`, `Dockerfile`),
Uppy dari `uppy.io`. Lisensi, versi rilis, dan tanggal aktivitas terakhir dibaca dari API GitHub, npm,
dan PyPI. FastAPI dan Starlette lewat context7 (`/websites/fastapi_tiangolo`, `/kludex/starlette`) dan
dicocokkan dengan kode terpasang (FastAPI 0.141.1, Starlette 1.7.0). PostgreSQL dari dokumentasi resmi
versi 17. Docker Compose dari `docs.docker.com`. plotly dari kode terpasang (plotly 7.1.0, plotly.js
4.1.1). Next.js lewat context7 (`/vercel/next.js/v16.2.9`) dan halaman resmi (versi dokumen 16.3.8).
Konteks repo dibaca dari `server/app.py`, `server/db.py`, `server/manage.py`, `deploy/compose.yaml`,
`deploy/compose.gpu.yaml`, `spike/extract_frames.py`, `spike/run.py`, dan
`docs/specs/2026-09-29-capture-and-map-pipeline-design.md`. Kutipan dijaga di bawah 15 kata. Tanda ⚠️
berarti belum terverifikasi penuh. Tanggal pengecekan: 1 Oktober 2026.

**Keputusan yang sudah dikunci dan tidak dibahas ulang di sini:** FastAPI + antrean pekerjaan di tabel
PostgreSQL (`SELECT ... FOR UPDATE SKIP LOCKED`, satu pekerja), berkas di folder disk tanpa MinIO,
dashboard Next.js *static export* yang disajikan FastAPI, tidak membuka port. Akses dari luar lewat
Cloudflare Tunnel (`cloudflared`) + Cloudflare Access (daftar email, one-time PIN) pada subdomain
`rockhead07.tech`.

## Ringkasan

| Pertanyaan | Jawaban singkat | Dasar |
|---|---|---|
| Batas ukuran body di Cloudflare Free? | **100 MB per permintaan** (Free dan Pro), Business 200 MB, Enterprise sampai 5 GB. Lewat batas = `413`. Hostname Tunnel wajib *proxied*, jadi batas ini **berlaku**. Satu video 540 MB tidak bisa dikirim dalam satu permintaan | Cloudflare docs: Error 413, Workers limits, Tunnel API |
| Batas waktu? | Origin harus mulai menjawab dalam **125 s** (Proxy Read Timeout, `524`, hanya Enterprise yang bisa mengubah). Pembangunan peta wajib asinkron dengan polling status | Cloudflare connection limits, Error 524 |
| Protokol unggah yang bisa dilanjutkan? | **tus 1.0.0**. Klien Uppy `@uppy/tus` (MIT) di atas tus-js-client (MIT), dengan **`chunkSize` di bawah 100 MB** (usulan 50 MiB) | tus.io, tus-js-client `docs/api.md`, uppy.io |
| Server tus? | **tusd** (Go, MIT, rilis v2.10.1 16 September 2026) sebagai container, hook HTTP ke FastAPI. Alternatif Python: `tuspyserver` (MIT, aktif, komunitas kecil). `fastapi-tusd` tidak aktif sejak 2025 | Repo tusd, PyPI, API GitHub |
| FastAPI dan unggahan besar? | `UploadFile` di-*spool* ke memori sampai 1 MB lalu ke berkas sementara. `request.stream()` menulis langsung tanpa salinan kedua. Starlette 1.7 punya `RequestBodyLimitMiddleware` | Dokumen FastAPI, Starlette, kode terpasang |
| Antrean pekerjaan? | Pola `SKIP LOCKED` disebut resmi di dokumentasi PostgreSQL untuk tabel mirip antrean. `LISTEN/NOTIFY` hanya pembangun opsional, pekerja tetap harus polling | PostgreSQL 17 docs |
| GPU di Compose? | `deploy.resources.reservations.devices` dengan `driver: nvidia`, `capabilities: [gpu]` (wajib), `count` atau `device_ids` | Docker docs |
| Validasi Access di origin? | Header `Cf-Access-Jwt-Assertion`, kunci di `https://<tim>.cloudflareaccess.com/cdn-cgi/access/certs`, cek `aud` (AUD tag) dan `iss`. `cloudflared` juga bisa memvalidasi sendiri (`originRequest.access`) | Cloudflare Access docs, origin parameters |
| Paket gratis Zero Trust? | Sekitar **50 pengguna** ⚠️. OTP berlaku 10 menit, email dikirim hanya kalau lolos kebijakan | Cloudflare product page, blog, OTP docs |
| Upload `fetch`/XHR lewat Access? | Satu hostname = tidak ada CORS, cookie `CF_Authorization` ikut otomatis. Lintas hostname = preflight `OPTIONS` ditolak `403` tanpa pengaturan khusus | Cloudflare Access CORS docs, MDN |
| Laporan 3D plotly kecil? | `include_plotlyjs='directory'` atau path `.js` sendiri: hemat sekitar 4,8 MB per laporan. `'cdn'` bergantung pada `cdn.plot.ly` | Kode plotly 7.1.0 |
| Ketentuan video di Cloudflare? | Paket non-Enterprise dilarang **menyajikan** video lewat CDN tanpa layanan berbayar. Unggahan ke origin **tidak disebut** ⚠️. Jangan menyajikan video kembali lewat Tunnel | Service-Specific Terms (28 September 2026), Tunnel FAQ |
| Next.js static export? | Tanpa Server Actions, Route Handler dinamis, cookies, rewrites, optimasi gambar bawaan. Rute dinamis butuh `generateStaticParams`, jadi pakai parameter query | Next.js docs |

---

## 1. Batas Cloudflare: ukuran body dan batas waktu

### 1.1 Ukuran body per plan

- Halaman [Error 413](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/)
  memuat tabel batas unggah: **Free 100 MB, Pro 100 MB, Business 200 MB, Enterprise sampai 5 GB**.
  Pengaturannya ada di halaman **Network** milik zona. Saran resmi saat melewati batas: pecah permintaan
  menjadi potongan kecil, pakai rekaman DNS-only, atau naikkan plan.
- Angka yang sama ada di [Workers limits](https://developers.cloudflare.com/workers/platform/limits/),
  dengan penegasan bahwa batas body *"depend on your Cloudflare account plan"*, bukan plan Workers.
  Lewat batas, jawabannya `413 Request entity too large`.
- [Changelog 4 September 2026](https://developers.cloudflare.com/changelog/post/2026-09-04-enterprise-self-serve-upload-limits/):
  hanya Enterprise yang berubah (atur sendiri sampai 5 GB, bawaan tetap 500 MB). Free tidak berubah.
- ⚠️ Dokumen menulis "100 MB" tanpa menjelaskan apakah 10^6 atau 2^20 byte. Potongan 50 MiB
  (52.428.800 byte) aman untuk kedua tafsiran.

### 1.2 Apakah batas itu berlaku untuk Tunnel?

**Ya.** Hostname publik Tunnel adalah rekaman CNAME ke `<tunnel-id>.cfargotunnel.com` yang wajib
`"proxied": true`
([Create a tunnel (API), langkah 3a](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel-api/)).
Rekaman itu memungkinkan Cloudflare *"to proxy"* lalu lintas hostname ke Tunnel. [FAQ Tunnel](https://developers.cloudflare.com/cloudflare-one/faq/cloudflare-tunnels-faq/)
juga menyebut rute hostname publik berjalan lewat *reverse proxy* Cloudflare. Jadi semua batas
proxy (ukuran body, timeout) ikut berlaku. Jalan keluar "DNS-only" dari halaman 413 **tidak tersedia**
untuk Tunnel, dan kalaupun dipakai tanpa Tunnel berarti membuka port, yang dilarang desain.

### 1.3 Batas waktu yang relevan

Dari [Connection limits](https://developers.cloudflare.com/fundamentals/reference/connection-limits/),
antara Cloudflare dan origin:

| Batas | Nilai | Error | Bisa diubah |
|---|---|---|---|
| Proxy Read Timeout | 125 s | 524 | Hanya zona Enterprise |
| Proxy Write Timeout | 30 s | 524 | Tidak |
| Proxy Idle Timeout | 900 s | 520 | Tidak |
| Complete TCP Connection | 19 s | 522 | Tidak |

- ⚠️ Catatan untuk angka "100 s" yang sering dikutip: dokumen resmi saat ini menulis **125 detik**.
  [Error 524](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-524/)
  menyebut origin tidak menjawab sebelum *"the default 125 seconds"*. Enterprise bisa menaikkannya sampai
  6.000 s. Saran resminya untuk proses panjang: **polling status**.
- Definisi Proxy Read Timeout di [pengaturan Cache Rules](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/):
  jeda *"between two successive read operations"* dari origin. Artinya yang dibatasi adalah jeda origin
  menjawab, bukan lama klien mengirim body. ⚠️ Perilaku saat klien mengirim satu potongan besar lewat
  jaringan lambat tidak dijelaskan di dokumen (apakah Cloudflare menahan body dulu atau meneruskannya
  langsung). Potongan yang lebih kecil memperkecil risiko ini dan memperkecil data yang hilang saat gagal.
- **Konsekuensi:** permintaan "bangun peta" tidak boleh menunggu hasil. API mengembalikan ID pekerjaan
  segera, dashboard melakukan polling `GET /jobs/{id}`. Ini sudah sesuai desain antrean.

---

## 2. Protokol unggah yang bisa dilanjutkan

### 2.1 Protokol tus 1.0.0

[Spesifikasi tus 1.0.0](https://tus.io/protocols/resumable-upload) (dirilis 25 Maret 2016):

- **Inti:** `HEAD` mengembalikan `Upload-Offset` (berapa byte yang sudah diterima server), lalu `PATCH`
  dengan `Content-Type: application/offset+octet-stream` melanjutkan dari offset itu. Header
  `Tus-Resumable` wajib di setiap permintaan dan jawaban.
- **Ekstensi:** Creation (`POST` + `Upload-Length`, server menjawab `Location`), Termination (`DELETE`),
  Expiration (`Upload-Expires`), metadata lewat `Upload-Metadata`.
- **Potongan:** klien *"MAY also use multiple small requests successively"*. Spesifikasi tidak mengatur
  ukuran potongan maksimum. `Tus-Max-Size` adalah batas ukuran total unggahan, bukan per potongan.

### 2.2 Klien: tus-js-client dan Uppy

| Klien | Lisensi | Versi (npm) | Catatan |
|---|---|---|---|
| [tus-js-client](https://github.com/tus/tus-js-client) | MIT | 4.3.1 | Pustaka protokol. Di peramban memakai XHR |
| [@uppy/tus](https://uppy.io/docs/tus/) ([repo Uppy](https://github.com/transloadit/uppy)) | MIT | 6.0.0 (Uppy 6.0.4, rilis 30 September 2026) | Pembungkus tus-js-client dengan UI Dashboard siap pakai |

**`chunkSize`** ([tus-js-client `docs/api.md`](https://github.com/tus/tus-js-client/blob/main/docs/api.md#chunksize)):

- Bawaan `Infinity`: seluruh berkas dikirim dalam **satu** `PATCH`.
- Dokumen memberi hanya dua alasan sah untuk mengisinya. Salah satunya: server atau proxy membatasi
  ukuran body, dan *"Reverse proxies and CDNs often impose such a limit"*. Dengan bawaan `Infinity`,
  permintaan ditolak `413` atau koneksinya ditutup, sering sebelum server tus melihatnya.
- Anjurannya: isi `chunkSize` **di bawah batas body terkecil** di sepanjang jalur ke server.
- Uppy memakai opsi yang sama: *"maximum size of a `PATCH` request body in bytes"*, bawaan `Infinity`
  ([uppy.io/docs/tus](https://uppy.io/docs/tus/)). Opsi lain: `retryDelays` bawaan `[0, 1000, 3000, 5000]` ms,
  `limit` bawaan 20 unggahan bersamaan, `withCredentials` bawaan `false`.

**Untuk Cloudflare Free: `chunkSize: 50 * 1024 * 1024`.** Satu video 540 MB = 11 `PATCH`. Satu sesi
(dua video) = 22 `PATCH`. Potongan jauh di bawah 100 MB juga berarti putus koneksi hanya mengulang paling
banyak 50 MiB.

### 2.3 Server: tusd, pustaka Python, atau endpoint sendiri

**tusd** ([repo](https://github.com/tus/tusd), MIT, rilis v2.10.1 pada 16 September 2026, dikelola tim tus):

- Image `tusproject/tusd` ([instalasi](https://tus.github.io/tusd/getting-started/installation/)).
  Dari [`Dockerfile`](https://github.com/tus/tusd/blob/main/Dockerfile): Alpine, `EXPOSE 8080`, berjalan
  sebagai pengguna `tusd` (uid 1000), folder kerja `/srv/tusd-data`.
- [Konfigurasi](https://tus.github.io/tusd/getting-started/configuration/): port bawaan 8080, jalur
  pembuatan unggahan bawaan `/files/` (ubah dengan `-base-path`), penyimpanan bawaan `./data`
  (`-upload-dir`), tanpa batas ukuran kecuali `-max-size` diisi, `-behind-proxy` untuk menghormati
  header `X-Forwarded-*`, `-disable-download`, `-disable-termination`, CORS aktif bawaan.
- [Hooks](https://tus.github.io/tusd/advanced-topics/hooks/) (sumber:
  [`docs/_advanced-topics/hooks.md`](https://github.com/tus/tusd/blob/main/docs/_advanced-topics/hooks.md)):

| Hook | Memblokir? | Kapan | Dipakai untuk |
|---|---|---|---|
| `pre-create` | Ya | Sebelum unggahan dibuat | Autentikasi, validasi metadata, ID unggahan sendiri (`ChangeFileInfo`), tolak (`RejectUpload`) |
| `pre-finish` | Ya | Semua data diterima, **sebelum** jawaban terakhir dikirim | Mencatat pekerjaan sebelum klien diberi tahu selesai. **Tidak aktif bawaan** |
| `post-finish` | Tidak | Setelah jawaban dikirim | Pemrosesan lanjut. Dokumen: hook *"usually not retried"* |

- Hook HTTP diaktifkan dengan `-hooks-http <url>`. Batas waktu bawaan 15 s, jawaban maksimal 5 KiB,
  diulang 3 kali pada `500` atau galat jaringan dengan jeda 1 s (`-hooks-http-retry`,
  `-hooks-http-backoff`). Kalau hook yang memblokir gagal, tusd menjawab klien `500`.
- Isi permintaan hook memuat `Upload.ID`, `Size`, `MetaData`, `Storage.Path`, dan **semua header
  permintaan klien** (`HTTPRequest.Header`). `-hooks-http-forward-headers` meneruskan header tertentu
  langsung sebagai header permintaan hook.
- Aktifkan hook tambahan dengan `-hooks-enabled-events`. ⚠️ Dokumen tusd tidak konsisten soal
  `post-receive` (tabel bilang aktif bawaan, paragraf lain bilang tidak). Tidak berpengaruh karena
  `post-receive` tidak dibutuhkan.

**Pustaka Python:**

| Pustaka | Lisensi | Status | Catatan |
|---|---|---|---|
| [edihasaj/tuspyserver](https://github.com/edihasaj/tuspyserver) (PyPI `tuspyserver`) | MIT | v4.4.2 di PyPI 17 September 2026, push terakhir 28 September 2026, 36 bintang | Router FastAPI. Creation, creation-with-upload, expiration, termination. Callback `on_upload_complete` dan `upload_complete_dep` (dependency FastAPI), `pre_create_dep` untuk izin. Satu pengelola utama |
| [liviaerxin/fastapi-tusd](https://github.com/liviaerxin/fastapi-tusd) | MIT | Rilis PyPI terakhir 0.100.2 (10 Mei 2024), push terakhir 3 Juni 2025, 13 bintang | Tidak aktif. Jangan dipakai |
| kirill-ilichev/TusFastAPIServer | Tidak ada lisensi terdeteksi (API GitHub) | Push terakhir Januari 2025 | Tanpa lisensi = tidak boleh dipakai ulang |

Pembanding bahasa lain yang aktif dan MIT: `tus/tus-node-server`, `tusdotnet`, `tus-java-server` (API
GitHub, September 2026). Tidak relevan untuk stack Python.

**Endpoint potongan buatan sendiri:** misalnya `PATCH /uploads/{id}` dengan offset dan `HEAD` untuk
menanyakan offset. Ini pada dasarnya **menulis ulang tus**: harus menangani offset yang tidak cocok,
penulisan parsial saat koneksi putus, dan konkurensi, lalu klien JavaScript-nya juga harus ditulis dan
diuji. Tidak ada keuntungan dibanding tusd selain satu container lebih sedikit.

---

## 3. FastAPI dan Starlette untuk unggahan besar

- **`UploadFile`** ([FastAPI, Request Files](https://fastapi.tiangolo.com/tutorial/request-files/)):
  memakai *spooled file*, di memori sampai batas tertentu lalu pindah ke disk, dan membuka objek
  `SpooledTemporaryFile` Python. Di kode Starlette 1.7.0 (`starlette/formparsers.py`),
  `MultiPartParser.spool_max_size = 1024 * 1024` (1 MB). Berkas sementara ada di folder temp sistem
  (di container: `/tmp`), jadi video 540 MB **ditulis dua kali** (ke temp, lalu disalin ke folder data).
- **`request.stream()`** ([Starlette, Requests](https://github.com/kludex/starlette/blob/main/docs/requests.md)):
  membaca body per potongan tanpa menyimpan semuanya di memori. Setelah itu `.body()`, `.form()`,
  `.json()` tidak bisa dipanggil lagi. Ini cara yang benar untuk endpoint potongan buatan sendiri:
  tulis langsung ke berkas tujuan.
- **Batas ukuran total:** `request.form(max_files, max_fields, max_part_size)` hanya membatasi field
  non-berkas. Berkas di-*spool* dan **tidak** dibatasi `max_part_size`. Untuk batas body total, Starlette
  menyediakan `max_body_size` dan `RequestBodyLimitMiddleware` (ada di Starlette 1.7.0,
  `starlette/middleware/body_limit.py`). FastAPI 0.141.1 tidak meneruskan parameter `max_body_size`
  (tidak ada di kode terpasang), jadi pasang middleware-nya dengan `app.add_middleware(...)`.
- **Relevansi:** kalau tusd yang menerima video, FastAPI tidak pernah menerima body besar. `/localize`
  yang ada tetap memakai `UploadFile` dengan batas 20 MB (`server/app.py`), dan itu sudah benar.

---

## 4. Antrean pekerjaan dan pekerja GPU

### 4.1 `FOR UPDATE SKIP LOCKED`

[PostgreSQL 17, SELECT, bagian The Locking Clause](https://www.postgresql.org/docs/17/sql-select.html#SQL-FOR-UPDATE-SHARE):
`SKIP LOCKED` melewati baris yang tidak bisa langsung dikunci. Dokumen menyebut ini tidak cocok untuk
kerja umum, tetapi berguna *"with multiple consumers accessing a queue-like table"*. Kunci tingkat tabel
`ROW SHARE` tetap diambil seperti biasa. Dengan satu pekerja, `SKIP LOCKED` tetap berguna: pekerja kedua
bisa ditambah nanti tanpa mengubah kueri.

### 4.2 `LISTEN/NOTIFY` sebagai pembangun

[PostgreSQL 17, NOTIFY](https://www.postgresql.org/docs/17/sql-notify.html):

- Notifikasi di dalam transaksi baru dikirim **setelah commit**. Pas untuk "sisipkan pekerjaan lalu beri
  tahu".
- Notifikasi hanya sampai ke sesi yang sudah `LISTEN`. Kalau pekerja sedang mati, notifikasi hilang.
- Payload di bawah 8000 byte. Notifikasi identik dalam satu transaksi digabung.
- **Konsekuensi:** `NOTIFY` hanya mempercepat. Pekerja tetap harus memeriksa tabel saat menyala dan secara
  berkala (misalnya tiap 30 s). Untuk beban "beberapa kali seminggu", polling saja sudah cukup.

### 4.3 Pekerja GPU di Docker Compose

[Docker docs, GPU support](https://docs.docker.com/compose/how-tos/gpu-support/):

```yaml
services:
  worker:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1          # atau device_ids: ["0"], tidak boleh keduanya
              capabilities: [gpu]
```

- `capabilities` **wajib**, tanpa itu deploy gagal. `count` berupa angka atau `all`. `count` dan
  `device_ids` saling eksklusif.
- Pola ini sudah dipakai `deploy/compose.gpu.yaml` untuk `api` (`count: all`). Pekerja membutuhkan
  blok yang sama. Kalau `api` tetap CPU (sesuai klaim latensi tanpa GPU), GPU RTX 3070 hanya dipakai
  pekerja.

---

## 5. Cloudflare Access

### 5.1 Validasi JWT di origin

[Validate JWTs](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/):

- Token ada di header **`Cf-Access-Jwt-Assertion`**. Cookie `CF_Authorization` juga dikirim peramban,
  tetapi dokumen menganjurkan memvalidasi header karena cookie *"is not guaranteed to be passed"*.
- Kunci publik: `https://<team-name>.cloudflareaccess.com/cdn-cgi/access/certs`. Kunci dirotasi tiap
  6 minggu, kunci lama tetap berlaku 7 hari.
- Cek `aud` terhadap **Application Audience (AUD) Tag** (dashboard: Zero Trust, Access controls,
  Applications, Configure, Additional settings) dan `iss` terhadap domain tim. Contoh Python resmi memakai
  PyJWT ([repo](https://github.com/jpadilla/pyjwt), MIT, 2.15.1). PyJWT belum ada di `uv.lock`.
- **`cloudflared` bisa memvalidasi sendiri:** parameter origin `access` (`required`, `teamName`,
  `audTag`) membuat `cloudflared` memvalidasi JWT Access sebelum meneruskan ke origin
  ([Origin parameters](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/cloudflared-parameters/origin-parameters/)).
  Ini menutup celah kalau aplikasi Access salah konfigurasi, tetapi API tetap perlu membaca JWT untuk
  tahu **siapa** yang mengunggah atau menerbitkan.

### 5.2 One-time PIN dan jumlah pengguna

- [One-time PIN](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/):
  alternatif tanpa penyedia identitas. PIN berlaku 10 menit. Email hanya dikirim kalau alamatnya lolos
  kebijakan Access, jadi kebijakan "Emails: daftar alamat" sekaligus menjadi daftar izin.
- **Paket gratis ⚠️ sekitar 50 pengguna.** [Halaman produk Access](https://www.cloudflare.com/products/zero-trust/zero-trust-network-access/)
  menulis paket gratis *"Best for teams under 50 users"*, dan
  [blog peluncuran 2020](https://blog.cloudflare.com/teams-plans/) menyebut *"up to 50 users"*. Tabel harga
  tidak terbaca utuh saat pengecekan. [Seat management](https://developers.cloudflare.com/cloudflare-one/team-and-resources/users/seat-management/):
  kursi terpakai pada setiap login Access, dan dibebaskan dengan menghapus pengguna dari organisasi.
  Untuk pemilik repo, beberapa anggota lab, dan pembimbing, batas ini jauh dari tercapai.
- Batas akun lain ([Account limits](https://developers.cloudflare.com/cloudflare-one/account-limits/)):
  500 aplikasi Access, 1.000 tunnel per akun. Tunnel kedua untuk PC lab tidak bermasalah.

### 5.3 Unggahan `fetch`/XHR lewat Access, dan CORS

- [Authorization cookie](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/):
  token aplikasi disimpan sebagai cookie di domain yang dilindungi, `HttpOnly` aktif bawaan, `SameSite`
  bisa `None`, `Lax`, atau `Strict`. Durasi sesi mengikuti pengaturan global, lalu aplikasi, bawaan
  24 jam.
- [CORS dengan Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/cors/):
  *"CORS checks do not occur on the same domain."* Lintas domain, preflight `OPTIONS` tidak membawa cookie
  sehingga dijawab `403`. Solusinya "Bypass OPTIONS requests to origin", respons CORS dari Cloudflare, atau
  Worker. Untuk XHR, dokumen menganjurkan `credentials: 'same-origin'`.
- [MDN `withCredentials`](https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/withCredentials):
  *"Setting `withCredentials` has no effect on same-origin requests."* Jadi pada satu hostname, Uppy dengan
  `withCredentials: false` bawaan tetap mengirim cookie Access.
- **Kesimpulan:** taruh dashboard, API, dan tusd di **satu hostname** (misalnya `vps.rockhead07.tech`),
  dibedakan dengan jalur. Aturan ingress `cloudflared` bisa mencocokkan `hostname` dan `path` (regex Go),
  dan wajib diakhiri aturan penampung
  ([Configuration file](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/)).
- ⚠️ Belum terverifikasi: apa yang terjadi pada unggahan yang sedang berjalan saat sesi Access habis
  (kemungkinan XHR diarahkan ke halaman login dan gagal). Mitigasi: durasi sesi aplikasi yang cukup
  panjang (misalnya 24 jam), dan tus melanjutkan dari offset setelah login ulang.
- ⚠️ **Konflik dengan aplikasi navigasi:** spesifikasi menulis aplikasi navigasi **tanpa login**. Kalau
  `/localize` berada di hostname yang sama di balik kebijakan OTP, ponsel tidak bisa menjangkaunya. Perlu
  hostname atau aplikasi Access terpisah untuk `/localize` (misalnya token layanan, belum diriset). Ini di
  luar cakupan dokumen ini tetapi harus diputuskan sebelum `/localize` dibuka ke internet.

---

## 6. Laporan 3D plotly

Dibaca dari docstring `write_html` di plotly 7.1.0 terpasang (`plotly/basedatatypes.py`), yang membundel
plotly.js 4.1.1 (`plotly.min.js` 4.815.814 byte). Halaman resmi
[Interactive HTML Export](https://plotly.com/python/interactive-html-export/) mengonfirmasi berkas
bawaan *"very large (5Mb+)"* karena memuat plotly.js.

| `include_plotlyjs` | Isi HTML | Catatan |
|---|---|---|
| `True` (bawaan) | plotly.js disisipkan (sekitar 4,8 MB) | Mandiri, bisa luring. Inilah sebab laporan sekitar 5 MB |
| `'cdn'` | `<script src="https://cdn.plot.ly/plotly-4.1.1.min.js">` dengan hash SRI (`plotly/io/_html.py`) | Sekitar 4,8 MB lebih kecil. Peramban peninjau butuh akses ke `cdn.plot.ly` |
| `'directory'` | Merujuk `plotly.min.js` di folder yang sama, disalin sekali per folder | Bisa luring, satu salinan per folder |
| String berakhiran `.js` | Merujuk path itu, misalnya `/static/plotly-4.1.1.min.js` | Satu salinan di server untuk semua laporan, satu origin |
| `False` | Tanpa plotly.js | Hanya untuk `full_html=False` yang disisipkan ke halaman yang sudah memuat plotly.js |

- `full_html=False` menghasilkan satu `<div>` saja. Cocok kalau dashboard sendiri memuat plotly.js.
- **Usulan:** tulis laporan dengan `include_plotlyjs="/static/plotly-4.1.1.min.js"` dan sajikan satu salinan
  dari FastAPI. Laporan menjadi sebesar datanya saja, tidak bergantung CDN pihak ketiga, dan semua berkas
  berada di balik Access yang sama. Tampilkan di dashboard dengan `<iframe src="/reports/{id}/map.html">`
  dari origin yang sama. ⚠️ Pengaruh atribut `sandbox` pada plotly belum diuji.

---

## 7. Ketentuan Cloudflare tentang video dan berkas besar

- [Service-Specific Terms, Application Services](https://www.cloudflare.com/service-specific-terms-application-services/#content-delivery-network-free-pro-or-business)
  (diperbarui 28 September 2026), bagian CDN Free, Pro, atau Business: selain Enterprise, layanan berbayar
  (Developer Platform, Images, Stream) wajib dipakai *"to serve video and other large files via the CDN"*.
  Cloudflare boleh membatasi akses kalau CDN dipakai tanpa layanan itu untuk menyajikan video atau
  berkas besar dalam porsi tidak wajar.
- [Tunnel FAQ](https://developers.cloudflare.com/cloudflare-one/faq/cloudflare-tunnels-faq/) (bagian lalu
  lintas berkas besar dan streaming): ketentuan itu **berlaku juga untuk rute hostname publik Tunnel**.
  Rute jaringan privat tidak terkena karena tidak menerbitkan aplikasi ke internet.
- [Delivering videos with Cloudflare](https://developers.cloudflare.com/fundamentals/reference/policies-compliances/delivering-videos-with-cloudflare/):
  menyarankan Stream. Konten yang tampak menyajikan video tanpa layanan berbayar bisa dialihkan atau
  ditindak.
- ⚠️ **Unggahan dari klien ke origin tidak disebut** di ketiga sumber. Kata kuncinya "serve" (menyajikan
  ke pengunjung). Mengunggah sekitar 1 GB per sesi, beberapa kali seminggu, oleh beberapa orang, kecil
  kemungkinannya dianggap "disproportionate", tetapi ini tafsiran, bukan pernyataan Cloudflare.
- **Konsekuensi desain:** jangan menyajikan video kembali lewat Tunnel (tanpa pemutar video di
  dashboard, `-disable-download` di tusd). Tampilkan frame contoh (JPEG kecil) dan laporan saja.

---

## 8. Next.js static export

[Static Exports](https://nextjs.org/docs/app/guides/static-exports) (versi dokumen 16.3.8, diperbarui
25 Agustus 2026; sama dengan dokumen v16.2.9 di context7):

- **Tidak didukung:** rute dinamis dengan `dynamicParams: true` atau tanpa `generateStaticParams()`, Route
  Handler yang membaca `Request`, cookies, rewrites, redirects, headers, Proxy, ISR, optimasi gambar dengan
  loader bawaan, Draft Mode, **Server Actions**, Intercepting Routes. Pages Router API routes juga ditolak.
- Route Handler hanya `GET` dan dirender statis saat build.
- **Konsekuensi:** ID sesi dan versi peta baru ada saat runtime, jadi `generateStaticParams` tidak bisa
  dipakai. Pakai parameter query (`/session?id=12`) dengan Client Component yang mengambil data dari API
  FastAPI. Semua mutasi (unggah, terbitkan) lewat API FastAPI, bukan Server Actions.
- FastAPI menyajikan folder `out/` dengan `StaticFiles(directory=..., html=True)`: mode HTML memuat
  `index.html` untuk direktori dan `404.html` kalau ada
  ([Starlette StaticFiles](https://github.com/kludex/starlette/blob/main/docs/staticfiles.md)).

---

## Implikasi untuk desain

### Rekomendasi konkret

1. **Satu permintaan maksimal 50 MiB.** Uppy `@uppy/tus` dengan `chunkSize: 50 * 1024 * 1024`. Tanpa ini,
   video 540 MB pasti ditolak `413` di Cloudflare Free (bagian 1).
2. **Server unggahan: tusd** sebagai container di Compose, `-upload-dir` di volume yang juga dipasang
   (baca saja) ke pekerja, `-base-path /files/`, `-behind-proxy`, `-disable-download`, `-max-size` sekitar
   1 GB, hook `-hooks-http http://api:8000/internal/tus-hook` dengan
   `-hooks-enabled-events pre-create,pre-finish`. Alasan: implementasi rujukan dari pemilik protokol,
   MIT, aktif, dan kode protokol yang harus kita tulis = nol.
3. **Pekerjaan dicatat di `pre-finish`, bukan `post-finish`.** `pre-finish` memblokir, jadi klien baru
   diberi tahu selesai setelah baris pekerjaan masuk PostgreSQL. `post-finish` tidak diulang kalau
   pemrosesan gagal (bagian 2.3). Hook hanya menyisipkan baris, tidak menjalankan pembangunan peta.
4. **Autentikasi berlapis, dengan satu pemilik keputusan:**
   - Cloudflare Access (kebijakan email + OTP) di tepi.
   - `cloudflared` dengan `originRequest.access` (`required: true`, `teamName`, `audTag`) sebagai pagar
     kedua, supaya salah konfigurasi di dashboard tidak membuka origin.
   - FastAPI memvalidasi `Cf-Access-Jwt-Assertion` (PyJWT, kunci dari endpoint `certs`) dalam **satu
     dependency** yang dipakai rute API **dan** hook `pre-create` tusd (header klien ada di
     `HTTPRequest.Header` isi hook). Email dari JWT dicatat sebagai pengunggah dan penyetuju.
5. **Satu hostname**, misalnya `vps.rockhead07.tech`: ingress `path: ^/files/` ke `tusd:8080`, sisanya ke
   `api:8000`. Tanpa CORS, tanpa preflight yang ditolak Access.
6. **`cloudflared` sebagai service Compose** di jaringan internal, sehingga `api` dan `tusd` tidak perlu
   `ports`. `deploy/compose.yaml` sekarang memublikasikan `8000` ke host. Itu tidak membuka port ke
   internet (tetap di belakang NAT), tetapi bisa dijangkau dari LAN lab. Pertimbangkan menghapusnya setelah
   Tunnel jalan.
7. **Semua proses panjang asinkron.** `POST` apa pun menjawab di bawah beberapa detik, status lewat
   polling. Batas 125 s tidak bisa dinaikkan di Free.
8. **Laporan 3D:** `include_plotlyjs` diarahkan ke satu salinan `plotly.min.js` yang disajikan FastAPI.
   Jangan menyajikan video kembali lewat Tunnel.
9. **Pekerja:** service Compose terpisah dengan reservasi GPU (bagian 4.3), polling tabel pekerjaan dengan
   `SKIP LOCKED`. `LISTEN/NOTIFY` belum perlu.

### Tiga pendekatan kandidat

| | A. Uppy + tusd + hook ke FastAPI (usulan) | B. Uppy + `tuspyserver` di dalam FastAPI | C. Endpoint potongan buatan sendiri |
|---|---|---|---|
| Container tambahan | tusd, cloudflared | cloudflared | cloudflared |
| Kode protokol yang ditulis | Nol. Hanya endpoint hook (auth + sisipkan pekerjaan) | Nol. Konfigurasi router + callback | Semua: offset, `HEAD`, penulisan parsial, klien JS |
| Kematangan | Implementasi rujukan tim tus, MIT, rilis September 2026 | MIT, aktif, 36 bintang, satu pengelola utama | Belum teruji sama sekali |
| Unggahan membebani API? | Tidak, proses terpisah | Ya, berbagi proses dengan `/localize` (model torch dan kunci global di `server/app.py`) | Ya |
| Titik lemah | Satu layanan lagi untuk dipantau. Autentikasi lewat hook harus benar | Ketergantungan pada proyek kecil. Unggahan besar bersaing dengan lokalisasi | Waktu pengembangan dan bug yang tidak perlu |
| Kapan dipilih | Bawaan | Kalau jumlah container harus minimum dan beban unggah sangat jarang | Tidak dianjurkan |

Jalan yang **ditolak:** satu `POST` multipart berisi seluruh video (ditolak `413` di atas 100 MB), dan
rekaman DNS-only tanpa proxy (butuh port terbuka, melanggar aturan akses).

### Yang bertentangan atau menambah desain terkunci

1. **Video, bukan foto kunci.** Spesifikasi bagian 2 memilih foto kunci dari aplikasi capture dan menulis
   "tanpa video". Website ini melayani jalur Tahap 0 dan PA opsi (a) (kamera bawaan + `extract_frames.py`),
   jadi tidak bertentangan dengan tahapan, tetapi alur unggah video perlu dicatat sebagai jalur tersendiri,
   bukan pengganti aplikasi capture.
2. **Container bertambah.** Spesifikasi menyebut PostgreSQL, API, pekerja. Pendekatan A menambah tusd dan
   cloudflared. Tidak melanggar prinsip "satu host, folder disk", hanya menambah daftar layanan.
3. **Keputusan terbuka nomor 4 (cara login)** terjawab untuk website: Cloudflare Access OTP, tanpa akun
   lokal. Peran (pemeta, peninjau, admin) tetap perlu dipetakan dari email di JWT ke tabel sendiri.
4. **`/localize` untuk aplikasi navigasi tanpa login** tidak bisa berada di balik kebijakan OTP yang sama
   (bagian 5.3). Perlu keputusan terpisah.
5. **Ketentuan video Cloudflare** tidak melarang unggahan secara eksplisit ⚠️, tetapi melarang
   menyajikan video. Dashboard tidak boleh memutar ulang video lewat Tunnel.
