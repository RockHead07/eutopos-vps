"use client";

import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SystemDiagnosticsPopover } from "@/components/SystemDiagnosticsPopover";
import { api } from "@/lib/api";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { usePoll } from "@/lib/usePoll";
import { cn } from "@/lib/utils";

type Crumb = { label: string; href?: string };

/** Chip status layanan. Isi dari /api/service (bukan teks tetap), jadi sama di setiap halaman. */
function ServiceChips() {
  const { data: s, error } = usePoll(api.service, 5000);
  const [open, setOpen] = useState(false);

  return (
    <div className="chips">
      {s?.area_id && (
        <span className="chip"><Icon name="active-map" />Serving {s.area_id}{s.map_version !== null && ` v${s.map_version}`}</span>
      )}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={cn(
              "chip cursor-pointer select-none border-0 transition-colors hover:brightness-95 focus-visible:outline-2 focus-visible:outline-forest focus-visible:outline-offset-2",
              error ? "bad" : s ? "ok" : ""
            )}
            title="Click to view system diagnostics"
            aria-label="System diagnostics: VPS status"
          >
            <span className="dot" aria-hidden="true" />
            <span>{error ? "VPS unreachable" : s ? "VPS online" : "Checking..."}</span>
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="end"
          sideOffset={8}
          className="w-[calc(100vw-2rem)] sm:w-[360px] max-w-[380px] p-0 shadow-lg border border-border bg-card overflow-hidden"
        >
          <SystemDiagnosticsPopover isOpen={open} onClose={() => setOpen(false)} />
        </PopoverContent>
      </Popover>
    </div>
  );
}

/** Kepala halaman yang sama di semua halaman: breadcrumb, judul, keterangan, dan chip status. */
export function PageHead({
  crumbs,
  title,
  children,
  controls,
}: {
  crumbs: Crumb[];
  title: string;
  children?: React.ReactNode;
  controls?: React.ReactNode;
}) {
  return (
    <div className={cn("page-head", controls && "max-lg:!grid-cols-1")}>
      <div>
        <p className="crumbs">
          <Link href="/">eutopos</Link>
          {crumbs.map((c) => (
            <span key={c.label} className="crumb">
              <span aria-hidden="true">/</span>
              {c.href ? <Link href={c.href}>{c.label}</Link> : <span>{c.label}</span>}
            </span>
          ))}
        </p>
        <h1>{title}</h1>
        {children && <div className="muted">{children}</div>}
      </div>
      <div className={cn("flex flex-col gap-2.5 items-start", controls ? "w-full lg:w-auto lg:items-end" : "md:items-end")}>
        <ServiceChips />
        {controls}
      </div>
    </div>
  );
}
