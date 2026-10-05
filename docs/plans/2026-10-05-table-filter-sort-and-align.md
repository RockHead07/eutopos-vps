# Table Left-Alignment, Filter Bar, and Column Sorting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menyamakan perataan semua tabel dashboard menjadi rata kiri (`text-left`), serta menambahkan komponen filter bar yang bersih dan kemampuan pengurutan kolom (*column sort*) interaktif pada halaman Jobs (`/jobs/`) dan Map Versions (`/maps/`).

**Architecture:** Membuat komponen SVG sort native di `web/public/icons/` dan komponen `SortableHead` serta `TableFilterBar` di `web/components/`. State filter (search, status, area) dan sort (key, direction) dikelola secara in-memory di level halaman menggunakan fungsi array native JavaScript (`filter`, `sort`, `localeCompare`), kemudian data terolah disajikan ke `<Table>` yang telah di-align left.

**Tech Stack:** Next.js 16 (Turbopack, static export), React 19, TypeScript, Tailwind CSS v4, shadcn/ui (`Input`, `NativeSelect`, `Button`, `Table`), SVG native via `Icon.tsx`.

## Global Constraints

- **Prinsip Ponytail & YAGNI:** Dilarang menambah pustaka eksternal (tanpa TanStack Table, lodash, dsb.).
- **Ikon Native:** Hanya menggunakan file SVG di `web/public/icons/*.svg` via `web/lib/Icon.tsx`. Dilarang menggunakan pustaka ikon eksternal.
- **Tanpa URL Sync State:** State filter dan sort murni in-memory di React state untuk menjaga kesederhanaan dan menghindari hydration mismatch pada static export dengan polling 5 detik.
- **Konsistensi Alignment:** Seluruh header `<TableHead>` dan cell `<TableCell>` di kedua tabel menggunakan `text-left`.

---

### Task 1: Add Sort Native SVGs & SortableHead Component

**Files:**
- Create: `web/public/icons/sort.svg`
- Create: `web/public/icons/sort-asc.svg`
- Create: `web/public/icons/sort-desc.svg`
- Create: `web/components/SortableHead.tsx`

**Interfaces:**
- Consumes: `<Icon name="..." />` from `@/lib/Icon`, `<TableHead>` from `@/components/ui/table`
- Produces: `<SortableHead column="..." label="..." activeKey={...} direction={...} onSort={...} />`

- [ ] **Step 1: Create `sort.svg`, `sort-asc.svg`, and `sort-desc.svg`**

Create `web/public/icons/sort.svg`:
```xml
<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" fill="none"><path fill="currentColor" fill-rule="evenodd" clip-rule="evenodd" d="M8 2.5a.75.75 0 01.53.22l2.5 2.5a.75.75 0 11-1.06 1.06L8.75 5.06V10.94l1.22-1.22a.75.75 0 111.06 1.06l-2.5 2.5a.75.75 0 01-1.06 0l-2.5-2.5a.75.75 0 111.06-1.06l1.22 1.22V5.06L6.03 6.28a.75.75 0 01-1.06-1.06l2.5-2.5A.75.75 0 018 2.5z"/></svg>
```

Create `web/public/icons/sort-asc.svg`:
```xml
<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" fill="none"><path fill="currentColor" fill-rule="evenodd" clip-rule="evenodd" d="M8 3a.75.75 0 01.53.22l3.5 3.5a.75.75 0 01-1.06 1.06L8.75 5.56V13a.75.75 0 01-1.5 0V5.56L5.03 7.78a.75.75 0 01-1.06-1.06l3.5-3.5A.75.75 0 018 3z"/></svg>
```

Create `web/public/icons/sort-desc.svg`:
```xml
<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" fill="none"><path fill="currentColor" fill-rule="evenodd" clip-rule="evenodd" d="M8 13a.75.75 0 01-.53-.22l-3.5-3.5a.75.75 0 111.06-1.06l2.22 2.22V3a.75.75 0 011.5 0v7.44l2.22-2.22a.75.75 0 111.06 1.06l-3.5 3.5A.75.75 0 018 13z"/></svg>
```

