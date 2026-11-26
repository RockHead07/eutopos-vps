"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/Panel";
import { api, type Usage, type UsageGroup } from "@/lib/api";
import { useFormatDate, useFormatNumber, useT } from "@/lib/i18n";

function UsageRow({ label, group }: { label: string; group: UsageGroup }) {
  const t = useT();
  const fmt = useFormatNumber();
  const formatDate = useFormatDate();

  if (group.requests === 0) {
    return (
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1 border-b border-line/60 pb-2 last:border-0 last:pb-0">
        <span className="text-xs font-semibold text-foreground">{label}</span>
        <span className="text-xs text-muted-foreground">{t("usage.noRequests")}</span>
      </div>
    );
  }

  const parts = [t("usage.requests", { count: fmt(group.requests, 0) })];
  if (group.ok_ratio != null) {
    parts.push(t("usage.okRatio", { pct: fmt(group.ok_ratio * 100, 0) }));
  }
  if (group.wall_s_p50 != null) {
    parts.push(t("usage.p50", { val: fmt(group.wall_s_p50, 2) }));
  }
  if (group.wall_s_p95 != null) {
    parts.push(t("usage.p95", { val: fmt(group.wall_s_p95, 2) }));
  }
  if (group.inliers_median != null) {
    parts.push(t("usage.inliersMedian", { val: fmt(group.inliers_median, 0) }));
  }

  return (
    <div className="flex flex-col gap-0.5 border-b border-line/60 pb-2 last:border-0 last:pb-0">
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
        <span className="text-xs font-semibold text-foreground">{label}</span>
        <span className="text-sm font-medium text-foreground num break-words">
          {parts.join(" | ")}
        </span>
      </div>
      {group.first_at && group.last_at && (
        <span className="text-xs text-muted-foreground sm:text-right">
          {t("usage.range", {
            first: formatDate(group.first_at),
            last: formatDate(group.last_at),
          })}
        </span>
      )}
    </div>
  );
}

export function MapUsagePanel({ jobId }: { jobId: number }) {
  const t = useT();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setUsage(null);
    setError(null);
    api
      .jobUsage(jobId)
      .then((data) => {
        if (!cancelled) setUsage(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  return (
    <Panel className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="text-sm font-semibold text-foreground">{t("usage.title")}</h2>
          {usage?.map_version != null && (
            <span className="text-xs text-muted-foreground font-mono">
              {t("usage.versionTag", { version: usage.map_version })}
            </span>
          )}
        </div>
        <span className="text-xs text-muted-foreground">{t("usage.liveNote")}</span>
      </div>
      {error && <p className="error">{error}</p>}
      {!error && !usage && <span className="skeleton row" />}
      {usage && (
        <div className="flex flex-col gap-2">
          <UsageRow label={t("usage.served")} group={usage.served} />
          <UsageRow label={t("usage.candidate")} group={usage.candidate} />
        </div>
      )}
    </Panel>
  );
}
