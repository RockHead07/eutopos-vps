# Tiket CO-STAR · Node graph rekonstruksi dengan kotak ikon kecil

Ditulis 27 November 2026 dan diperbarui 28 November 2026 untuk agy. Lanjutkan di `D:/wt/pipeline-node-graph` dengan baseline `3402f5a`.

## C. Context

Dashboard Eutopos di `/job/?id=<id>` sudah punya implementasi graph di worktree agy. Graph memakai kotak ikon kecil dengan nama dan durasi di luar kotak. Kanvas pada implementasi awal selalu gelap. Revisi ini meminta kanvas mengikuti tema dashboard. Bagus akan memilih sendiri aset ikon. Untuk tahap ini, pakai placeholder seragam di semua node.

Rujukan susunan node di mesin yang sama adalah `C:/Users/UNKNOWN/.codex/visualizations/2026/11/21/01a1fda6-979e-7560-b4e8-f27f25dbf7d9/pipeline-node-graph-compact.html`. Warna kanvas mengikuti ketentuan tema di bawah. Kontrol simulasi dan angka contoh di mockup khusus demonstrasi.

- `web/app/job/page.tsx` mengambil job tiap 5 detik dan merender `web/components/PipelineStageIndicator.tsx`. `web/app/globals.css` memuat gaya timeline. `web/lib/i18n/` menangani Indonesia dan Inggris.
- `server/worker.py` menjalankan `gpu_wait → extract → build → inspect → register → align → gate`. Job dapat selesai walaupun `summary.align.status` adalah `skipped` atau `failed`. `summary.gate.decision` bernilai `publish`, `hold`, atau `reject`. `publish` di sini berarti lolos gate.
- `server/scan_report.py` menyediakan `summary.report.processing` dengan `stage_seconds`, `queue_s`, `gpu_wait_s`, dan `total_s`. Durasi tahap tersimpan ketika laporan dibuat. Job lama atau gagal sebelum laporan dibuat dapat tidak memilikinya.
- `web/lib/api.ts` menyediakan data versi melalui `api.versions()`. Cocokkan `job.map_version_id` ke `version.id` untuk membaca status publikasi dan `splat_status`, `splat_stage`, `splat_error`, serta `splat_summary.train_seconds`. Publish peta dan Build 3D punya status terpisah.

## O. Objective

### 1. Tampilan dan interaksi

- Buat kanvas bertema terang di Light Mode dan gunakan kanvas charcoal saat Dark Mode. Gunakan grid titik samar pada keduanya.
- Setiap node berupa kotak **42 × 42 px** dengan sudut membulat ringan. Nama dan satu baris status/durasi berada di bawah kotak pada desktop. Deskripsi, alasan, dan rincian waktu berada di panel detail. Area interaksi, termasuk label, minimal 44 × 44 px.
- Di kanvas lebar, dua input bergabung ke rangkaian tahap yang dibaca dari kiri ke kanan. Keputusan Gate dan dua keluaran turun ke jalur cabang. Pada lebar menengah, tahap inti boleh dilipat menjadi dua baris. Di ponsel, susun tahap vertikal dengan nama dan durasi di samping kotak kecil. Jangan menambah geser horizontal.
- Pakai node HTML/React, konektor SVG, dan animasi kabel CSS. Posisikan ujung kabel pada port kotak ikon setelah perubahan lebar kontainer, ukuran teks, atau locale.
- Sumber pemetaan **Video** dan **Paket foto berpose** bertemu di Extract. Tandai sumber berdasarkan `job.videos` dengan `role === "peta"` dan `kind`. Gunakan kompatibilitas job lama dari API. Foto uji tidak menyalakan cabang input pemetaan.
- Urutan DOM dan keyboard mengikuti urutan kerja, termasuk ketika layout desktop berbalik arah. Klik atau tekan Enter pada kartu untuk menampilkan deskripsi, status, waktu dan alasan jika tersedia di panel detail. Di kartu Build, tampilkan rincian pasangan gambar, matching, dan SfM bila `summary.run.t_map_s` menyediakan waktunya.

#### Tema kanvas pipeline

- Di `web/app/globals.css`, gunakan token global untuk warna kanvas di kedua tema. Di Dark Mode, latar dashboard dan graph memakai `#202225`, panel `#292B2F`, kotak node netral `#2F3136`, dan border `#40444B`. Pertahankan aksen hijau Eutopos `#82AB8E`. Tema **Sistem** mengikuti kelas yang diterapkan oleh pengatur tema dashboard.
- Light Mode memakai `--canvas` untuk latar graph, `--card` untuk kotak node, `--mist` untuk sorotan aktif, `--line` untuk border dekoratif, serta `--ink` dan `--slate` untuk label, ikon placeholder, dan durasi. Buat titik grid dan kabel belum aktif dari campuran token netral dengan latar agar tetap terlihat. Gunakan hijau Eutopos dari `--forest` dan `--ok-fg` untuk jalur aktif, jalur selesai, pulse, dan fokus.
- Ganti literal warna yang selama ini khusus untuk charcoal pada hover, outline terpilih, label selesai, port, serta kotak peringatan dan gagal dengan token scoped untuk kedua tema. Pakai `--busy-fg`, `--bad-fg`, dan pasangan latar yang sesuai di Light Mode. Pastikan label node belum aktif tetap terbaca.
- Pergantian tema harus memperbarui kanvas, grid, node, port, kabel, dan teks dalam tampilan yang sama. Pertahankan ukuran, geometri, pilihan node, dan status job saat tema berganti.

