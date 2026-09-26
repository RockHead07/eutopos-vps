# CI/CD

Cara repo ini diperiksa otomatis sekarang, dan rencana build serta deployment layanan nanti. Klaim
yang belum terverifikasi ke sumber primer ditandai ⚠️.

## 1. Prinsip

Semua prinsip di bawah berasal dari panduan keamanan GitHub Actions
([Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)), kecuali
yang ditandai lain.

| Prinsip | Penerapan di repo ini |
|---|---|
| **Action dipin ke SHA commit penuh.** Menurut GitHub, ini satu-satunya cara memakai action sebagai rilis yang tidak bisa diubah | Semua `uses:` memakai SHA, versinya ditulis di komentar. Dependabot yang memperbaruinya |
| **Hak token minimum.** Izin bawaan `GITHUB_TOKEN` sebaiknya baca saja, dinaikkan per job hanya kalau perlu | `permissions: {}` di tingkat workflow, `contents: read` per job |
| **Self-hosted runner hampir tidak pernah dipakai di repo publik**, karena siapa pun bisa membuka pull request yang menjalankan kode di runner itu | Repo ini publik. **Server instansi tidak boleh dijadikan runner GitHub** (lihat bagian 4) |
| **Kredensial tidak tertinggal di runner** | `persist-credentials: false` di setiap checkout |
| **Versi alat dikunci.** CI dan laptop memakai versi yang sama persis | Versi uv dipin lewat `required-version` di `pyproject.toml` (dibaca `setup-uv` di CI, ditegakkan uv lokal). Alat pengembangan dikunci di `uv.lock`, dan CI memakai `uv sync --locked` |
| **Perintah CI bisa dijalankan lokal** | Lihat bagian 3 |
| **Pembaruan dependensi ditunda sebentar** (cooldown), supaya rilis bermasalah sempat ditarik sebelum masuk | Dependabot `cooldown: 7 hari` |

## 2. Yang sudah ada (fase 0, sebelum ACC)

