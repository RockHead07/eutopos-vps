# Brief serah terima: gerbang foto uji dan publish otomatis (Fase A)

Ditulis 2026-11-19 untuk agen pelaksana. Disusun dengan kerangka CO-STAR. Diperiksa terhadap `origin/main` di
`99a9c31` (hierarki gedung tahap 1, migrasi 0008). Bila `origin/main` sudah maju, ulangi pemeriksaan di bagian
"Koreksi terhadap rencana" sebelum mulai.

---

## C. Context (konteks)

eutopos-vps adalah Visual Positioning System lokal untuk navigasi indoor: FastAPI + SQLModel + Alembic + PostgreSQL,
pekerja pembangun peta (hloc ALIKED + LightGlue, pycolmap), dashboard Next.js static export. Production berjalan di
PC lab dengan **auto-deploy dari `main`** (timer systemd, `deploy/autodeploy.sh`), dan container API menjalankan
`alembic upgrade head` saat menyala. Jadi apa pun yang di-merge ke `main` langsung berjalan di production.

Arah produk yang dikunci pemilik repo (Bagus) pada 2026-11-19:
- Jalur publish utama adalah **aplikasi capture terpisah** (`eutopos-mobile`, Build Profile kedua) yang mengirim foto
  kunci berpose ARCore. Video lewat website tetap jalur cadangan.
- Peta harus dinilai otomatis sebelum terbit. Saat ini tombol Terbitkan bisa menerbitkan peta yang putus.
- Latar riset: `docs/map-quality-verification-research.md`. Spesifikasi aplikasi capture:
  `eutopos-mobile/docs/specs/2026-11-05-mode-rekam-peta-irisan-1-design.md`.

Urutan program (hanya Fase A untukmu):

| Fase | Isi | Siapa |
|---|---|---|
| **A** | **Gerbang foto uji dan publish otomatis di server (brief ini)** | **Kamu** |
| B | Spike di ponsel: resolusi gambar ARCore, foto kunci 0,4 m vs video 2 fps | Bagus (butuh ponsel dan lorong) |
| C | Aplikasi capture irisan 1, server menerima paket foto berpose | Rencana terpisah, belum ditulis |
| D | Skala dari pose ARCore dan metode `known_distance` di `align.json` | Rencana terpisah, belum ditulis |

## O. Objective (tujuan)

Kerjakan rencana `D:/Dev/Projects/eutopos-vps/docs/plans/2026-11-05-gerbang-publish-otomatis.md` Task 1 sampai 5
(berkas rencana, spesifikasinya `docs/specs/2026-11-05-capture-publish-otomatis-multi-org-design.md`, riset, dan
brief ini **belum ter-commit**, jadi tidak ada di worktree baru; baca dari checkout utama dengan path absolut,
hanya baca), **dengan koreksi di bawah**
yang mengalahkan isi rencana bila bertentangan. Hasil akhir: setelah pekerja membangun peta, gerbang menilai foto uji
dan menandai versi `ready`, `candidate` (ditahan), atau `rejected` dengan alasan; penerbit otomatis menerbitkan versi
`ready` **hanya bila diaktifkan lewat variabel lingkungan**.

### Koreksi terhadap rencana (wajib, sudah diverifikasi di `origin/main` 99a9c31)

1. **Publish otomatis harus opt-in (keputusan keamanan, baru).** Rencana lama menyalakan `publish_loop` setiap kali
   `DATABASE_URL` ada. Itu berarti merge langsung mengganti peta yang dilayani production tanpa orang. Tambahkan
   `auto_publish_enabled()` di `server/active_map.py` dengan pola yang sama seperti `splat_auto_enabled()` di
   `server/worker.py` (`EUTOPOS_AUTO_PUBLISH` bernilai `1/true/yes/on`, bawaan mati). `lifespan` hanya memulai
   `publish_loop` bila fungsi itu benar. Tes: `test_publish_loop_not_started_without_flag` dan
   `test_auto_publish_enabled_parses_flag` (parametrize nilai hidup, mati, kosong). Penilaian gerbang di pekerja tetap
   selalu jalan; yang opt-in hanya penerbitan.
2. **`Status` di `server/db.py` baris 15** sudah berisi `candidate`, `published`, `rejected`, `retired`. Cukup tambah
   `ready`. Tanpa migrasi Alembic (kolom string; indeks parsial hanya peduli `published`).
3. **Tes daftar tahap.** `tests/test_worker.py` sekitar baris 594 meng-assert
   `stages == ["gpu_wait", "extract", "build", "inspect", "register"]`. Setelah Task 3 tahap `gate` muncul setelah
   `register`. Perbarui assert itu menjadi daftar lengkap yang baru, jangan dilonggarkan.
4. **Assert summary** yang disebut rencana "sekitar baris 105" ada di sekitar **baris 112**
   (`job.summary == {"run": ..., "inspect": ...}`). Tambahkan kunci `"gate"` dengan keputusan `hold`, jangan
   melonggarkan.
5. **Splat.** `process()` memanggil `queue_splat(session, version.id)` setelah `jobs.finish`. Jalur `reject` keluar
   sebelum itu, jadi peta yang ditolak tidak diantrekan 3D. Itu disengaja; tambahkan tes
   `test_gate_reject_does_not_queue_splat` (dengan `EUTOPOS_SPLAT_AUTO=1` lewat `monkeypatch.setenv`).
