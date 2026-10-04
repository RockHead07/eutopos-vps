# Desain Pengelolaan Rujukan dan Teks Paper untuk AI (Zotero + MarkItDown)

**Tanggal:** 2026-10-04
**Status:** Revisi disetujui pemilik 2026-10-04, menggantikan draf awal di hari yang sama (draf awal membuat
pengambil metadata dan penulis BibTeX sendiri, dan menaruh proposal LaTeX di repo ini). Belum
diimplementasikan.

## 1. Masalah

1. **Sitasi proposal harus presisi.** Rujukan IEEE butuh metadata versi terbit (jurnal atau konferensi,
   volume, halaman, DOI), bukan versi pracetak. Empat belas rujukan Bab 1 sudah diverifikasi manual ke
   Crossref (`docs/research-paper.md` bagian 10); cara manual itu tidak bertahan untuk puluhan rujukan.
2. **Asisten AI (Claude Code, Antigravity) membaca paper lebih baik dari teks.** PDF dua kolom boros
   token dan urutan teksnya bisa kacau; teks Markdown bisa dicari dengan grep di seluruh koleksi.
3. **Repo ini publik (AGPL-3.0).** PDF paper sudah di-gitignore karena hak ciptanya beragam
   (`.gitignore`). Teks lengkap hasil konversi adalah salinan paper yang sama, jadi berlaku aturan yang sama.

## 2. Keputusan

| Keputusan | Alasan | Alternatif yang ditolak |
|---|---|---|
| **Zotero + Better BibTeX adalah satu-satunya pemilik metadata rujukan** | Standar akademik: metadata versi terbit dari DOI atau URL arXiv, PDF tersimpan, citekey stabil, ekspor `.bib` otomatis, gaya IEEE, plugin Word dan LaTeX. Satu pemilik, sisanya diturunkan (`CLAUDE.md`, larangan duplikasi data manual) | Skrip sendiri yang memanggil API arXiv lalu menulis BibTeX (draf awal): mengulang fungsi Zotero, dan API arXiv hanya memberi versi pracetak |
| **Teks paper untuk AI disimpan lokal saja** | Teks lengkap paper tidak boleh disebarkan ulang lewat repo publik. Fungsi untuk AI tetap sama karena dibaca dari disk | Meng-commit `docs/references/*.md` |
| **MarkItDown sebagai pengubah PDF ke Markdown** | Ringan dan sudah dipilih pemilik. Diganti hanya kalau hasilnya terbukti buruk (bagian 5) | Docling atau Marker sejak awal: lebih paham tata letak paper, tapi berat (model PDF) dan belum terbukti dibutuhkan |
| **Proposal tidak berada di repo ini** | Proposal memuat nama dan NRP, sedangkan repo ini publik. Formatnya mengikuti template resmi jurusan (`.docx`) kecuali LaTeX diizinkan pembimbing atau jurusan. Zotero mendukung keduanya | Folder `proposal/` LaTeX di repo ini (draf awal) |
| **Korpus paper bukan korpus RAG avatar** | RAG avatar menjawab pertanyaan tentang kampus dan POI. Paper riset bukan bahan jawabannya | Menyebut paper sebagai basis pengetahuan RAG (draf awal) |

## 3. Alur dan berkas

```text
Zotero (pustaka lokal pemilik, PDF di penyimpanan Zotero)
  └─ Better BibTeX: ekspor otomatis, "Export files" aktif
       └─► docs/references/library.bib        (lokal, di-gitignore: berisi jalur berkas lokal)
             └─ python -m tools.ref2md
                  └─► docs/references/<citekey>.md   (lokal, di-gitignore: teks lengkap paper)
```

| Berkas | Di repo publik? | Isi |
|---|---|---|
| `tools/ref2md.py` | ya | Pengubah, bagian 4 |
| `.gitignore` | ya | Tambah `docs/references/` |
| `docs/research-paper.md` | ya | Sintesis dan keputusan kita sendiri, bukan teks paper. Tetap jadi tempat rujukan dibahas |
| `docs/references/library.bib`, `docs/references/*.md` | **tidak** | Diturunkan dari Zotero, bisa dibuat ulang kapan saja |
| `docs/papers/` | tidak | Tetap di-gitignore. Tidak dipakai lagi: PDF tinggal di Zotero |
| Proposal | tidak | Repo atau folder privat. Kalau LaTeX, `library.bib` dirujuk atau disalin dari Zotero |

