"use client";

import { useEffect, useRef, useState } from "react";
import {
  api,
  type SystemDiagnostics,
  type StorageDiagnostics,
  type StorageLocation,
  type HostDisk,
  type HealthStatus,
} from "@/lib/api";
import { Gauge } from "@/components/Gauge";
import { useLocale, useT } from "@/lib/i18n";
import type { TranslationKey } from "@/lib/i18n";
import { effectiveFree, freeLevel } from "@/lib/storage";
import { cn } from "@/lib/utils";

interface SystemDiagnosticsPopoverProps {
  isOpen: boolean;
  onClose?: () => void;
}

export function useDiagnostics(isOpen: boolean) {
  const [data, setData] = useState<SystemDiagnostics | null>(null);
  const [healthData, setHealthData] = useState<HealthStatus | null>(null);
  const [initialLoading, setInitialLoading] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const inFlightRef = useRef(false);
  const hasLoadedRef = useRef(false);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    let active = true;

    const fetchDiagnostics = async () => {
      if (inFlightRef.current) {
        return;
      }
      inFlightRef.current = true;
      if (!hasLoadedRef.current) {
        setInitialLoading(true);
      }

      try {
        const [res, h] = await Promise.all([
          api.system(),
          api.health().catch(() => null),
        ]);
        if (!active) return;
        setData(res);
        setHealthData(h);
        setRefreshError(null);
        setLastUpdated(new Date());
        hasLoadedRef.current = true;
      } catch (err: unknown) {
        if (!active) return;
        const msg = err instanceof Error ? err.message : "Failed to load telemetry";
        setRefreshError(msg);
      } finally {
        if (active) {
          setInitialLoading(false);
          inFlightRef.current = false;
        }
      }
    };

    // Panggil langsung saat popover dibuka
    fetchDiagnostics();

    // Polling setiap 10 detik selama popover tetap terbuka
    const interval = setInterval(fetchDiagnostics, 10000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [isOpen]);

  return { data, healthData, loading: initialLoading, refreshError, lastUpdated };
}

function formatUptime(seconds: number): string {
  if (seconds < 60) {
    return `${Math.floor(seconds)}s`;
  }
  const mins = Math.floor(seconds / 60);
  if (mins < 60) {
    const s = Math.floor(seconds % 60);
    return `${mins}m ${s}s`;
  }
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  if (hrs < 24) {
    return `${hrs}h ${remMins}m`;
  }
  const days = Math.floor(hrs / 24);
  const remHrs = hrs % 24;
  return `${days}d ${remHrs}h`;
}

function Verdict({
  free,
  hostKnown,
  t,
}: {
  free: ReturnType<typeof effectiveFree>;
  hostKnown: boolean;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
}) {
  if (!free) {
    return (
      <p className="rounded-md bg-canvas/60 p-2 text-[11px] text-muted-foreground">
        {t("diag.diskUnavailable")}
      </p>
    );
  }
  const where = free.source === "host" ? t("diag.onWindowsDrive") : t("diag.onServerDisk");
  const gb = Math.round(free.gb);
  if (free.level === "ok" && !hostKnown) {
    // Sehat menurut disk yang dilihat container, tapi disk itu bisa virtual: jangan menyatakan siap.
    return (
      <p className="rounded-md bg-canvas/60 p-2 text-[11px] text-muted-foreground">
        {t("diag.unconfirmedServerDisk", { gb })}
      </p>
    );
  }
  const text =
    free.level === "ok"
      ? t("diag.readyToBuild", { gb, where })
      : free.level === "warn"
        ? t("diag.diskLow", { gb, where })
        : free.source === "volume"
          ? t("diag.buildsRefused", { gb, where })
          : t("diag.windowsKeepAbove", { gb });
  return (
    <p
      className={cn(
        "rounded-md p-2 text-[11px] font-medium",
        free.level === "ok" && "bg-forest/10 text-forest",
        free.level === "warn" && "bg-amber-500/10 text-amber-700",
        free.level === "bad" && "bg-bad-bg/60 text-bad-fg",
      )}
    >
      {text}
    </p>
  );
}

function formatAge(seconds: number): string {
  return seconds < 3600 ? `${Math.round(seconds / 60)} min` : `${Math.round(seconds / 3600)} h`;
}

