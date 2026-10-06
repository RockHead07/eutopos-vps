# Waktu rekam dan pratinjau job

Status: diimplementasikan 2026-10-06 (cabang `feat/recorded-date-preview`). Menjadi kontrak untuk UI
dashboard (kolom Recorded, foto pratinjau di halaman job).

## 1. Masalah

Dashboard hanya tahu kapan sebuah job dibuat (`created_at`, saat unggahan dimulai). Itu bukan kapan lokasinya
direkam: video bisa direkam hari ini dan diunggah minggu depan. Untuk mengetahui apakah sebuah peta masih
mewakili kondisi ruangan, perlu tanggal rekam, dan foto kecil dari rekaman itu supaya peta mudah dikenali.

## 2. Keputusan

- **Waktu rekam dibaca dari dalam video** (kotak `mvhd`, `creation_time`), bukan dari tanggal berkas. Di data
  kita, salinan sebuah video bergeser lebih dari satu jam pada tanggal berkas, sedangkan isi videonya tetap
  benar (04:15:49 UTC, cocok dengan nama berkas ponsel `VID_20261001_111550`).
- **Dibaca oleh pekerja sebelum video dihapus** (`worker.stamp_recorded`), karena video unggahan memang dibuang
  setelah frame diekstrak (privasi). Disimpan per video di kolom JSON `map_job.videos[].recorded_at`, jadi
  tanpa migrasi.
- **Tidak ada tebakan.** Folder frame, video tanpa metadata, tahun sebelum 2000, dan waktu di masa depan
  (jam perangkat belum diatur) menjadi `null`. UI menampilkannya sebagai "-".
- **Pratinjau = frame pertama video peta pertama**, diperkecil ke lebar 640 px, JPEG kualitas 80 (sekitar 20 KB),
  ditulis pekerja ke `maps/<area>/job-<id>/preview.jpg`. Folder itu dipilih karena container `api` hanya bisa
  membaca `/maps` (tidak `/data/jobs`), dan penghapusan job membuangnya sekaligus. Berkas ditulis ke nama
  sementara lalu diganti, jadi api tidak pernah menyajikan berkas setengah jadi.
- **Pratinjau opsional.** Kegagalan membuatnya (frame rusak, tidak ada frame) tidak menggagalkan job.
- **Job lama:** waktu rekam tidak bisa diisi ulang (videonya sudah terhapus). Pratinjau bisa, dari frame yang
  masih tersimpan: `python -m server.manage previews` (di container pekerja). Aman diulang, tidak menimpa,
  dan tidak membuat ulang folder peta yang sudah dihapus.

## 3. Kontrak API

| Rute | Perubahan |
|---|---|
| `GET /api/jobs`, `GET /api/jobs/{id}` | tiap `videos[]` memuat `recorded_at` (ISO 8601 dengan zona, atau `null`); job memuat `has_preview` (bool) |
| `GET /api/jobs/{id}/preview` | `200 image/jpeg` dengan `Cache-Control: private, max-age=3600`; `404` bila job tidak ada atau belum punya pratinjau |

`GET /api/jobs/{id}/preview` hanya menyajikan berkas yang tepat berada di bawah `/maps`: `area_id` dari baris yang
rusak tidak bisa menyeret berkas lain (ada tesnya).

## 4. Deploy

Tanpa perubahan `compose.yaml` atau `.env`. Setelah autodeploy membangun ulang image, buat pratinjau job lama:

    docker compose exec worker python -m server.manage previews

## 5. Di luar cakupan

Waktu rekam untuk job lama, pratinjau foto uji, mengganti pratinjau dengan frame lain, dan menyamarkan wajah.
Frame yang tampil sudah tersimpan di `data/jobs/<id>/` sejak sebelum fitur ini; yang baru adalah dapat dilihat
dari dashboard oleh semua pengguna yang lolos Cloudflare Access.
