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
}: {
  free: ReturnType<typeof effectiveFree>;
  hostKnown: boolean;
}) {
  if (!free) {
    return (
      <p className="rounded-md bg-canvas/60 p-2 text-[11px] text-muted-foreground">
        Disk space is unavailable, so readiness to build maps is unknown.
      </p>
    );
  }
  const where = free.source === "host" ? "on the Windows drive" : "on the server disk";
  const gb = Math.round(free.gb);
  if (free.level === "ok" && !hostKnown) {
    // Sehat menurut disk yang dilihat container, tapi disk itu bisa virtual: jangan menyatakan siap.
    return (
      <p className="rounded-md bg-canvas/60 p-2 text-[11px] text-muted-foreground">
        Server disk shows {gb} GB free. The physical drive is not reported, so readiness to build
        maps is not confirmed.
      </p>
    );
  }
  const text =
    free.level === "ok"
      ? `Ready to build maps: ${gb} GB free ${where}.`
      : free.level === "warn"
        ? `Disk is getting low: ${gb} GB free ${where}.`
        : free.source === "volume"
          ? `Map builds are refused: ${gb} GB free ${where}, the worker needs 20 GB.`
          : `Windows drive has ${gb} GB free; keep it above 30 GB before building.`;
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
}: {
  storage: StorageDiagnostics | undefined;
  host: HostDisk | null;
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
    lines.push(`That disk is larger than drive ${host.mount}, so not all of it can be used.`);
  }
  if (storage?.host?.stale) {
    lines.push(`Drive reading is ${formatAge(storage.host.age_s)} old and ignored.`);
  } else if (!storage?.host) {
    lines.push("Physical drive not reported: if this disk is virtual, real free space may be lower.");
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
          <span className="font-semibold text-foreground text-sm">System Diagnostics</span>
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide uppercase",
              data?.device === "cuda"
                ? "bg-forest/15 text-forest"
                : "bg-muted text-muted-foreground"
            )}
          >
            {data?.device ? `${data.device.toUpperCase()} Mode` : "Detecting"}
          </span>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-canvas hover:text-foreground transition-colors cursor-pointer"
            aria-label="Close diagnostics"
          >
            ✕
          </button>
        )}
      </div>

      {/* Notice jika ada refresh error tetapi data sebelumnya tetap tampil */}
      {refreshError && (
        <div className="rounded-md bg-bad-bg/60 p-2 text-[11px] text-bad-fg flex items-start gap-1.5">
          <span className="font-bold">!</span>
          <span>Refresh failed ({refreshError}). Showing last known metrics.</span>
        </div>
      )}

      {loading && !data ? (
        <div className="flex flex-col gap-2 py-4 items-center justify-center text-muted-foreground">
          <div className="skeleton h-4 w-3/4 rounded" />
          <div className="skeleton h-12 w-full rounded" />
          <div className="skeleton h-12 w-full rounded" />
          <span className="text-[11px] mt-1">Reading system sensors...</span>
        </div>
      ) : (
        <>
          {/* Bagian 1: kesiapan membangun peta dan pengukur */}
          <Verdict free={free} hostKnown={host !== null} />
          <div className="grid grid-cols-3 gap-1 py-1">
            {host ? (
              <Gauge
                label={`Drive ${host.mount}`}
                fill={host.percent}
                display={String(Math.round(host.free_gb))}
                unit="GB free"
                level={freeLevel(host.free_gb, "host")}
                caption={`${host.used_gb.toFixed(0)} of ${host.total_gb.toFixed(0)} GB used`}
              />
            ) : volume ? (
              <Gauge
                label="Server disk"
                fill={volume.percent}
                display={String(Math.round(volume.free_gb))}
                unit="GB free"
                level={freeLevel(volume.free_gb, "volume")}
                caption={`${volume.used_gb.toFixed(0)} of ${volume.total_gb.toFixed(0)} GB used`}
              />
            ) : (
              <Gauge label="Disk" fill={0} display="N/A" unit="unavailable" />
            )}
            <Gauge
              label="GPU memory"
              fill={vramPct ?? 0}
              display={vramPct !== null ? String(vramPct) : "N/A"}
              unit={vramPct !== null ? "% used" : "unavailable"}
              caption={
                gpu && gpu.vram_used_mb !== null && gpu.vram_total_mb
                  ? `${(gpu.vram_used_mb / 1024).toFixed(1)} of ${(gpu.vram_total_mb / 1024).toFixed(1)} GB`
                  : undefined
              }
            />
            <Gauge
              label="GPU temp"
              fill={gpu?.temperature_c ?? 0}
              display={gpu?.temperature_c != null ? String(gpu.temperature_c) : "N/A"}
              unit={gpu?.temperature_c != null ? "°C" : "unavailable"}
              level={gpu?.temperature_c != null ? (gpu.temperature_c >= 80 ? "bad" : "ok") : undefined}
            />
          </div>
          {gpu?.name && <p className="-mt-1 text-center text-[11px] text-muted-foreground">{gpu.name}</p>}
          <DiskNotes storage={storage} host={host} />

          {/* Bagian 3: System Status & Alignment */}
          <div className="flex flex-col gap-2 border-t border-border pt-2.5">
            <span className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">
              System Status
            </span>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="flex flex-col rounded-md bg-canvas/60 p-2">
                <span className="text-[11px] text-muted-foreground">Connection</span>
                <span className="font-semibold text-forest flex items-center gap-1.5 mt-0.5">
                  <span className="h-2 w-2 rounded-full bg-forest animate-pulse" />
                  Reachable
                </span>
              </div>
              <div className="flex flex-col rounded-md bg-canvas/60 p-2">
                <span className="text-[11px] text-muted-foreground">Service Uptime</span>
                <span className="font-semibold text-foreground num mt-0.5">
                  {data?.uptime_s !== undefined ? formatUptime(data.uptime_s) : "N/A"}
                </span>
              </div>
            </div>

            {/* Metric Alignment Row */}
            <div className="flex flex-col rounded-md bg-canvas/60 p-2 text-xs">
              <span className="text-[11px] text-muted-foreground">Active Map Coordinate Frame</span>
              <span className="font-semibold text-foreground flex items-center gap-1.5 mt-0.5">
                {healthData?.aligned ? (
                  <span className="text-forest flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-forest" />
                    Metric aligned (pose_building in meters)
                  </span>
                ) : healthData ? (
                  <span className="text-muted-foreground flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
                    Model coordinates only (unaligned SfM)
                  </span>
                ) : (
                  "Checking..."
                )}
              </span>
              <span className="text-[10px] text-muted-foreground mt-0.5 leading-snug">
                {healthData?.aligned
                  ? "Poses transformed to metric coordinates via align.json"
                  : "Poses output in unitless SfM space pending reference points"}
              </span>
            </div>

            {data?.reloading && (
              <div className="rounded-md bg-busy-bg p-2 text-[11px] text-busy-fg">
                Map reload is currently in progress...
              </div>
            )}
            {data?.reload_error && (
              <div className="rounded-md bg-bad-bg p-2 text-[11px] text-bad-fg">
                Reload error: {data.reload_error}
              </div>
            )}
          </div>

          {/* Footer Telemetry */}
          <div className="flex items-center justify-between border-t border-border/80 pt-2 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-forest" />
              Auto-refreshing (10s)
            </span>
            <span className="num">
              {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Updating..."}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