/** Keterangan di bawah pengukur: apa yang dilihat container, dan apakah drive fisik dilaporkan. */
function DiskNotes({
  storage,
  host,
  t,
}: {
  storage: StorageDiagnostics | undefined;
  host: HostDisk | null;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
}) {
  const maps = storage?.maps ?? null;
  const data = storage?.data ?? null;
  const shared = Boolean(
    maps && data && maps.total_bytes === data.total_bytes && maps.free_bytes === data.free_bytes,
  );
  const lines: string[] = [];
  const line = (name: string, loc: StorageLocation) =>
    `${name}: ${loc.used_gb.toFixed(1)} of ${loc.total_gb.toFixed(1)} GB used`;
  if (shared && maps) lines.push(line("/maps and /data share one disk", maps));
  else {
    if (maps) lines.push(line("/maps", maps));
    if (data) lines.push(line("/data", data));
  }
  const seen = maps ?? data;
  if (host && seen && seen.total_gb > host.total_gb) {
    lines.push(t("diag.diskLarger", { mount: host.mount }));
  }
  if (storage?.host?.stale) {
    lines.push(t("diag.readingOld", { age: formatAge(storage.host.age_s) }));
  } else if (!storage?.host) {
    lines.push(t("diag.physicalNotReported"));
  }
  if (!lines.length) return null;
  return (
    <ul className="flex flex-col gap-0.5 text-[10px] text-muted-foreground num">
      {lines.map((l) => (
        <li key={l}>{l}</li>
      ))}
    </ul>
  );
}