- [ ] **Step 2: Create `web/components/SortableHead.tsx`**

```tsx
"use client";
import { TableHead } from "@/components/ui/table";
import { Icon } from "@/lib/Icon";

export type SortDirection = "asc" | "desc";

interface SortableHeadProps {
  column: string;
  label: string;
  activeKey: string | null;
  direction: SortDirection;
  onSort: (column: string) => void;
  className?: string;
}

export function SortableHead({
  column,
  label,
  activeKey,
  direction,
  onSort,
  className = "",
}: SortableHeadProps) {
  const isActive = activeKey === column;
  const iconName = isActive ? (direction === "asc" ? "sort-asc" : "sort-desc") : "sort";

  return (
    <TableHead className={`text-left select-none ${className}`}>
      <button
        type="button"
        onClick={() => onSort(column)}
        aria-sort={isActive ? (direction === "asc" ? "ascending" : "descending") : "none"}
        className="inline-flex items-center gap-1.5 text-left font-medium text-foreground hover:text-ink transition-colors group focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded py-1 -my-1"
      >
        <span>{label}</span>
        <span
          className={`inline-flex items-center transition-opacity ${
            isActive ? "text-forest opacity-100 font-bold" : "opacity-40 group-hover:opacity-75"
          }`}
        >
          <Icon name={iconName} />
        </span>
      </button>
    </TableHead>
  );
}
```

- [ ] **Step 3: Verify TypeScript build**

Run: `npm --prefix web run build`
Expected: Passes with no TypeScript errors.

- [ ] **Step 4: Commit Task 1**

```bash
git add web/public/icons/sort*.svg web/components/SortableHead.tsx
git commit -m "feat(web): add sort icons and SortableHead component"
```

---

### Task 2: Create Reusable TableFilterBar Component

**Files:**
- Create: `web/components/TableFilterBar.tsx`

**Interfaces:**
- Consumes: `<Input>` from `@/components/ui/input`, `<NativeSelect>` from `@/components/ui/native-select`, `<Button>` from `@/components/ui/button`
- Produces: `<TableFilterBar ... />` with search, status dropdown, area dropdown, count, and reset button.

- [ ] **Step 1: Write `web/components/TableFilterBar.tsx`**

