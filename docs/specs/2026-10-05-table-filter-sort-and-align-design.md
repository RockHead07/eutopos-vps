# Spesifikasi Desain: Table Left-Alignment, Filter Bar, dan Column Sorting

Tanggal: 2026-10-05  
Status: Draf disetujui (siap implementasi)  
Prinsip: Ponytail (Anti-overengineering & YAGNI)

---

## 1. Latar Belakang & Masalah

Pada dashboard eutopos VPS:
1. **Perataan Kolom (Alignment):** Kolom aksi (*Action*) pada tabel Jobs saat ini rata kanan (`text-right`), menyisakan rongga kosong yang lebar dari kolom data sebelumnya (`By`). Agar tampilan tabel lebih kompak, rapi, dan konsisten dengan seluruh kolom lainnya, seluruh isi tabel dan header disepakati menjadi rata kiri (`text-left`).
2. **Kebutuhan Filter:** Saat jumlah data jobs dan versi peta bertambah, pengguna membutuhkan cara cepat untuk memfilter data berdasarkan kata kunci (pencarian teks bebas), status pekerjaan (*done*, *failed*, *queued*), dan nama area (*floor10*, *demo*).
3. **Kebutuhan Sorting:** Pengguna membutuhkan kemampuan mengurutkan data tabel dengan mengeklik header kolom (misal: urutkan berdasarkan `#` ID, nama Area, atau Status) yang dilengkapi indikator ikon panah atas-bawah `↕`.

---

## 2. Tujuan & Cakupan

### Tujuan
- Menyamakan seluruh perataan kolom tabel di dashboard menjadi rata kiri (`text-left`), termasuk kolom Action dan angka/ID.
- Menyediakan komponen filter bar yang bersih dan reusable ([`TableFilterBar`](file:///d:/Dev/Projects/eutopos-vps/web/components/TableFilterBar.tsx)) di atas tabel.
- Menyediakan kemampuan pengurutan kolom (*column sort*) interaktif pada header tabel dengan siklus 3 tahap: netral (`↕`) -> ascending (`↑`) -> descending (`↓`) -> netral.
- Menerapkan fitur ini pada dua halaman tabel utama:
  1. Halaman Jobs ([`/jobs/`](file:///d:/Dev/Projects/eutopos-vps/web/app/jobs/page.tsx))
  2. Halaman Map Versions ([`/maps/`](file:///d:/Dev/Projects/eutopos-vps/web/app/maps/page.tsx))

### Non-Goals (Batasan Ponytail / YAGNI)
- **Tanpa Pustaka Eksternal:** Dilarang menginstal TanStack Table, lodash, atau library sorting/filtering eksternal. Semua operasi menggunakan array built-in JavaScript (`filter`, `sort`, `localeCompare`).
- **Tanpa Sinkronisasi URL Params:** State filter dan sort disimpan di in-memory state React lokal halaman. Tidak memanipulasi `window.location` atau query params URL untuk menghindari kompleksitas batas Suspense di Next.js static export dan polling 5 detik.
- **Tabel Kecil Dikecualikan:** Tabel daftar video di `/job/` (1-3 baris) dan staging upload di `/new/` (1-2 baris) tidak memerlukan filter/sort bar.

---

## 3. Desain Komponen & UI

### 3.1 Ikon Sort Native (`web/public/icons/`)
Menambahkan tiga file SVG native di `web/public/icons/` mengikuti format standar 16x16 `currentColor` (digunakan via `<Icon name="..." />`):
- `sort.svg`: Panah atas dan bawah netral `↕` (warna samar saat belum diurutkan).
- `sort-asc.svg`: Panah atas `↑` (warna kontras aktif saat ascending).
- `sort-desc.svg`: Panah bawah `↓` (warna kontras aktif saat descending).

### 3.2 Komponen `TableFilterBar` (`web/components/TableFilterBar.tsx`)
Komponen kontrol yang diletakkan di atas tabel di dalam `<Panel>`:
- **Search Input:** Input pencarian teks cepat menggunakan shadcn/ui [`Input`](file:///d:/Dev/Projects/eutopos-vps/web/components/ui/input.tsx).
- **Status Filter:** Dropdown menggunakan shadcn/ui [`NativeSelect`](file:///d:/Dev/Projects/eutopos-vps/web/components/ui/native-select.tsx) dengan opsi dinamis sesuai tabel.
- **Area Filter:** Dropdown area unik yang diekstrak secara otomatis dari daftar data (`Array.from(new Set(data.map(d => d.area_id))).sort()`).
- **Counter & Reset:** Teks ringkas *"Showing X of Y"* dan tombol *"Reset"* yang hanya tampil jika filter sedang aktif.
- **Empty State:** Jika hasil filter 0 baris, tampilkan pesan informatif ramah: *"No matching records found"* dan tombol *"Clear filters"*.

### 3.3 Komponen / Pola `SortableHead`
Header tabel yang dapat diklik untuk mengubah urutan:
- Menggunakan `<TableHead>` dengan tombol interaktif minimalis (tanpa border, kursor pointer).
- Menampilkan teks judul kolom dan ikon sort di sampingnya (`sort`, `sort-asc`, atau `sort-desc`).
- Mendukung aksesibilitas keyboard (`Enter` / `Space`) dan atribut `aria-sort`.

### 3.4 Perataan Kolom (Alignment)
- Seluruh `<TableHead>` dan `<TableCell>` menggunakan `text-left`.
- Kelas `text-right` pada header dan cell `Action` dihapus.

---

## 4. Alur Data & State Management

1. **State Lokal di Komponen Halaman:**
   - `search`: string teks pencarian.
   - `statusFilter`: string (`"all"` atau nilai status tertentu).
   - `areaFilter`: string (`"all"` atau ID area tertentu).
   - `sortKey`: nama field yang diurutkan atau `null`.
   - `sortDir`: `"asc"` | `"desc"`.
2. **Pipeline Pemrosesan:**
   - Data mentah diterima dari `usePoll(api.jobs, 5000)` atau `usePoll(api.versions, 5000)`.
   - Tahap 1 (Filter): Menyaring array data berdasarkan kecocokan `search`, `statusFilter`, dan `areaFilter`.
   - Tahap 2 (Sort): Melakukan `.slice().sort(...)` berdasarkan `sortKey` dan `sortDir`.
   - Data hasil olahan langsung di-render ke `<TableBody>`.

---

## 5. Rencana Verifikasi

1. **Build & Type Check:**
   - `npm --prefix web run build`: Lulus static export Next.js dan TypeScript compiler tanpa warning atau error.
2. **Lockfile & Code Integrity:**
   - `npm --prefix web ci --dry-run`: Memastikan tidak ada dependensi eksternal baru yang terinstal.
   - `uv run ruff check .` dan `uv run ruff format --check .`: Memastikan integritas repo Python tetap bersih.
3. **Verifikasi Visual di Browser:**
   - Buka `http://localhost:8101/jobs/` dan `http://localhost:8101/maps/`.
   - Uji pengetikan pada input pencarian (filter instan).
   - Uji filter Status dan Area.
   - Uji klik pengurutan pada kolom `#`, `Area`, dan `Status`.
   - Pastikan seluruh konten tabel rata kiri secara konsisten.
