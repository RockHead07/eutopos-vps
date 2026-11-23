# Brief serah terima: server untuk aplikasi capture (token aplikasi, tanpa terbit otomatis, uji kandidat)

Ditulis 2026-11-23 untuk agen pelaksana. Kerangka CO-STAR. Diperiksa terhadap `origin/main` `0277bd4`. Bila
`origin/main` sudah maju, periksa ulang rujukan baris sebelum mulai dan sebutkan di laporan.

---

## C. Context (konteks)

eutopos-vps adalah VPS lokal untuk navigasi indoor (FastAPI, SQLModel + Alembic, hloc ALIKED + LightGlue, pycolmap,
dashboard Next.js static export di `web/`). Production di PC lab **auto-deploy dari `main`**.

Aplikasi capture Android (repo eutopos-mobile, terpisah) akan merekam foto berpose, mengunggah paket lewat tus, lalu
perekam menguji lokalisasi di lokasi. Server belum siap untuk itu:

1. `server/auth.py` menolak token layanan Cloudflare Access ("service tokens are not allowed"), jadi aplikasi tidak bisa
   membuat pekerjaan. Keputusan Bagus: **token aplikasi yang diperiksa FastAPI sendiri**, tidak bergantung pada
   Cloudflare (server akan pindah ke nginx).
2. Dengan `EUTOPOS_AUTO_PUBLISH` menyala, versi yang lolos gerbang terbit sendiri. Keputusan Bagus: **pekerjaan dari
   aplikasi capture tidak pernah terbit otomatis**; admin menerbitkan manual setelah uji di tempat.
3. `/localize` hanya melayani satu peta (`EUTOPOS_AREA`). Perekam perlu menguji versi kandidat **tanpa mengganti peta
   yang dilayani**.

Dokumen yang mengikat:
- **Rencana (ikuti tugas demi tugas):** `D:/wt/capture-server/docs/plans/2026-11-23-server-aplikasi-capture.md`
- **Spesifikasi (hanya baca):** `D:/wt/capture-design/docs/specs/2026-11-23-aplikasi-capture-matang-design.md`, bagian 4
  dan 6. Rencana menang atas brief ini bila ada beda rincian; spesifikasi menang atas rencana.

## O. Objective (tujuan)

Kerjakan **Tugas 1 sampai 6** di rencana. Tugas 7 (PC lab) **bukan** untukmu.

Hasil akhir:
- Admin membuat, melihat, dan mencabut token aplikasi dari dashboard; token mentah tampil sekali, server hanya menyimpan
  hash SHA-256.
- Token aplikasi (`Authorization: Bearer`) diterima **hanya** di `POST /api/jobs`, `GET /api/jobs/{job_id}` (pekerjaan
  sendiri saja), hook tus pre-create, dan `POST /versions/{version_id}/localize`. Rute lain menolaknya.
- Versi dari pekerjaan beridentitas `app:<nama>` yang lolos gerbang tetap `candidate`.
- `POST /versions/{version_id}/localize` melokalisasi terhadap versi itu dengan model respons `/localize` yang sama,
  paling banyak satu kandidat dimuat, peta yang dilayani tidak berubah, log mencatat `candidate = true`.

## S. Style (gaya kerja)

- TDD: tulis tes di rencana, jalankan dan lihat gagal, baru implementasi. Nama tes dan assert ikuti rencana.
- Baca `CLAUDE.md` repo (aturan 1 sampai 10). Perubahan minimal, ikuti pola modul yang ada.
- Tanpa dependensi baru (Python maupun npm).
- Sebelum mulai, catat garis dasar: `uv run pytest -q` (jumlah lulus, lewati, gagal) dan SHA-256 tiap berkas yang akan
  kamu ubah. Setelah selesai, SHA-256 lagi.

## T. Tone (nada)

Lugas dan jujur. Pisahkan "diuji otomatis" dari "dicoba manual" dari "tidak dibuktikan". Laporan bahasa Indonesia,
istilah teknis bahasa Inggris, tanpa em dash.

## A. Audience (pembaca)

Bagus yang memutuskan commit, lalu Claude yang memverifikasi ulang setiap klaim secara mandiri (menjalankan tes sendiri,
membaca diff, mencoba rute) sebelum PR dan sebelum Tugas 7 di PC lab.

## R. Response (format keluaran)

Tulis `D:/wt/capture-server/LAPORAN-SERVER-CAPTURE.md` (jangan di-commit) berisi:
1. Garis dasar tes dan SHA-256 sebelum.
2. Per tugas: berkas yang diubah, tes yang gagal lalu lulus (keluaran singkat), penyimpangan dari rencana beserta
   alasannya.
3. Hasil akhir `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, dan untuk `web/`:
   `npx tsc --noEmit` dan `npm run build`.
4. Tangkapan layar halaman token (Tugas 6 langkah 3).
5. SHA-256 berkas yang berubah sesudahnya.
6. Draf pesan commit (bahasa Indonesia, gaya `feat(capture): ...`, **tanpa atribusi AI apa pun**).
7. Daftar yang tidak terbukti atau ragu.

## Batas

- **Jangan commit, push, PR, atau merge.** Bekerja di worktree yang sudah ada `D:/wt/capture-server` (cabang
  `plan/capture-server`, dari `origin/main` `0277bd4`). Jangan berpindah cabang, jangan membuat worktree lain, jangan
  mengubah checkout utama `D:/Dev/Projects/eutopos-vps`.
- **Jangan menyentuh PC lab**, production, Cloudflare, `deploy/`, atau rahasia apa pun (termasuk
  `vps-token.local.json`).
- Berkas yang boleh diubah hanya yang tercantum di bagian File Structure rencana, ditambah `tests/conftest.py` bila
  fixture bersama memang perlu. Perlu berkas lain? Berhenti dan tulis alasannya di laporan.
- Jangan mengubah `LocalizeResponse` atau `CONTRACT_VERSION`.
- Jangan melonggarkan, menghapus, atau melewati tes lama. Satu-satunya tes lama yang boleh diubah adalah helper
  `run_gate_job`/`queued` di `tests/test_worker.py` (tambah parameter `created_by` dengan bawaan lama).
- Jangan menghapus `docs/plans/2026-11-23-server-aplikasi-capture.md` atau brief ini.

## Kriteria selesai

- Tugas 1 sampai 6 selesai sesuai rencana; semua tes di Review Focus rencana ada dan lulus.
- `uv run pytest -q` tidak lebih buruk dari garis dasar; ruff bersih; `npm run build` lulus.
- Laporan lengkap sesuai bagian R.
