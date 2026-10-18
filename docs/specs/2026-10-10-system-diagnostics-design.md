# Popover Diagnostik Sistem (System Diagnostics Popover)

Status: diimplementasikan 2026-10-10 (PR #64, commit `6236c5c`). Menjadi kontrak untuk UI header chip dan endpoint telemetri sistem di dashboard eutopos.

---

## 1. Masalah dan Kebutuhan

Saat server eutopos berjalan di PC lab (sebagai VPS lokal), operator perlu memantau kesehatan dasar server:
1. **Kapasitas disk**: unggahan video rekaman berukuran ratusan MB sampai beberapa GB. Jika partisi `/data` (tempat video diunggah) atau `/maps` (tempat model point cloud disimpan) penuh, proses bangun peta atau unggahan tusd akan gagal tiba-tiba.
2. **Kondisi hardware dan GPU**: proses bangun peta (COLMAP + LightGlue/ALIKED) membebani GPU dan VRAM. Operator perlu mengetahui apakah GPU terdeteksi, suhu hardware dalam batas wajar, dan berapa sisa memory VRAM yang tersedia.
3. **Kerapian antarmuka**: informasi hardware ini tidak boleh mengotori halaman utama (Overview) dengan kartu raksasa permanen yang jarang dilihat setiap saat.

---

## 2. Keputusan Desain

- **Popover on-demand**: diletakkan di balik chip status header `VPS online` yang sudah ada (`web/lib/PageHead.tsx`). Pengguna mengeklik chip untuk melihat diagnostik, dan menutupnya dengan klik di luar atau tombol Escape.
- **Polling hanya saat popover terbuka**: request polling berjalan tiap 10 detik saat popover aktif (`isOpen === true`). Saat ditutup atau unmount, timer langsung dihentikan (`clearInterval`), sehingga tidak membebani jaringan atau proses server saat operator bekerja di halaman lain.
- **Data nyata tanpa angka karangan (aturan zero mock data)**:
  - Kapasitas disk dibaca langsung lewat `shutil.disk_usage()` pada path `/maps` dan `/data`.
  - Telemetri GPU dibaca via subprocess `nvidia-smi` (CLI resmi NVIDIA), dengan fallback ke `torch.cuda` jika tanpa CLI. Jika server berjalan di CPU mode, status jujur `GPU telemetry unavailable (CPU Mode)` ditampilkan tanpa membuat nilai palsu.
  - Jika suhu GPU tidak didukung hardware (seperti kartu komputasi tertentu), nilai suhu ditampilkan `N/A`, sementara sisa metrik VRAM tetap ditampilkan.
  - Sisa data sebelumnya tetap dipertahankan jika terjadi gangguan koneksi sementara saat refresh, disertai banner peringatan halus (`Refresh failed: showing last known metrics`).
- **Prinsip Ponytail**: memanfaatkan komponen Radix Popover resmi shadcn yang sudah terpasang, tanpa menambah pustaka charting baru atau dependensi npm/pip tambahan.

---

## 3. Kontrak API

### Endpoint: `GET /api/system`
- Autentikasi: Terautentikasi (`uploads.User` via Cloudflare Access atau dev mode).
- Response Model: `server.system.SystemDiagnostics`

```json
{
  "storage": {
    "maps": {
      "total_bytes": 270014763008,
      "used_bytes": 233282240512,
      "free_bytes": 36732522496,
      "total_gb": 251.5,
      "used_gb": 217.3,
      "free_gb": 34.2,
      "percent": 86.4
    },
    "data": {
      "total_bytes": 270014763008,
      "used_bytes": 233282240512,
      "free_bytes": 36732522496,
      "total_gb": 251.5,
      "used_gb": 217.3,
      "free_gb": 34.2,
      "percent": 86.4
    }
  },
  "gpu": {
    "name": "NVIDIA GeForce RTX 4090",
    "temperature_c": 52,
    "vram_used_mb": 2400,
    "vram_total_mb": 24576
  },
  "device": "cuda",
  "uptime_s": 1420.5,
  "area_id": "floor10",
  "map_version": 3,
  "reloading": false,
  "reload_error": null
}
```

Jika salah satu path tidak terpasang atau GPU tidak tersedia, field terkait bernilai `null`.

---

## 4. Kerangka Analisis & Evaluasi Relevansi ke Depan

Dokumen ini mencatat parameter untuk menganalisis apakah fitur ini perlu dipertahankan, disederhanakan, atau dimodifikasi di kemudian hari:

### A. Kapan Fitur Ini Terbukti Relevan (Kriteria Manfaat)
1. **Pencegahan Kegagalan Unggahan**: operator dapat langsung mengetahui bahwa disk `/data` hampir penuh (>85%) sebelum memulai unggahan video berukuran 2 GB.
2. **Diagnostik Masalah Rekonstruksi**: jika pekerja pembuat peta tiba-tiba mati karena Out-Of-Memory (OOM) GPU, operator dapat membuka popover untuk memeriksa apakah memory VRAM habis atau GPU throttling karena suhu tinggi.
3. **Verifikasi Mode Komputasi PC Lab**: operator dapat memverifikasi dalam sekali klik apakah kontainer Docker mendeteksi GPU NVIDIA (`CUDA Mode`) atau secara tidak sengaja jatuh ke `CPU Mode`.

### B. Indikator Jika Fitur Ini Kurang Relevan / Perlu Dipangkas
1. **Operator Tidak Pernah Mengeklik Chip**: jika dalam uji coba rutin operator hanya melihat daftar job dan tidak memerlukan inspeksi popover, fitur popover interaktif ini berpotensi berlebih (over-engineering).
2. **Kebutuhan Sebenarnya adalah Peringatan Proaktif (Alert), Bukan Menu Introspeksi**: jika disk penuh tetapi operator tidak sadar karena tidak membuka popover, maka UI popover pasif kurang efektif dibanding banner peringatan otomatis saat disk tersisa < 10%.
3. **Penyatuan Partisi Disk**: jika di server produksi `/maps` dan `/data` selalu berada di partisi volume yang sama, menampilkan dua bar penyimpanan identik bisa membingungkan operator dan cukup diringkas menjadi satu ringkasan penyimpanan server.

### C. Rencana Tindak Lanjut Evaluasi
- Amati penggunaan selama pengujian lapangan berikutnya (rekaman rute koridor baru).
- Tinjau apakah informasi suhu (°C) memberikan wawasan operasional yang nyata atau sekadar pemanis visual.
- Jika dirasa berlebih, bagian GPU dapat disederhanakan hanya menjadi indikator mode perangkat (`CUDA` / `CPU`), atau diringkas sesuai prinsip Ponytail.

---

## 5. Batasan Teknis Saat Ini

- **Uptime**: mengukur umur hidup proses kontainer FastAPI sejak start (`time.time() - _START_TIME`), bukan uptime OS host WSL2/Ubuntu.
- **Suhu GPU di Lingkungan Virtual**: pada beberapa konfigurasi container tanpa hak akses manajemen hardware penuh, sensor suhu mungkin mengembalikan `null` / `N/A`.