| Berkas | Isi |
|---|---|
| `.github/workflows/ci.yml` | Job **Lint dan format Python**: `ruff check` dan `ruff format --check`. Job **Audit keamanan workflow**: [zizmor](https://github.com/zizmorcore/zizmor) memeriksa workflow dari pola berbahaya (injeksi, token berlebih, action tidak dipin) |
| `.github/dependabot.yml` | PR mingguan untuk SHA action dan alat di `uv.lock`, dikelompokkan jadi satu PR per ekosistem |
| `pyproject.toml`, `uv.lock` | Konfigurasi ruff dan versi alat. **Belum** memuat dependensi runtime (torch, hloc) |

CI berjalan pada push ke `main`, setiap pull request, dan manual (`workflow_dispatch`). PR yang
diperbarui membatalkan run lama untuk PR yang sama.

**Sengaja belum ada:**
- **Unit test.** Belum ada kode layanan yang diuji. Mulai fase 1.
- **Smoke test pipeline hloc** (instalasi torch CPU + hloc, lalu `spike/run.py` pada data contoh
  Sacré-Cœur). Berguna untuk menangkap instalasi yang rusak, tapi **waktunya di runner GitHub tidak
  boleh dipakai sebagai hasil**, karena runner GitHub bukan salah satu dari T1, T2, atau T3. Belum
  dibuat karena tidak bisa divalidasi dari lingkungan penyusun (unduhan PyTorch diblokir). Usulan:
  workflow manual, bukan gerbang PR.
- **Build dan deploy.** Belum ada layanan dan belum ada Dockerfile.

## 3. Menjalankan pemeriksaan yang sama di laptop

```bash
uv sync                       # memasang ruff dan zizmor sesuai uv.lock
uv run ruff check .           # lint
uv run ruff format .          # merapikan format (CI hanya memeriksa, tidak mengubah)
uv run zizmor .github/        # audit workflow
```

Mengubah versi alat: `uv add --dev ruff@<versi>` atau `uv lock --upgrade-package ruff`, lalu commit
`pyproject.toml` dan `uv.lock` bersamaan.

**Versi uv** dipin di `pyproject.toml` (`required-version`). uv dengan versi lain menolak berjalan
dan menyarankan `uv self update <versi>`. ⚠️ Belum dicek apakah Dependabot ikut memperbarui pin ini. Anggap tidak, dan naikkan manual:
ubah `required-version`, jalankan `uv self update <versi>`, lalu pastikan `uv sync --locked` lolos.

`.claude/` dikecualikan dari ruff karena isinya skill pihak ketiga yang disalin apa adanya.

## 4. Rencana (fase 1 dan 2, setelah ACC dan setelah layanan ada)

### Fase 1: continuous integration layanan

1. **Dependensi runtime masuk `pyproject.toml`**: torch dari indeks CPU PyTorch dan hloc dipin ke
   commit. Langkah manual di `docs/spike-plan.md` bagian 12 digantikan `uv sync`.
2. **Unit test** (pytest) untuk bagian yang dibangun sendiri: kontrak API `/localize` dan `/health`,
   transformasi koordinat, dan validasi masukan. Pipeline hloc sendiri tidak diuji ulang.
3. **Image Docker multi-stage**, PyTorch CPU, dibangun di CI pada setiap PR (tanpa dipublikasikan)
   supaya Dockerfile yang rusak ketahuan lebih awal.
4. **Rilis bertag** (`v*`): image dipublikasikan dengan tag versi dan dirujuk lewat **digest**,
   disertai provenance build. ⚠️ Pilihan action untuk attestation belum dicek.

### Fase 2: deployment ke server instansi

**Best practice untuk kondisi ini: deployment berbasis tarik (pull).** Server instansi menarik
image versi tertentu (lewat digest), lalu menjalankannya. GitHub tidak pernah masuk ke server.
Alasannya:
- Server instansi berada di jaringan internal, dan alamatnya tidak boleh muncul di repo publik.
- Self-hosted runner di repo publik dilarang (bagian 1).
- Kunci SSH server yang disimpan sebagai secret GitHub akan memberi akses masuk ke jaringan instansi
  dari luar. Risiko ini tidak perlu diambil.

**Rollback** cukup menjalankan kembali digest sebelumnya.

**Keputusan yang harus ditanyakan ke pembimbing dulu:**

| Pertanyaan | Kenapa |
|---|---|
| Registry image boleh di GitHub Container Registry, atau harus di dalam instansi? | Arahan "fully local" berlaku untuk layanan. Runtime tidak bergantung pada registry setelah image ditarik, tapi menarik dari luar tetap lalu lintas keluar dari server instansi. Kompromi: registry di dalam instansi, atau image dibangun di server dari tag git |
| Server instansi punya akses internet keluar? | Menentukan apakah server bisa menarik image dan bobot model sendiri |

**Bobot model tidak boleh diunduh saat layanan menyala.** Server bisa saja tanpa internet, dan
layanan harus fully local. Bobot dimasukkan ke image atau dipasang sebagai volume. ⚠️ Kalau image
dipublikasikan secara publik, bobot di dalamnya ikut **didistribusikan ulang**, jadi lisensi bobot
ALIKED, LightGlue, dan retrieval global (MegaLoc atau NetVLAD) harus dicek dulu. Lisensi kode
repo-nya tidak otomatis berlaku untuk bobotnya.

## 5. Pengaturan GitHub yang harus diaktifkan pemilik repo

Berkas di repo tidak bisa mengaktifkan ini. Aktifkan lewat **Settings** repo:

1. **Rulesets untuk `main`**: wajib lewat pull request, dan wajib lolos status check
   `Lint dan format Python` dan `Audit keamanan workflow`. Larang force push.
2. **Actions > General**: aktifkan kebijakan yang mewajibkan action dipin ke SHA penuh (disebut di
   panduan keamanan GitHub). Izin bawaan workflow: **read**.
3. **Advanced Security**: secret scanning dan push protection, Dependabot alerts dan security
   updates, serta code scanning **default setup** (CodeQL). ⚠️ Ketersediaan gratis untuk repo publik
   belum saya cocokkan ke halaman harga GitHub. Cek di halaman Settings.

Secret scanning hanya mengenali pola kredensial yang dikenalnya. **NRP, nama server internal, dan
alamat IP tidak tertangkap.** Aturan repo publik di `CLAUDE.md` tetap harus diperiksa manual sebelum
commit.
