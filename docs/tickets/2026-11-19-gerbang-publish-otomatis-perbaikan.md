# Brief perbaikan: Fase A gerbang dan publish otomatis (putaran 2)

Ditulis 2026-11-19 setelah verifikasi mandiri atas `LAPORAN-FASE-A.md`. Kerangka CO-STAR. Lanjutan dari
`D:/Dev/Projects/eutopos-vps/docs/tickets/2026-11-19-gerbang-publish-otomatis-handoff.md`; semua batas di brief itu
tetap berlaku.

---

## C. Context (konteks)

Fase A sudah kamu kerjakan di worktree `D:/wt/auto-publish`, cabang `feat/auto-publish`, belum di-commit. Hasil
verifikasi mandiri: berkas yang berubah sesuai izin, `ruff` bersih, `npm run build` lulus, pytest 766 lulus dan
7 dilewati, tes lama tidak dilonggarkan. Dua cacat ditemukan dan harus diperbaiki di putaran ini.

## O. Objective (tujuan)

Perbaiki tepat dua hal berikut, masing-masing dengan TDD (tes gagal dulu, lalu lulus).

### Perbaikan 1: ikon versi yang ditolak (regresi)

`web/lib/Icon.tsx` mengubah `rejected` dari `"error-map"` menjadi `"inactive-map"`. Ikon `web/public/icons/error-map.svg`
ada dan dipakai di tempat lain, jadi perubahan itu membuat versi yang ditolak tampil sama dengan kandidat.

- Kembalikan `rejected: "error-map"`. `ready: "inactive-map"` tetap.
- Tidak perlu tes otomatis untuk satu baris ini, tetapi periksa di browser bahwa versi `rejected` menampilkan ikon
  `error-map` (lihat bagian R).

### Perbaikan 2: publish otomatis tidak boleh menerbitkan peta tanpa alignment di area yang dilayani

Masalah: `publish_ready` di `server/active_map.py` menerbitkan versi `ready` terbaru di area yang dilayani
(`serving_area()`) lewat `reload_in_background`. Gerbang hanya menilai foto uji. Versi baru belum punya alignment,
jadi bila `EUTOPOS_AUTO_PUBLISH` dinyalakan, peta yang dilayani production berganti ke peta tanpa koordinat meter dan
navigasi rusak.

Perilaku yang diminta:
- Untuk **area yang dilayani**: versi `ready` terbaru hanya diterbitkan otomatis bila alignment-nya ada. Bila belum
  ada, **lewati** (versi tetap `ready`, tidak diubah statusnya, tidak ditolak), supaya terbit sendiri pada putaran
  berikutnya setelah alignment dipasang. Versi `ready` lama di area itu tetap ditandai `retired` seperti sekarang.
- Untuk **area lain**: perilaku tidak berubah (terbit langsung), karena tidak mengganti peta yang dilayani.
- Graf rute tidak disyaratkan di sini (graf milik area, bukan versi, dan sudah ada untuk area yang dilayani).

Cara (wajib satu pemilik logika, jangan menyalin):
- Logika alignment sekarang ada di `_align(s, v)` di `server/maps_api.py`. Pindahkan menjadi fungsi publik
  `version_alignment(session, version: MapVersion, maps_root: Path) -> dict | None` di `server/alignment.py`, dengan
  perilaku persis sama (DB lebih dulu, lalu `run_dir(Path(v.path)) / "align.json"` yang harus berada di dalam
  `maps_root`). Akar peta dijadikan **parameter**, bukan diimpor, karena repo punya dua sumber akar peta:
  `maps_api.MAPS_ROOT` (konstanta, di-monkeypatch oleh `tests/test_maps_api.py` baris 35) dan
  `navgraph.maps_root()` (membaca `EUTOPOS_MAPS_ROOT`). Penyatuan keduanya di luar lingkup; catat sebagai usulan.
- `maps_api._align(s, v)` diganti menjadi pemanggilan `alignment.version_alignment(s, v, MAPS_ROOT)` (boleh tetap
  sebagai pembungkus satu baris supaya pemanggil lain tidak berubah).