#### Konektor

- Sambungkan kotak dengan garis solid sekitar **1–1,5 px**, belokan halus, dan port sisi sekitar **4–5 px**. Jalur masuk/keluar mengikuti kotak, sehingga kabel tidak memotong label di bawahnya. Marker kepala panah dan pola putus-putus tidak dipakai.
- Kelompokkan input yang bergabung, tiga keputusan Gate, dan dua keluaran dengan garis cabang yang memakai ruang kosong antarnode. Di ponsel gunakan gutter samping. Segmen bersama tidak dibuat lebih tebal karena stroke bertumpuk.
- Jalur belum dipilih memakai warna netral redup dan jalur selesai memakai sage solid. Hanya kabel menuju tahap aktif yang diberi satu segmen terang pendek yang bergerak dari sumber ke tujuan. Saat animasi dijeda atau reduced motion aktif, pertahankan penanda status yang statis.
- Uji skenario **Build berjalan** dan **Peta terbit · 3D berjalan** pada beberapa lebar. Pastikan tidak ada kabel yang menabrak kotak atau label. Struktur graph, status API, dan durasi mengikuti poin tiket lainnya.

```text
Video ─┐
       ├─► Extract → Build → Inspect → Register → Align → Gate
Foto ──┘                                                    │
                                                   Keputusan Gate
             ├─► Ditolak   · alasan pemeriksaan
             ├─► Ditahan   · alasan dan status aktual versi
             └─► Lolos     · hasil pemeriksaan

Setelah job peta selesai tanpa penolakan
  ├─► Publikasi peta · status versi aktual
  └─► Build 3D      · status job Splat yang terpisah
```

### 2. Status dan durasi

| Kondisi API | Perlakuan di UI |
|---|---|
| Unggahan, antrean worker, atau `running/gpu_wait` | Tampilkan teks menunggu yang sesuai. Kabel diam. |
| `running` dengan tahap aktif yang diketahui | Sorot kartu dan animasikan tepat satu kabel yang masuk ke tahap aktif. Untuk Extract animasikan kabel dari sumber aktif. |
| Tahap gagal sebelum Gate | Tandai tahap gagal, hentikan animasi, tampilkan alasan yang tersedia, dan biarkan tahap berikutnya belum mulai. |
| Align `applied`, `skipped`, atau `failed` | Tampilkan hasil dan alasan jika tersedia. Job utama dapat berlanjut ke Gate. |
| Gate `publish`, `hold`, atau `reject` | Sorot hanya cabang Lolos, Ditahan, atau Ditolak sesuai respons. Jika penolakan terjadi di Gate, tampilkan alasan dan hentikan alur keluaran. |
| Versi `published` | Baru tampilkan status **Terbit** pada node Publikasi. Jika versi belum tersedia, tampilkan status yang belum diketahui. Kegagalan publish tidak mengubah riwayat tahap rekonstruksi. |
| Splat `queued`, `running`, `done`, atau `failed` | Tampilkan status independen. Animasikan kabel hanya saat Splat berjalan di luar `gpu_wait`. Saat belum ada job Splat, tampilkan **Opsional** atau **Belum dijadwalkan** sesuai data. |
| Polling gagal atau data terlambat | Pertahankan status terakhir dengan penanda pembaruan tertunda dan jeda animasi sampai data segar diterima. |

- Pakai ulang polling job. Ambil versi terkait hanya bila job memiliki `map_version_id`. Pakai ulang fetch atau cache untuk versi jika tersedia. Sinkronkan setelah publish, hindari permintaan tumpang tindih, dan bersihkan timer ketika halaman ditinggalkan.
- Di bawah node tahap tampilkan `stage_seconds[stage]` jika tercatat, termasuk angka nol. Gunakan `—` bila data kosong. Bedakan data historis yang tidak punya Align/Gate dari hasil `skipped` yang eksplisit. Jangan menghitung durasi tahap dari waktu polling.
- Di bawah graph tampilkan **Antrean worker**, **Menunggu GPU**, **Rekonstruksi**, dan **Total sejak antre**. `total_s` sudah mencakup waktu menunggu GPU dari saat worker mulai. Jika kedua angka ada, durasi rekonstruksi adalah `total_s - gpu_wait_s`. Jika antrean dan `total_s` tersedia, total sejak antre adalah `queue_s + total_s`. Versi dengan data parsial tetap menampilkan metrik yang diketahui. Saat berjalan tampilkan **Sejak worker mulai** dari `started_at`. Labeli `train_seconds` sebagai **Waktu training 3D** di detail Splat dan pisahkan dari total peta.
- Timer tahap aktif yang akurat memerlukan timestamp tahap dari worker dan berada di luar tiket ini. Status teks adalah sumber informasi utama. Hindari persentase per tahap yang tidak tersedia dari API.

