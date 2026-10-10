"use client";

import { useEffect, useRef, useState } from "react";
import { api, type SystemDiagnostics, type StorageLocation } from "@/lib/api";
import { cn } from "@/lib/utils";

interface SystemDiagnosticsPopoverProps {
  isOpen: boolean;
  onClose?: () => void;
}

export function useDiagnostics(isOpen: boolean) {
  const [data, setData] = useState<SystemDiagnostics | null>(null);
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
        const res = await api.system();
        if (!active) return;
        setData(res);
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

  return { data, loading: initialLoading, refreshError, lastUpdated };
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

function StorageMeter({
  name,
  mountPath,
  loc,
}: {
  name: string;
  mountPath: string;
  loc: StorageLocation | null;
}) {
  if (!loc) {
    return (
      <div className="flex flex-col gap-1 rounded-md bg-canvas/70 p-2.5 text-xs">
        <div className="flex items-center justify-between font-medium">
          <span className="text-foreground">{name}</span>
          <span className="text-muted-foreground font-mono">{mountPath}</span>
        </div>
        <div className="text-muted-foreground italic">Storage location unavailable</div>
      </div>
    );
  }

  const isCritical = loc.percent >= 95;
  const isWarning = loc.percent >= 85 && !isCritical;

  const barColor = isCritical
    ? "bg-bad-fg"
    : isWarning
      ? "bg-amber-600"
      : "bg-forest";

  return (
    <div className="flex flex-col gap-1.5 rounded-md bg-canvas/60 p-2.5 text-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="font-medium text-foreground">{name}</span>
          <span className="font-mono text-[11px] text-muted-foreground">({mountPath})</span>
        </div>
        <span
          className={cn(
            "font-semibold num",
            isCritical ? "text-bad-fg" : isWarning ? "text-amber-700" : "text-foreground"
          )}
        >
          {loc.percent}% used
        </span>
      </div>

      <div
        className="meter w-full bg-line"
        role="progressbar"
        aria-label={`${name} storage usage`}
        aria-valuenow={loc.percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <span
          className={cn("h-full transition-all duration-300", barColor)}
          style={{ width: `${Math.min(100, Math.max(0, loc.percent))}%` }}
        />
      </div>

      <div className="flex items-center justify-between text-[11px] text-muted-foreground num">
        <span>
          {loc.used_gb.toFixed(1)} GB of {loc.total_gb.toFixed(1)} GB
        </span>
        <span>{loc.free_gb.toFixed(1)} GB free</span>
      </div>
    </div>
  );
}

export function SystemDiagnosticsPopover({
  isOpen,
  onClose,
}: SystemDiagnosticsPopoverProps) {
  const { data, loading, refreshError, lastUpdated } = useDiagnostics(isOpen);

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
          {/* Bagian 1: Storage */}
          <div className="flex flex-col gap-2">
            <span className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">
              Storage Locations
            </span>
            <div className="flex flex-col gap-2">
              <StorageMeter
                name="Maps Storage"
                mountPath="/maps"
                loc={data?.storage?.maps ?? null}
              />
              <StorageMeter
                name="Application Data"
                mountPath="/data"
                loc={data?.storage?.data ?? null}
              />
            </div>
          </div>

          {/* Bagian 2: Compute / GPU */}
          <div className="flex flex-col gap-2 border-t border-border pt-2.5">
            <span className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">
              Compute & GPU
            </span>

            {data?.gpu ? (
              <div className="flex flex-col gap-2 rounded-md bg-canvas/60 p-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-foreground truncate max-w-[200px]" title={data.gpu.name ?? "GPU"}>
                    {data.gpu.name ?? "Discrete GPU"}
                  </span>
                  <span className="text-muted-foreground num font-medium">
                    Temp:{" "}
                    {data.gpu.temperature_c !== null ? (
                      <span className={cn(data.gpu.temperature_c >= 80 ? "text-bad-fg font-semibold" : "text-foreground")}>
                        {data.gpu.temperature_c} °C
                      </span>
                    ) : (
                      "N/A"
                    )}
                  </span>
                </div>

                {data.gpu.vram_total_mb !== null && data.gpu.vram_used_mb !== null ? (
                  <div className="flex flex-col gap-1 mt-0.5">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-muted-foreground">VRAM Usage</span>
                      <span className="num font-semibold text-foreground">
                        {Math.round((data.gpu.vram_used_mb / data.gpu.vram_total_mb) * 100)}%
                      </span>
                    </div>
                    <div
                      className="meter w-full bg-line"
                      role="progressbar"
                      aria-label="GPU VRAM usage"
                      aria-valuenow={Math.round((data.gpu.vram_used_mb / data.gpu.vram_total_mb) * 100)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                    >
                      <span
                        className="h-full bg-forest transition-all duration-300"
                        style={{
                          width: `${Math.min(100, Math.max(0, Math.round((data.gpu.vram_used_mb / data.gpu.vram_total_mb) * 100)))}%`,
                        }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground num">
                      <span>{(data.gpu.vram_used_mb / 1024).toFixed(1)} GB used</span>
                      <span>{(data.gpu.vram_total_mb / 1024).toFixed(1)} GB total</span>
                    </div>
                  </div>
                ) : (
                  <div className="text-[11px] text-muted-foreground italic">
                    VRAM memory metrics unavailable
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-between rounded-md bg-canvas/60 p-2.5 text-xs text-muted-foreground">
                <span>GPU telemetry unavailable</span>
                <span className="font-medium text-foreground">
                  {data?.device === "cpu" ? "CPU Mode" : "No sensor"}
                </span>
              </div>
            )}
          </div>

          {/* Bagian 3: System Status */}
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
