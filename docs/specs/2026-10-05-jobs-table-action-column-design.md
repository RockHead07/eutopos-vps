# Jobs Table Action Column Design Spec

**Tanggal:** 2026-10-05  
**Status:** Approved  
**Cabang:** `feat/jobs-table-action`  
**Tujuan:** Menambahkan kolom aksi eksplisit pada tabel pekerjaan di `/jobs/` agar pengguna dapat langsung membuka dan menginspeksi peta 3D atau melihat progres/galat pekerjaan tanpa bergantung pada klik nomor ID `#` kecil.

---

## 1. Masalah & Kebutuhan Pengguna

### Masalah
Pada halaman daftar pekerjaan ([`web/app/jobs/page.tsx`](file:///D:/Dev/Projects/eutopos-vps/web/app/jobs/page.tsx)), kolom tabel yang tersedia saat ini adalah `#`, `Area`, `Status`, `Stage`, dan `By`. Satu-satunya tautan untuk membuka detail pekerjaan dan visualisasi peta 3D adalah angka ID `#` kecil di kolom pertama (`1`, `2`, `3`, dst.).
- Pengguna baru kesulitan menemukan pintu masuk ke halaman detail pekerjaan.
- Sisi kanan tabel memiliki ruang kosong lebar yang belum dimanfaatkan.

### Kebutuhan
Menyediakan kolom khusus **Action** di sisi paling kanan tabel dengan tombol resmi shadcn/ui yang memiliki teks dan ikon jelas sesuai status pekerjaan.

---

## 2. Pilihan Ikon Native

Proyek tidak menggunakan library ikon eksternal (seperti `lucide-react`). Ikon yang digunakan sepenuhnya berasal dari ikon native SVG yang sudah ada di [`web/public/icons/`](file:///D:/Dev/Projects/eutopos-vps/web/public/icons/):

1. **`view-3d.svg`:**
   - Digunakan untuk status `done` (menandakan bahwa pekerjaan telah selesai dan peta 3D point cloud siap diinspeksi).
   - Teks tombol: **"Inspect map"**.
2. **`arrow-up-right.svg`:**
   - Digunakan untuk status selain `done`:
     - Status `running` / `queued` / `uploading`: Teks tombol **"View progress"**.
     - Status `failed`: Teks tombol **"View error"**.

Komponen perender ikon tetap menggunakan [`web/lib/Icon.tsx`](file:///D:/Dev/Projects/eutopos-vps/web/lib/Icon.tsx) (`<Icon name="..." />`).

---

## 3. Desain Komponen & Antarmuka

### Modifikasi Berkas: `web/app/jobs/page.tsx`

1. **TableHeader:**
   Menambahkan kolom header di ujung kanan dengan alignment kanan:
   ```tsx
   <TableHead className="text-right">Action</TableHead>
   ```

2. **TableBody Cell:**
   Menambahkan sel aksi di setiap baris:
   ```tsx
   <TableCell className="text-right">
     <Button asChild variant="outline" size="sm" className="rounded-full gap-1.5 font-medium text-xs whitespace-nowrap">
       <Link href={`/job/?id=${j.id}`}>
         <Icon name={j.status === "done" ? "view-3d" : "arrow-up-right"} />
         <span>{j.status === "done" ? "Inspect map" : j.status === "failed" ? "View error" : "View progress"}</span>
       </Link>
     </Button>
   </TableCell>
   ```

3. **Komponen Pembungkus:**
   - Menggunakan `Button` shadcn/ui dengan varian `outline` dan `rounded-full` (radius pill kapsul khas Eutopos).
   - Menggunakan `asChild` membungkus `<Link>` dari `web/lib/Link.tsx` guna menghindari prefetch 404 pada Next.js static export.

---

## 4. Aliran Data & Penanganan Galat

- **Sumber Data:** Murni memanfaatkan `data: jobs` dari hook `usePoll(api.jobs, 5000)` yang sudah berjalan.
- **Tanpa Data Fiktif:** Setiap baris tombol merefleksikan nilai riil `j.id` dan `j.status` dari server FastAPI.
- **Responsivitas:** Kelas `whitespace-nowrap` mencegah tombol terlipat dua baris pada layar mobile saat tabel digulir secara horizontal.

---

## 5. Rencana Verifikasi

1. **Build Verifikasi:**
   Jalankan `npm --prefix web run build` untuk memastikan tipe TypeScript valid dan static export menghasilkan berkas tanpa galat.
2. **Docker Lockfile Verifikasi:**
   Jalankan `npm --prefix web ci --dry-run` untuk menjamin tidak ada dependensi yang berubah secara tidak sengaja.
3. **Pemeriksaan Browser:**
   Buka `http://localhost:3000/jobs/` di desktop dan layar ponsel (responsif) untuk memastikan tombol tampak proporsional, teks rapi, dan tautan mengarah tepat ke `/job/?id=N`.
