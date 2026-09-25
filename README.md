# eutopos-vps

**Visual Positioning System lokal untuk navigasi dalam gedung.** Ponsel mengirim satu foto kamera,
server mengembalikan posisi dan orientasi kamera dalam koordinat gedung. Tanpa QR code, tanpa penanda
fisik, dan tanpa layanan cloud pihak ketiga.

*eu* (baik) + *topos* (tempat): tempat yang baik.

Bagian dari Proyek Akhir D3 Teknik Informatika, Politeknik Elektronika Negeri Surabaya: *Platform
Indoor Navigation Terintegrasi AI Avatar Assistant Berbasis Retrieval-Augmented Generation*.

## Status

🔒 **Tahap perencanaan.** Pengembangan dimulai setelah judul Proyek Akhir disetujui.

## Rancangan

- **Pipeline:** [hloc](https://github.com/cvg/Hierarchical-Localization) + ALIKED + [LightGlue](https://github.com/cvg/LightGlue), peta 3D dari [COLMAP](https://colmap.github.io/)
- **Layanan:** FastAPI, berjalan di server instansi tanpa GPU
- **Peran:** koreksi posisi berkala untuk pelacakan ARCore di aplikasi Android

## Dokumentasi

| Berkas | Isi |
|---|---|
| [`docs/pa-context.md`](docs/pa-context.md) | Konteks Proyek Akhir: judul, riwayat, arahan, dan keputusan |
| [`docs/spike-plan.md`](docs/spike-plan.md) | Rencana uji kelayakan satu koridor |
| [`docs/design-notes.md`](docs/design-notes.md) | Penyelarasan koordinat, model data, rute, dan metrik evaluasi |
| [`docs/research-paper.md`](docs/research-paper.md) | Rujukan penelitian, lisensi, dan alasan pemilihan metode |
| [`docs/ci-cd.md`](docs/ci-cd.md) | Pemeriksaan otomatis (CI) dan rencana deployment |

## Lisensi

Copyright (C) 2026 Bagus Insan Pradana

Dilisensikan di bawah **GNU Affero General Public License v3.0**. Lihat [LICENSE](LICENSE).

Siapa pun yang memodifikasi perangkat lunak ini dan menjalankannya sebagai layanan jaringan wajib
menyediakan kode sumber versi modifikasinya kepada penggunanya.