export function SystemDiagnosticsPopover({
  isOpen,
  onClose,
}: SystemDiagnosticsPopoverProps) {
  const { data, healthData, loading, refreshError, lastUpdated } = useDiagnostics(isOpen);
  const { locale } = useLocale();
  const t = useT();

  const storage = data?.storage;
  const free = effectiveFree(storage);
  const host = storage?.host && !storage.host.stale ? storage.host : null;
  const volume = storage?.maps ?? storage?.data ?? null;
  const gpu = data?.gpu ?? null;
  const vramPct =
    gpu && gpu.vram_used_mb !== null && gpu.vram_total_mb
      ? Math.round((gpu.vram_used_mb / gpu.vram_total_mb) * 100)
      : null;

  return (
    <div className="flex flex-col gap-3 p-3 text-xs">
      {/* Header Panel */}
      <div className="flex items-center justify-between border-b border-border pb-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-foreground text-sm">{t("diag.title")}</span>
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide uppercase",
              data?.device === "cuda"
                ? "bg-forest/15 text-forest"
                : "bg-muted text-muted-foreground"
            )}
          >
            {data?.device ? `${data.device.toUpperCase()} Mode` : t("diag.detecting")}
          </span>
        </div>
        {onClose && (
          <button
            type="button"
            data-slot="diagnostics-close"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-canvas hover:text-foreground transition-colors cursor-pointer"
            aria-label={t("diag.closeAria")}
          >
            ✕
          </button>
        )}
      </div>

      {/* Notice jika ada refresh error tetapi data sebelumnya tetap tampil */}
      {refreshError && (
        <div className="rounded-md bg-bad-bg/60 p-2 text-[11px] text-bad-fg flex items-start gap-1.5">
          <span className="font-bold">!</span>
          <span>{t("diag.refreshFailed", { error: refreshError })}</span>
        </div>
      )}

      {loading && !data ? (
        <div className="flex flex-col gap-2 py-4 items-center justify-center text-muted-foreground">
          <div className="skeleton h-4 w-3/4 rounded" />
          <div className="skeleton h-12 w-full rounded" />
          <div className="skeleton h-12 w-full rounded" />
          <span className="text-[11px] mt-1">{t("diag.readingSensors")}</span>
        </div>
      ) : (
        <>
          {/* Bagian 1: kesiapan membangun peta dan pengukur */}
          <Verdict free={free} hostKnown={host !== null} t={t} />
          <div className="grid grid-cols-3 gap-1 py-1">
            {host ? (
              <Gauge
                label={t("diag.driveHost", { mount: host.mount })}
                fill={host.percent}
                display={String(Math.round(host.free_gb))}
                unit={t("diag.gbFree")}
                level={freeLevel(host.free_gb, "host")}
                caption={t("diag.usedCaption", {
                  used: host.used_gb.toFixed(0),
                  total: host.total_gb.toFixed(0),
                })}
              />
            ) : volume ? (
              <Gauge
                label={t("diag.serverDisk")}
                fill={volume.percent}
                display={String(Math.round(volume.free_gb))}
                unit={t("diag.gbFree")}
                level={freeLevel(volume.free_gb, "volume")}
                caption={t("diag.usedCaption", {
                  used: volume.used_gb.toFixed(0),
                  total: volume.total_gb.toFixed(0),
                })}
              />
            ) : (
              <Gauge label={t("diag.disk")} fill={0} display="N/A" unit={t("diag.unavailable")} />
            )}
            <Gauge
              label={t("diag.gpuMemory")}
              fill={vramPct ?? 0}
              display={vramPct !== null ? String(vramPct) : "N/A"}
              unit={vramPct !== null ? t("diag.percentUsed") : t("diag.unavailable")}
              caption={
                gpu && gpu.vram_used_mb !== null && gpu.vram_total_mb
                  ? `${(gpu.vram_used_mb / 1024).toFixed(1)} of ${(gpu.vram_total_mb / 1024).toFixed(1)} GB`
                  : undefined
              }
            />
            <Gauge
              label={t("diag.gpuTemp")}
              fill={gpu?.temperature_c ?? 0}
              display={gpu?.temperature_c != null ? String(gpu.temperature_c) : "N/A"}
              unit={gpu?.temperature_c != null ? "°C" : t("diag.unavailable")}
              level={gpu?.temperature_c != null ? (gpu.temperature_c >= 80 ? "bad" : "ok") : undefined}
            />
          </div>
          {gpu?.name && <p className="-mt-1 text-center text-[11px] text-muted-foreground">{gpu.name}</p>}
          <DiskNotes storage={storage} host={host} t={t} />

          {/* Bagian 3: System Status & Alignment */}
          <div className="flex flex-col gap-2 border-t border-border pt-2.5">
            <span className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">
              {t("diag.systemStatus")}
            </span>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="flex flex-col rounded-md bg-canvas/60 p-2">
                <span className="text-[11px] text-muted-foreground">{t("diag.connection")}</span>
                <span className="font-semibold text-forest flex items-center gap-1.5 mt-0.5">
                  <span className="h-2 w-2 rounded-full bg-forest animate-pulse" />
                  {t("diag.reachable")}
                </span>
              </div>
              <div className="flex flex-col rounded-md bg-canvas/60 p-2">
                <span className="text-[11px] text-muted-foreground">{t("diag.serviceUptime")}</span>
                <span className="font-semibold text-foreground num mt-0.5">
                  {data?.uptime_s !== undefined ? formatUptime(data.uptime_s) : "N/A"}
                </span>
              </div>
            </div>

            {/* Metric Alignment Row */}
            <div className="flex flex-col rounded-md bg-canvas/60 p-2 text-xs">
              <span className="text-[11px] text-muted-foreground">{t("diag.activeMapCoordinateFrame")}</span>
              <span className="font-semibold text-foreground flex items-center gap-1.5 mt-0.5">
                {healthData?.aligned ? (
                  <span className="text-forest flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-forest" />
                    {t("diag.metricAligned")}
                  </span>
                ) : healthData ? (
                  <span className="text-muted-foreground flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
                    {t("diag.modelSfM")}
                  </span>
                ) : (
                  t("head.checking")
                )}
              </span>
              <span className="text-[10px] text-muted-foreground mt-0.5 leading-snug">
                {healthData?.aligned
                  ? t("diag.metricPosesDesc")
                  : t("diag.modelPosesDesc")}
              </span>
            </div>

            {data?.reloading && (
              <div className="rounded-md bg-busy-bg p-2 text-[11px] text-busy-fg">
                {t("diag.mapReloadInProgress")}
              </div>
            )}
            {data?.reload_error && (
              <div className="rounded-md bg-bad-bg p-2 text-[11px] text-bad-fg">
                {t("diag.reloadError", { error: data.reload_error })}
              </div>
            )}
          </div>

          {/* Footer Telemetry */}
          <div className="flex items-center justify-between border-t border-border/80 pt-2 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-forest" />
              {t("diag.autoRefreshing")}
            </span>
            <span className="num">
              {lastUpdated
                ? t("diag.updatedAt", {
                    time: lastUpdated.toLocaleTimeString(locale === "id" ? "id-ID" : "en-US"),
                  })
                : t("diag.updating")}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
