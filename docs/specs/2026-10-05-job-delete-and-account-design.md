# Hapus job, tanggal, dan identitas pengguna di API

Status: diimplementasikan 2026-10-05 (cabang `feat/api-me-delete`). Menjadi kontrak untuk UI dashboard
(kolom tanggal, aksi Delete, Properties, menu akun).

## 1. Masalah

Tabel dashboard belum punya tanggal, belum bisa menghapus job, dan tidak ada identitas pengguna yang bisa
ditampilkan. Datanya sebagian sudah ada di database (`created_at`, `started_at`, `finished_at`), tapi
`JobOut` tidak mengirimnya. Endpoint hapus dan endpoint identitas belum ada.

## 2. Keputusan

- **Penghapusan dikerjakan pekerja, bukan api.** Container `api` memasang `/maps` hanya-baca (hak akses
  minimum untuk layanan yang menghadap internet). `DELETE /api/jobs/{id}` hanya memeriksa aturan lalu
  menandai status `deleting`. Pekerja, yang punya akses tulis, menghapus folder peta dan baris database.
- **Yang dihapus:** `maps/<area>/job-<id>/`, baris `map_job`, dan baris `map_version` miliknya.
- **Yang dibiarkan:** `data/jobs/<id>/` (frame hasil ekstraksi dan log). Itu masukan yang bisa membangun
  ulang peta. Video unggahan memang sudah dibuang pekerja setelah ekstraksi (alasan privasi), jadi tidak
  ada video mentah yang tersisa untuk dipertahankan.
- **Hanya admin.** Admin = email di `EUTOPOS_ADMINS` (dipisah koma, tanpa peka huruf). Kosong berarti tidak
  ada yang boleh (gagal tertutup). Di mode uji lokal (`EUTOPOS_DEV_NO_AUTH=1`), `dev@local` admin.
- **Pengaman:** hanya job `done` atau `failed`; versi peta yang sedang `published` tidak boleh dihapus;
  terbitkan ditolak selama job-nya `deleting`; pekerja hanya menghapus tepat `<maps>/<area>/job-<id>` dan
  menandai job `failed` kalau jalurnya di luar folder peta.

## 3. Kontrak API

| Rute | Hasil |
|---|---|
| `GET /api/me` | `{"email": str, "is_admin": bool}` |
| `GET /api/jobs`, `GET /api/jobs/{id}` | sekarang memuat `created_at`, `started_at` (null bila tidak lewat pekerja), `finished_at` (ISO 8601, UTC) |
| `DELETE /api/jobs/{id}` | `202 {"status": "deleting"}`; `403` bukan admin; `404`; `409` dengan alasan (belum selesai, atau versi sedang terbit). Diulang aman. |
| `POST /api/versions/{id}/publish` | `409 "its job is being deleted"` selama job-nya `deleting` |

Status baru `deleting` muncul di `status` job sampai pekerja selesai (baris hilang dari daftar). Kalau
penghapusan gagal, job menjadi `failed` dengan `error` yang menjelaskan, dan bisa dihapus lagi.

Keluar (sign out) bukan bagian API ini: Cloudflare Access menyediakan `<domain>/cdn-cgi/access/logout`.

## 4. Deploy

Isi `EUTOPOS_ADMINS=email-kamu@contoh.com` di `deploy/.env` di PC lab, lalu `docker compose up -d`.
Tanpa itu, tombol Delete tidak muncul dan server menjawab 403.

## 5. Di luar cakupan

Menghapus versi peta tanpa job (dibuat lewat CLI), pemulihan setelah hapus, peran selain admin, dan
halaman profil. Belum ada kebutuhannya.
