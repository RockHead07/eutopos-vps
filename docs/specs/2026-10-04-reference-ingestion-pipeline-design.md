# Desain Pipeline Ingestion Referensi Riset (MarkItDown + BibTeX)

**Tanggal:** 2026-10-04  
**Status:** Disetujui (Draft Spec)  
**Tujuan:** Mengotomatiskan konversi sumber literatur (PDF paper, arXiv, dan artikel web) menjadi format Markdown terstruktur untuk konsumsi AI (Claude Code & Antigravity), basis pengetahuan RAG, catatan riset, dan sinkronisasi sitasi BibTeX untuk proposal Sempro di LaTeX.

---

## 1. Konteks & Latar Belakang

Pada proyek Proyek Akhir *Platform Indoor Navigation Terintegrasi AI Avatar Assistant Berbasis Retrieval-Augmented Generation* (`eutopos-vps`), terdapat kebutuhan untuk:
1. **Penyusunan Proposal Sempro (LaTeX):** Membutuhkan manajemen sitasi yang presisi (`references.bib`) dan pemahaman mendalam atas literatur (hloc, LightGlue, ALIKED, MegaLoc, VIO-APR, MobileARLoc, dll.) untuk Bab 1 dan Bab 2.
2. **Keterbacaan oleh AI Coding Assistant (Claude Code & Antigravity):** Membaca PDF 2-kolom secara langsung sering kali menghasilkan teks berantakan dan boros token. Format Markdown (`.md`) yang bersih memungkinkan asisten AI membaca, memahami, dan mensintesis teori secara optimal.
3. **Knowledge Base untuk RAG:** Menjadi fondasi korpus pengetahuan lokal yang siap di-*chunk* untuk fitur asisten avatar di masa mendatang.
4. **Pemberitahuan ke Claude Code:** Memastikan Claude Code mengetahui keberadaan direktori referensi ini melalui pembaruan di `CLAUDE.md`.

---

## 2. Struktur Berkas & Direktori

```text
eutopos-vps/
├── docs/
│   ├── papers/             # Berkas PDF asli (lokal saja, di-gitignore)
│   └── references/         # Berkas Markdown hasil konversi (ramah AI & RAG)
│       ├── sarlin2019coarse.md
│       ├── zhao2023aliked.md
│       └── ...
├── proposal/               # Proyek LaTeX Proposal Sempro
│   ├── main.tex
│   ├── references.bib      # Berkas BibTeX tersinkronisasi otomatis
│   └── chapters/
│       ├── 01-pendahuluan.tex
│       ├── 02-kajian-pustaka.tex
│       └── 03-metodologi.tex
├── tools/
│   └── ingest_ref.py       # Skrip CLI ingestion (MarkItDown + Metadata Fetcher)
└── CLAUDE.md               # Diperbarui agar Claude Code otomatis membaca docs/references/
```

---

## 3. Spesifikasi Fungsional

### 3.1 Masukan (Input Modes)
Skrip `tools/ingest_ref.py` mendukung 3 moda masukan:

1. **URL arXiv (`--arxiv` atau deteksi otomatis URL):**
   - Contoh: `python -m tools.ingest_ref https://arxiv.org/abs/2304.03608`
   - Skrip memanggil arXiv API (`http://export.arxiv.org/api/query?id_list=...`) untuk mengambil metadata lengkap: judul, daftar penulis, tahun, abstrak, dan link PDF.
   - Skrip otomatis mengunduh PDF ke `docs/papers/` (jika belum ada) dan mengonversi isi dokumen.
   - Menghasilkan `citekey` standar: `[author_last_name][year][first_title_word]` (misal: `zhao2023aliked`).

2. **Berkas PDF Lokal:**
   - Contoh: `python -m tools.ingest_ref docs/papers/LightGlue.pdf --citekey lindenberger2023lightglue --title "..." --year 2023 --authors "..."`
   - Mengonversi isi PDF ke Markdown menggunakan Microsoft `markitdown`.

3. **URL Web / Dokumentasi:**
   - Contoh: `python -m tools.ingest_ref https://colmap.github.io/tutorial.html --citekey colmap_tutorial`
   - Mengunduh HTML dan mengonversinya ke Markdown bersih tanpa elemen navigasi website yang tidak perlu.

### 3.2 Format Berkas Markdown (`docs/references/<citekey>.md`)
Setiap berkas Markdown memiliki YAML Frontmatter di bagian awal untuk menyediakan identitas sitasi:

```markdown
---
citekey: zhao2023aliked
title: "ALIKED: A Lighter Keypoint and Descriptor Extraction Network via Deformable Transformation"
authors:
  - Xiaoming Zhao
  - Xingming Wu
  - Jiahuan Yu
  - Weihai Chen
year: 2023
venue: "IEEE Transactions on Instrumentation and Measurement"
url: "https://arxiv.org/abs/2304.03608"
source_type: "paper"
ingested_at: "2026-10-04"
---

# ALIKED: A Lighter Keypoint and Descriptor Extraction Network via Deformable Transformation

## Abstract
...

## 1. Introduction
...
```

### 3.3 Sinkronisasi BibTeX (`proposal/references.bib`)
- Skrip memeriksa apakah `citekey` sudah ada di dalam `proposal/references.bib`.
- Jika belum ada, otomatis menambahkan blok entri BibTeX standar:
  ```bibtex
  @article{zhao2023aliked,
    title = {ALIKED: A Lighter Keypoint and Descriptor Extraction Network via Deformable Transformation},
    author = {Zhao, Xiaoming and Wu, Xingming and Yu, Jiahuan and Chen, Weihai},
    year = {2023},
    journal = {IEEE Transactions on Instrumentation and Measurement},
    url = {https://arxiv.org/abs/2304.03608}
  }
  ```
- Jika sudah ada, skrip melewatkan penulisan BibTeX untuk mencegah duplikasi entri yang merusak kompilasi LaTeX.

---

## 4. Integrasi dengan Claude Code & Antigravity

Setelah skrip dan direktori terpasang:
1. `CLAUDE.md` diperbarui pada bagian panduan riset:
   > **Referensi Paper:** Berkas literatur dalam bentuk teks Markdown tersedia di `docs/references/`. Saat membutuhkan rujukan paper untuk penulisan proposal, teori, atau perancangan arsitektur, baca berkas `.md` di direktori tersebut alih-alih mencoba membaca PDF biner mentah.
2. Kunci sitasi `citekey` di setiap berkas `.md` dapat langsung disitir oleh AI di dokumen LaTeX menggunakan `\cite{<citekey>}`.

---

## 5. Rencana Pengujian

1. **Instalasi:** `uv add markitdown` ke environment virtual proyek.
2. **Uji Ingestion arXiv:** Menjalankan `python -m tools.ingest_ref https://arxiv.org/abs/2304.03608` (Paper ALIKED).
3. **Verifikasi Output:**
   - Memastikan berkas `docs/references/zhao2023aliked.md` tercipta dengan YAML frontmatter lengkap dan teks bersih.
   - Memastikan berkas `proposal/references.bib` terbuat dan memuat entri BibTeX `zhao2023aliked`.
4. **Pembaruan `CLAUDE.md`:** Menambahkan catatan panduan penggunaan `docs/references/` dan melakukan commit git.