### 3. Slot ikon sementara

- Pakai placeholder netral yang seragam, misalnya outline persegi kecil di tengah kotak. Gambar bersifat dekoratif. Nama, status, dan durasi tetap tersedia untuk keyboard dan pembaca layar.
- Pastikan setiap slot bisa diisi aset pilihan Bagus berdasarkan ID node tanpa mengubah ukuran kotak atau titik kabel. Pemilihan dan pemasangan ikon final, termasuk keputusan penggunaan Rive, dilanjutkan setelah aset diberikan.
- Graph tahap ini tidak memuat canvas Rive, `.riv`, WASM, atau ikon dari sumber luar. Simpan pekerjaan Rive yang sudah ada sebagai bahan lanjutan. Satu kontrol jeda mengatur animasi kabel dan menghormati `prefers-reduced-motion`.

## S. Style

Ikuti `CLAUDE.md`, komponen dashboard yang ada, dan i18n ID/EN. Desain graph tetap baca-saja dengan fokus keyboard yang terlihat, status yang terbaca tanpa warna, serta panel detail yang bisa dipakai di layar sentuh. Lingkup kode adalah `web/` dan tes yang relevan. Pertahankan kontrak API, aturan publish, worker, dan konfigurasi deployment. Graph dengan placeholder tidak memerlukan dependensi baru.

## T. Tone

Bahasa Indonesia yang lugas dengan istilah teknis yang sudah dipakai repo. Label menyebutkan kondisi yang nyata, misalnya **Menunggu GPU**, **Build berjalan**, atau **Ditahan di Gate**. Jelaskan sebab jika API menyediakannya.

## A. Audience

Operator dashboard perlu tahu pekerjaan yang sedang berjalan, hasilnya, dan waktu yang dipakai. Developer perlu melihat tahap yang gagal, keputusan Gate, dan status publikasi serta Build 3D secara terpisah. Bagus meninjau desain dan bukti uji sebelum integrasi.

## R. Response

Lanjutkan di worktree agy yang sudah ada. Serahkan lokasi worktree, baseline SHA, ringkasan diff, hasil pengujian, dan kendala terbuka. Sertakan tangkapan layar desktop dan ponsel yang menunjukkan kotak placeholder, posisi label/durasi, serta cabang Gate. Rekaman singkat memperlihatkan kabel aktif dan kontrol jeda. Simpan bukti di luar diff aplikasi. Commit, push, PR, merge, dan deploy mengikuti instruksi Bagus.

### Kriteria penerimaan

- Graph sesuai alur pada tiket. Kotak ikon berukuran seragam, nama dan waktu berada di luar kotak, dan konektor tetap tersambung jika Inspect → Register turun baris. Status Align yang dilewati, tiga hasil Gate, dan dua keluaran berasal dari job dan versi yang tepat.
- Uji di browser minimal pada 320–390 px dan desktop, tema terang/gelap serta locale ID/EN. Periksa keyboard, port/kabel setelah resize, dan pemilihan kartu.
- Ambil bukti Light dan Dark dari job yang sama. Uji **Terang → Gelap → Sistem** tanpa reload. Di Light Mode pastikan kanvas terang dan node aktif, selesai, tertunda, dan gagal tetap jelas. Di Dark Mode periksa token global di latar halaman, panel, dan kanvas graph pada satu build, beserta aksen hijau.
- Uji antrean dan GPU wait, Build aktif lalu selesai atau gagal, Gate hold/reject, versi published, Splat queued/running/gpu_wait/done/failed, job lama tanpa report, dan respons polling yang gagal lalu pulih. Fixture sintetis hanya untuk pengujian dan bukti lokal.
- Tambahkan regresi saat `GET /api/versions` gagal atau tertunda dan `GET /api/jobs/{id}` tetap sehat. Jika status terakhir Build 3D adalah `running`, tandai status versi tertunda dan jeda kabel Build 3D hingga data versi kembali segar.
- Tambahkan regresi saat `splat_status: "failed"` dan `has_splat: true`. Node Build 3D menampilkan **Gagal** dan alasan dari percobaan terbaru. Aset lama tetap dicatat tersedia sebagai informasi terpisah. Dalam detail job gagal, labeli `splat_stage` sebagai **Tahap saat gagal** bila tersedia. Pakai `splat_summary: null` pada fixture gagal agar sesuai dengan respons `server/maps_api.py`.
- Placeholder tampil di setiap node. Buktikan bahwa halaman graph tidak memuat aset ikon luar, `.riv`, atau WASM. Uji jeda animasi kabel, reduced motion, dan perpindahan job/stage.
- `npm ci`, `npx --no-install tsc --noEmit`, dan `npm run build` di `web/` berhasil. Pengujian dilakukan lokal dengan fixture atau data uji yang diizinkan.