```tsx
"use client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";

interface Option {
  value: string;
  label: string;
}

interface TableFilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  statusFilter: string;
  onStatusChange: (value: string) => void;
  statusOptions: Option[];
  areaFilter: string;
  onAreaChange: (value: string) => void;
  areaOptions: string[];
  totalCount: number;
  filteredCount: number;
  onReset: () => void;
}

export function TableFilterBar({
  search,
  onSearchChange,
  searchPlaceholder = "Search...",
  statusFilter,
  onStatusChange,
  statusOptions,
  areaFilter,
  onAreaChange,
  areaOptions,
  totalCount,
  filteredCount,
  onReset,
}: TableFilterBarProps) {
  const isFiltered = Boolean(search.trim() || statusFilter !== "all" || areaFilter !== "all");

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pb-3.5 mb-2 border-b border-line/60">
      <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[240px]">
        <div className="w-full sm:w-64">
          <Input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            className="h-8 text-xs bg-card"
          />
        </div>
        {statusOptions.length > 0 && (
          <div className="w-36">
            <NativeSelect
              value={statusFilter}
              onChange={(e) => onStatusChange(e.target.value)}
              className="h-8 text-xs bg-card"
            >
              <option value="all">All statuses</option>
              {statusOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </NativeSelect>
          </div>
        )}
        {areaOptions.length > 0 && (
          <div className="w-36">
            <NativeSelect
              value={areaFilter}
              onChange={(e) => onAreaChange(e.target.value)}
              className="h-8 text-xs bg-card"
            >
              <option value="all">All areas</option>
              {areaOptions.map((area) => (
                <option key={area} value={area}>
                  {area}
                </option>
              ))}
            </NativeSelect>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground ml-auto">
        <span>
          Showing {filteredCount} of {totalCount}
        </span>
        {isFiltered && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onReset}
            className="h-7 px-2 text-xs text-forest hover:text-forest-hover font-medium"
          >
            Reset
          </Button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript build**

Run: `npm --prefix web run build`
Expected: Passes with no errors.

- [ ] **Step 3: Commit Task 2**

```bash
git add web/components/TableFilterBar.tsx
git commit -m "feat(web): create reusable TableFilterBar component"
```

---

### Task 3: Implement Left-Alignment, Filter Bar & Column Sort in Jobs Page

**Files:**
- Modify: `web/app/jobs/page.tsx`

**Interfaces:**
- Consumes: `<TableFilterBar>`, `<SortableHead>`, `<Table>`, `<TableRow>`, `<TableCell>`
- Produces: Updated JobsPage with all columns left-aligned, filtering by search/status/area, and column sorting.

- [ ] **Step 1: Update `web/app/jobs/page.tsx`**

Integrate filter and sort state in `JobsPage`:
- Filter state: `search`, `statusFilter` ("all"), `areaFilter` ("all").
- Sort state: `sortKey` (default "id"), `sortDir` (default "desc").
- All `<TableHead>` and `<TableCell>` classes use `text-left` (remove `text-right` from `Action`).
- Cycling sort order: click active key toggles `asc` <-> `desc`; click new key switches to `asc`.
- If `filteredJobs.length === 0 && jobs.length > 0`, render an inline empty filtered state with *"No matching jobs found"* and a button to clear filters.

- [ ] **Step 2: Verify build**

Run: `npm --prefix web run build`
Expected: Compiled successfully with all routes static.

- [ ] **Step 3: Commit Task 3**

```bash
git add web/app/jobs/page.tsx
git commit -m "feat(web): left-align and add filter and sort to jobs page"
```

---

### Task 4: Implement Left-Alignment, Filter Bar & Column Sort in Maps Page

**Files:**
- Modify: `web/app/maps/page.tsx`

**Interfaces:**
- Consumes: `<TableFilterBar>`, `<SortableHead>`, `<Table>`, `<TableRow>`, `<TableCell>`
- Produces: Updated MapsPage with left-aligned columns, filtering by search/status/area, and sorting by Area, Version, Status, Job ID, or Published by.

- [ ] **Step 1: Update `web/app/maps/page.tsx`**

Integrate filter and sort state in `MapsPage`:
- Filter state: `search`, `statusFilter` ("all"), `areaFilter` ("all").
- Sort state: `sortKey` (default "version"), `sortDir` (default "desc").
- All `<TableHead>` and `<TableCell>` use `text-left`.
- Filter status options: `published`, `candidate`, `retired`, `rejected`.
- If `filteredVersions.length === 0 && versions.length > 0`, render an inline empty filtered state with *"No matching map versions found"* and clear button.

- [ ] **Step 2: Verify build**

Run: `npm --prefix web run build`
Expected: Compiled successfully with all routes static.

- [ ] **Step 3: Commit Task 4**

```bash
git add web/app/maps/page.tsx
git commit -m "feat(web): left-align and add filter and sort to maps page"
```

---

### Task 5: End-to-End Verification & Workspace Synchronization

**Files:**
- Test: `npm --prefix web run build`
- Test: `npm --prefix web ci --dry-run`
- Test: `uv run ruff check .` and `uv run ruff format --check .`
- Sync: Copy built `web/out/*` to `D:\wt\bento-lite\web\out` so the active FastAPI server on port 8101 immediately serves the changes.

- [ ] **Step 1: Run project-wide verifications**

Run:
```bash
npm --prefix web run build
npm --prefix web ci --dry-run
uv run ruff check .
uv run ruff format --check .
```
Expected: All checks pass cleanly with 0 errors.

- [ ] **Step 2: Sync built static assets to active server**

Copy `web/out/*` to `D:\wt\bento-lite\web\out` so the user can test immediately at `http://localhost:8101/jobs/` and `http://localhost:8101/maps/`.

- [ ] **Step 3: Final check and commit summary**