- `active_map.publish_ready` memanggil `alignment.version_alignment(session, version, navgraph.maps_root())`. Jangan
  mengimpor `maps_api` dari `active_map` (rawan impor melingkar). `run_dir` diimpor dari `server.pipeline`.
- Periksa tidak ada impor melingkar dengan `uv run python -c "import server.app"`.

Tes wajib di `tests/test_active_map.py`:
- `test_publish_ready_skips_serving_area_without_alignment`: versi `ready` di area yang dilayani tanpa alignment
  -> tidak ada thread, versi tetap `ready`, peta yang dilayani tidak berubah.
- `test_publish_ready_publishes_serving_area_once_aligned`: versi yang sama setelah alignment ditambahkan (lewat tabel
  DB alignment atau berkas `align.json` di `run_dir`, ikuti pola tes yang sudah ada di repo) -> terbit oleh `"system"`.
- `test_publish_ready_other_area_does_not_need_alignment`: versi `ready` di area lain tanpa alignment -> tetap terbit
  langsung.
- Tes lama `test_publish_ready_swaps_serving_area` dan tes lain yang menerbitkan area yang dilayani kini harus memberi
  alignment pada versinya. Ubah persiapan tesnya (tambah alignment), **jangan** melonggarkan assert-nya.

Semua tes `maps_api` yang sudah ada (termasuk `navigation_ready` dan `splat_placement`) harus tetap lulus tanpa diubah;
itu bukti pemindahan `_align` tidak mengubah perilaku.

## S. Style (gaya kerja)

TDD per perbaikan. Perubahan minimal. Baca `CLAUDE.md` repo (aturan 1 sampai 10). Gagasan lain ditulis sebagai usulan
di laporan, tidak dikerjakan. Khusus: **jangan** mengubah aturan potongan peta di `server/gate.py` (ditunda sampai ada
data lapangan).

## T. Tone (nada)

Lugas dan jujur. Pisahkan "diuji unit" dan "dibuktikan langsung". Bahasa Indonesia, istilah teknis bahasa Inggris,
tanpa em dash.

## A. Audience (pembaca)

Bagus (pemilik repo) yang memutuskan commit, lalu Claude yang memverifikasi ulang secara mandiri.

## R. Response (format keluaran)

Tambahkan bagian baru **"Putaran 2"** di akhir `D:/wt/auto-publish/LAPORAN-FASE-A.md` (jangan hapus isi lama):
1. Per perbaikan: berkas yang diubah, tes yang ditambah atau persiapannya diubah, output tes sebelum (gagal) dan
   sesudah (lulus).
2. Hasil akhir: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q` (dengan `PYTHONPATH` yang
   sama seperti putaran 1, sebutkan nilainya), `npm run build` di `web/`.
3. Browser: halaman `/maps/` dengan satu versi `rejected` menampilkan ikon `error-map`. Bila tidak bisa dibuka, tulis
   "TIDAK dibuktikan di browser". Bersihkan database uji dan tutup semua koneksi sesudahnya.
4. SHA-256 terbaru semua berkas yang berubah.
5. Draf pesan commit yang diperbarui (belum dijalankan).
6. Daftar yang tidak terbukti.

## Batas

- Tetap: jangan commit, push, PR, atau merge; hanya di `D:/wt/auto-publish`; jangan sentuh PC lab, production,
  Cloudflare, atau rahasia; tanpa dependensi atau migrasi baru; jangan melonggarkan atau melewati tes.
- Berkas tambahan yang boleh diubah di putaran ini: `server/alignment.py` dan `server/maps_api.py` (hanya untuk
  pemindahan `_align`), serta `tests/test_alignment.py` atau `tests/test_maps_api.py` bila perlu menambah tes untuk
  `version_alignment`. Berkas lain di luar daftar putaran 1 dan ini: berhenti dan tulis alasannya.

## Kriteria selesai

- `rejected` memakai `error-map` lagi.
- Tiga tes baru ada dan lulus; tes lama tetap lulus tanpa assert yang dilonggarkan.
- Hanya satu implementasi logika alignment di repo.
- Suite, `ruff`, dan `npm run build` hijau.
