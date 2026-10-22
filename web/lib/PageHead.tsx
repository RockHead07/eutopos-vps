"use client";

import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SystemDiagnosticsPopover } from "@/components/SystemDiagnosticsPopover";
import { api } from "@/lib/api";
import { Icon } from "@/lib/Icon";
import { useT } from "@/lib/i18n";
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
  const t = useT();

  const free = effectiveFree(sys?.storage);
  const isStorageCritical = free?.level === "bad";
  const isStorageWarning = free?.level === "warn";
  const minFreeGb = free?.gb ?? null;
  const hardLimit = free ? HARD_LIMIT_GB[free.source] : 20;
  const where = free?.source === "host" ? "Drive Windows" : "Ruang disk";

  return (
    <div className="chips">
      {s?.area_id && (
        <span
          className="chip"
          title={
            health?.aligned
              ? t("head.metricTitle")
              : t("head.modelTitle")
          }
        >
          <Icon name="active-map" />
          {t("head.serving", { area: s.area_id })}
          {s.map_version !== null && ` v${s.map_version}`}
          {health?.aligned ? (
            <span className="ml-1 text-[10px] font-semibold text-forest">· {t("head.metric")}</span>
          ) : health ? (
            <span className="ml-1 text-[10px] text-muted-foreground">· {t("head.model")}</span>
          ) : null}
        </span>
      )}

      {/* Proactive storage warning chip */}
      {isStorageCritical && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="chip bad cursor-pointer select-none border-0 transition-colors"
          title={t("head.storageCriticalTitle", {
            where,
            free: minFreeGb?.toFixed(1) ?? "",
            limit: hardLimit,
          })}
          aria-label={t("head.storageCriticalAlert")}
        >
          <span className="dot" aria-hidden="true" />
          <span>{t("head.storageUnder", { limit: hardLimit })}</span>
        </button>
      )}

      {isStorageWarning && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="chip cursor-pointer select-none border-0 transition-colors bg-amber-500/10 text-amber-700 hover:bg-amber-500/15"
          title={t("head.storageLowTitle", {
            where,
            free: minFreeGb?.toFixed(1) ?? "",
            limit: hardLimit,
          })}
          aria-label={t("head.storageLowWarning")}
        >
          <span className="dot bg-amber-600" aria-hidden="true" />
          <span>{t("head.storageLow", { free: minFreeGb?.toFixed(0) ?? "" })}</span>
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
            title={t("head.sysDiagClick")}
            aria-label={t("head.sysDiagAria")}
          >
            <span className="dot" aria-hidden="true" />
            <span>
              {error
                ? t("head.vpsUnreachable")
                : s
                ? t("head.vpsOnline")
                : t("head.checking")}
            </span>
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
