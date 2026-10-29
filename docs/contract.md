# Kontrak server dan aplikasi: /localize dan /navgraph

Dua jawaban ini dibaca aplikasi eutopos-mobile. Bentuknya dijaga supaya aplikasi lama tetap jalan
saat server berubah (prinsip 4 di `docs/plans/2026-10-24-roadmap-multifloor-tasking.md`).

## Versi

Setiap jawaban membawa `contract_version` (bilangan bulat, sekarang `1`), didefinisikan di
`server/contract.py`. Jawaban dari server yang lebih lama tidak memuat bidang ini, dan klien
memperlakukannya sebagai versi 0.

| Perubahan | Versi |
|---|---|
| Menambah bidang baru | tetap. Klien lama mengabaikan bidang yang tidak dikenal. |
| Mengubah arti, tipe, atau satuan bidang yang ada | naik |
| Menghapus bidang | naik |

Saat versi naik, endpoint lama tetap dilayani sampai klien lama tidak dipakai lagi.

## Berkas contoh bersama

Tiga berkas di `tests/fixtures/` ditulis dari jawaban server sungguhan, bukan JSON buatan tangan.
`tests/test_contract.py` menjalankan server dan membandingkan jawabannya dengan berkas itu, jadi
mengubah bentuk jawaban tanpa mengubah berkas membuat tes gagal.

| Berkas | Jawaban |
|---|---|
| `localize_ok.json` | `POST /localize` berhasil, dengan `pose_model` dan `pose_building` |
| `localize_failed.json` | `POST /localize` gagal (inlier kurang), kedua pose `null` |
| `navgraph_response.json` | `GET /navgraph` dengan graf terbit, `walkable`, dan `revision` |

`walkable_payload.json` (sudah ada) adalah bagian `walkable` dari `navgraph_response.json`.

**eutopos-mobile menyalin berkas-berkas ini byte demi byte** ke
`Assets/Eutopos/Tests/EditMode/` dan mem-parse-nya di tes EditMode. Mengubah satu berkas berarti
menyalin ulang ke repo aplikasi dan menjalankan tesnya di sana.

Catatan: `revision` selalu berformat ISO 8601 dengan zona (`+00:00`). Klien harus memperlakukannya
sebagai string buram untuk dibandingkan, bukan menguraikannya sebagai tanggal.