6. **Dashboard memakai i18n.** Label status di `web/app/maps/page.tsx` (sekitar baris 117) memakai
   `t("status.<nilai>")`. Tambahkan kunci `status.ready` dan `status.rejected`, serta label tahap `gate`, di
   **`web/lib/i18n/id.ts` dan `web/lib/i18n/en.ts`**. Jangan menulis label langsung di komponen. Bila kunci
   `status.rejected` sudah ada, pakai ulang.
7. **Hierarki gedung (0008)** tidak berubah oleh pekerjaan ini. `navigation_ready` tetap diturunkan dari versi
   terbit + alignment + graf. Jangan menambah kolom.
8. **Garis dasar tes:** rencana menyebut 1 tes lama gagal di Windows. Ukur ulang sendiri di worktree sebelum mengubah
   apa pun dan catat hasilnya apa adanya.

## S. Style (gaya kerja)

- Ikuti skill `superpowers:executing-plans` atau `superpowers:subagent-driven-development` per Task, TDD: tulis tes
  gagal, lihat gagal, implementasi, lihat lulus.
- Baca `CLAUDE.md` repo lebih dulu, terutama aturan 1 sampai 10 (tanpa data karangan, verifikasi sebelum klaim,
  tanpa dependensi baru, kerjakan tepat yang diminta, aturan worktree).
- Perubahan minimal. Gagasan di luar lingkup ditulis sebagai usulan di laporan, tidak dikerjakan.

## T. Tone (nada)

Laporan lugas dan jujur. Bedakan tegas **"diuji unit"** dan **"dibuktikan langsung"**. Kegagalan dilaporkan sama
jelasnya dengan keberhasilan. Bahasa Indonesia, istilah teknis bahasa Inggris, **tanpa em dash**.

## A. Audience (pembaca)

Bagus (pemilik repo, mahasiswa PA) yang akan meninjau sebelum commit, lalu Claude yang memverifikasi ulang
laporanmu secara mandiri (sha256, diff penuh, menjalankan tes sendiri).

## R. Response (format keluaran)

Tulis laporan ke `D:/wt/auto-publish/LAPORAN-FASE-A.md` (jangan di-commit) dengan bagian:
1. Garis dasar tes sebelum perubahan (perintah dan output mentah ringkas).
2. Per Task: berkas yang diubah, tes yang ditambah, perintah yang dijalankan, hasil.
3. Hasil akhir: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, `npm run build` di `web/`.
4. Pemeriksaan browser Task 5: apa yang dilihat di desktop dan lebar ponsel. Bila tidak bisa membuka browser, tulis
   "TIDAK dibuktikan di browser".
5. Semua penyimpangan dari rencana dan alasannya.
6. Daftar yang **tidak terbukti**.
7. Draf pesan commit per Task (belum dijalankan).

---

## Batas yang tidak boleh dilanggar

- **Jangan commit, jangan push, jangan buka PR, jangan merge.** Bagus yang memerintahkan, terpisah.
- Kerja hanya di worktree baru: `git fetch && git worktree add -b feat/auto-publish D:/wt/auto-publish origin/main`.
  Jangan berpindah cabang atau mengubah berkas di checkout utama `D:/Dev/Projects/eutopos-vps`.
- **Jangan menyentuh PC lab** (ssh, docker, systemd), production, Cloudflare, atau rahasia apa pun.
- Jangan menambah dependensi Python atau npm. Jangan menambah migrasi Alembic.
- Jangan melonggarkan, menghapus, atau melewati (`skip`, `xfail`) tes lama. Bila tes lama harus berubah karena
  perilaku baru yang sah (koreksi 3 dan 4), ubah assert-nya menjadi nilai baru yang tepat dan sebut di laporan.
- Berkas yang boleh diubah hanya yang disebut rencana dan koreksi di atas: `server/gate.py` (baru), `server/db.py`,
  `server/jobs.py`, `server/worker.py`, `server/active_map.py`, `server/app.py`, `tests/test_gate.py` (baru),
  `tests/test_jobs.py`, `tests/test_worker.py`, `tests/test_active_map.py`, `web/components/PipelineStageIndicator.tsx`,
  `web/components/StatusBadge.tsx`, `web/app/maps/page.tsx`, `web/lib/Icon.tsx`, `web/lib/i18n/id.ts`,
  `web/lib/i18n/en.ts`. Perlu berkas lain? Berhenti dan tulis alasannya di laporan.
- Data uji browser dibuat di database SQLite sementara di luar repo, bukan di database production.
- Jangan mengerjakan Fase B, C, atau D.

## Kriteria selesai

- Semua tes di Review Focus rencana ada dan lulus, ditambah tes koreksi 1 dan 5.
- Tanpa `EUTOPOS_AUTO_PUBLISH`, tidak ada versi yang terbit otomatis (dibuktikan tes).
- Seluruh suite hijau kecuali kegagalan garis dasar yang sudah tercatat sebelum perubahan.
- `ruff` bersih, `npm run build` lulus.
- Laporan lengkap sesuai bagian R.
