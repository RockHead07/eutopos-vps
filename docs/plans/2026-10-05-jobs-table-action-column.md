# Jobs Table Action Column Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menambahkan kolom aksi eksplisit pada tabel pekerjaan di `/jobs/` dengan tombol shadcn/ui (`Button`) yang dinamis sesuai status (`Inspect map` untuk `done`, `View progress` untuk `running`/`queued`, `View error` untuk `failed`).

**Architecture:** Memperbarui berkas `web/app/jobs/page.tsx` dengan menambahkan `<TableHead>` dan `<TableCell>` berformat `text-right` yang memuat `Button asChild` dari `@/components/ui/button`, membungkus `<Link>` native `@/lib/Link`, serta ikon native SVG dari `@/lib/Icon`.

**Tech Stack:** Next.js 16, React 19, Tailwind CSS v4, shadcn/ui (`Button`), TypeScript.

## Global Constraints

- Tanpa penambahan library ikon eksternal; hanya menggunakan `Icon` dari `web/lib/Icon.tsx` (`web/public/icons/*.svg`).
- Komponen menggunakan `Button` resmi shadcn yang sudah ada di `web/components/ui/button.tsx`.
- Data 100% nyata dari `usePoll(api.jobs, 5000)`; tanpa nilai fallback atau data dummy.
- Pengerjaan dilakukan di worktree `D:\wt\jobs-table-action` pada branch `feat/jobs-table-action`.
- `npm --prefix web run build` dan `npm --prefix web ci --dry-run` wajib lulus tanpa galat.

---

### Task 1: Tambahkan Kolom Action pada `web/app/jobs/page.tsx`

**Files:**
- Modify: `web/app/jobs/page.tsx:28-48`

**Interfaces:**
- Consumes: `Job` dari `@/lib/api`, `Button` dari `@/components/ui/button`, `Icon` dari `@/lib/Icon`, `Link` dari `@/lib/Link`.
- Produces: Kolom aksi tabel dengan tombol yang dapat diklik langsung menuju `/job/?id=${j.id}`.

- [ ] **Step 1: Modifikasi `web/app/jobs/page.tsx` untuk menyertakan `Button` dan `Icon`**

Pastikan impor memuat `Button` dan `Icon`:
```tsx
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { api } from "@/lib/api";
import { PageHead } from "@/lib/PageHead";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";
```

Perbarui struktur `<Table>`:
```tsx
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>Area</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>By</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((j) => (
                <TableRow key={j.id}>
                  <TableCell className="num"><Link href={`/job/?id=${j.id}`}>{j.id}</Link></TableCell>
                  <TableCell>{j.area_id}</TableCell>
                  <TableCell><StatusBadge status={j.status} /></TableCell>
                  <TableCell className="text-muted-foreground">{j.status === "done" ? "-" : (j.stage ?? "-")}</TableCell>
                  <TableCell className="text-muted-foreground">{j.created_by}</TableCell>
                  <TableCell className="text-right">
                    <Button asChild variant="outline" size="sm" className="rounded-full gap-1.5 font-medium text-xs whitespace-nowrap">
                      <Link href={`/job/?id=${j.id}`}>
                        <Icon name={j.status === "done" ? "view-3d" : "arrow-up-right"} />
                        <span>{j.status === "done" ? "Inspect map" : j.status === "failed" ? "View error" : "View progress"}</span>
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
```

- [ ] **Step 2: Jalankan build lokal untuk memvalidasi tipe TypeScript**

Run: `npm --prefix web run build` (di dalam `D:\wt\jobs-table-action`)  
Expected: Kompilasi sukses (`✓ Compiled successfully`).

- [ ] **Step 3: Commit perubahan Task 1**

```bash
git -C D:\wt\jobs-table-action add web/app/jobs/page.tsx
git -C D:\wt\jobs-table-action commit -m "feat(web): add action column with status-aware buttons in jobs table"
```

---

### Task 2: Verifikasi Build & Kerapian UI

**Files:**
- Test/Verify: `web/app/jobs/page.tsx`

- [ ] **Step 1: Jalankan verifikasi build statis Next.js**

Run: `npm --prefix web run build`  
Expected: Lolos 100% dan menghasilkan rute `/jobs`.

- [ ] **Step 2: Jalankan verifikasi integritas lockfile**

Run: `npm --prefix web ci --dry-run`  
Expected: Lolos 100% tanpa perubahan lockfile.

- [ ] **Step 3: Verifikasi tampilan tabel di browser**

Run dev server jika belum menyala: `npm --prefix web run dev`  
Periksa rute `http://localhost:3000/jobs/`:
- Pastikan kolom Action berada di sebelah kanan.
- Pastikan tombol pada baris berstatus `done` bertuliskan "Inspect map" dengan ikon 3D cube.
- Pastikan tombol pada baris berstatus `queued` / `running` bertuliskan "View progress" dengan ikon panah.
- Pastikan mengklik tombol langsung membuka halaman detail `/job/?id=N`.
