"use client";

import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SystemDiagnosticsPopover } from "@/components/SystemDiagnosticsPopover";
import { api } from "@/lib/api";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { useSharedPoll } from "@/lib/usePoll";
import { effectiveFree, HARD_LIMIT_GB } from "@/lib/storage";
import { cn } from "@/lib/utils";

type Crumb = { label: string; href?: string };

/** Chip status layanan. Menggunakan /api/service, /health, dan /api/system. */
function ServiceChips() {
  const { data: s, error } = useSharedPoll(api.service, 5000);
  const { data: health } = useSharedPoll(api.health, 10000);
  const { data: sys } = useSharedPoll(api.system, 15000);
  const [open, setOpen] = useState(false);

  const free = effectiveFree(sys?.storage);
  const isStorageCritical = free?.level === "bad";
  const isStorageWarning = free?.level === "warn";
  const minFreeGb = free?.gb ?? null;
  const hardLimit = free ? HARD_LIMIT_GB[free.source] : 20;
  const where = free?.source === "host" ? "The Windows drive" : "Available disk space";

  return (
    <div className="chips">
      {s?.area_id && (
        <span
          className="chip"
          title={
            health?.aligned
              ? "Active map served with metric coordinates (pose_building in meters)"
              : "Active map served in unitless SfM model coordinates (pending align.json reference points)"
          }
        >
          <Icon name="active-map" />
          Serving {s.area_id}
          {s.map_version !== null && ` v${s.map_version}`}
          {health?.aligned ? (
            <span className="ml-1 text-[10px] font-semibold text-forest">· Metric</span>
          ) : health ? (
            <span className="ml-1 text-[10px] text-muted-foreground">· Model</span>
          ) : null}
        </span>
      )}

      {/* Proactive storage warning chip */}
      {isStorageCritical && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="chip bad cursor-pointer select-none border-0 transition-colors"
          title={`${where} is critically low (${minFreeGb?.toFixed(1)} GB free, limit ${hardLimit} GB).`}
          aria-label="Storage critical alert"
        >
          <span className="dot" aria-hidden="true" />
          <span>Storage &lt; {hardLimit} GB</span>
        </button>
      )}

      {isStorageWarning && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="chip cursor-pointer select-none border-0 transition-colors bg-amber-500/10 text-amber-700 hover:bg-amber-500/15"
          title={`${where} is low (${minFreeGb?.toFixed(1)} GB free, limit ${hardLimit} GB).`}
          aria-label="Storage low warning"
        >
          <span className="dot bg-amber-600" aria-hidden="true" />
          <span>Storage low ({minFreeGb?.toFixed(0)} GB)</span>
        </button>
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
          className="mobile-popover sm:w-[360px] p-0 shadow-lg border border-border bg-card"
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