**Citekey** memakai formula Better BibTeX `auth.lower + year + shorttitle(1,0).lower`, misalnya
`zhao2023aliked`. Citekey yang sudah dipakai di dokumen tidak diubah (Better BibTeX bisa menyematkannya).

## 4. `tools/ref2md.py`

```bash
uv run --group refs python -m tools.ref2md                          # entri ber-PDF yang belum dikonversi
uv run --group refs python -m tools.ref2md zhao2023aliked --force   # satu entri, timpa
```

- Membaca `docs/references/library.bib` (jalur bisa diganti dengan `--bib`).
- Untuk setiap entri yang punya lampiran PDF: kalau `docs/references/<citekey>.md` belum ada (atau
  `--force`), ubah PDF dengan MarkItDown, lalu tulis berkas dengan frontmatter YAML yang **seluruhnya
  diambil dari entri BibTeX**, tidak pernah ditulis tangan:

  ```markdown
  ---
  citekey: <citekey>
  title: "<judul>"
  authors: [<penulis 1>, <penulis 2>, ...]
  year: <tahun>
  venue: "<jurnal atau konferensi>"
  doi: "<DOI, kalau ada>"
  url: "<URL, kalau ada>"
  converted_with: "markitdown <versi>"
  converted_at: "<tanggal>"
  ---
  ```
- Entri tanpa PDF dilewati dengan pesan; entri yang sudah dikonversi dilewati tanpa pesan.
- Ringkasan di akhir: berapa dikonversi, dilewati, gagal.
- Dependensi di grup uv terpisah `refs` (`markitdown[pdf]`, `bibtexparser`), sehingga tidak ikut ke
  image layanan, ke tahap test Docker, atau ke `uv sync` biasa.

## 5. Kapan MarkItDown diganti

Uji pada satu paper dua kolom dengan tabel dan rumus (ALIKED): kalau urutan teks antar-kolom tertukar
sehingga paragraf tidak bisa dibaca, atau tabel hasil tidak terbaca, coba Docling pada paper yang sama dan
pakai yang lebih rapi. Keputusan dan contohnya dicatat di sini.

## 6. Aturan untuk asisten AI

Ditambahkan ke `CLAUDE.md` saat implementasi:

- Saat butuh isi paper, baca `docs/references/<citekey>.md` kalau ada; jangan membaca PDF mentah.
- Berkas itu bisa tidak ada (lokal, di-gitignore). Kalau tidak ada, katakan, dan minta pemilik menambahkan
  paper ke Zotero lalu menjalankan `tools.ref2md`. Jangan mengarang isi paper.
- Sitasi memakai citekey dari frontmatter. Metadata tidak pernah ditulis tangan di luar Zotero.

## 7. Pengujian

1. **Unit test** untuk bagian yang bukan pustaka pihak ketiga: membangun frontmatter dari satu entri BibTeX
   contoh (termasuk penulis dengan nama majemuk dan judul berkurung kurawal), dan melewati entri tanpa PDF.
   Dilewati otomatis kalau grup `refs` tidak terpasang (`pytest.importorskip`).
2. **Uji manual:** satu paper dari Zotero (ALIKED) menjadi `.md` dengan frontmatter benar; dijalankan kedua
   kali, tidak ada yang ditimpa.
3. `git status` setelah konversi: tidak ada berkas di `docs/references/` yang muncul sebagai berkas baru.

## 8. Langkah pemilik (sekali)

1. Pasang Zotero dan plugin Better BibTeX; atur formula citekey (bagian 3).
2. Tambahkan rujukan lewat DOI. Empat belas rujukan Bab 1 dan DOI-nya ada di `docs/research-paper.md`
   bagian 10.
3. Ekspor koleksi dengan Better BibTeX (format Better BibTeX, "Keep updated" dan "Export files" aktif) ke
   `docs/references/library.bib`.
