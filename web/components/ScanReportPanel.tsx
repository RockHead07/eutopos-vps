"use client";

import { Panel } from "@/components/Panel";
import type { ScanReport } from "@/lib/api";
import { useFormatDate, useFormatNumber, useT, type TranslationKey } from "@/lib/i18n";

const KNOWN_REASONS = new Set([
  "not_recorded",
  "no_arcore",
  "cli_job",
  "video_deleted",
  "no_meta",
]);

function Item({
  label,
  value,
  note,
  warn,
}: {
  label: string;
  value: string;
  note?: string;
  warn?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium text-foreground num break-words">{value}</dd>
      {note && <span className="text-xs text-muted-foreground break-words">{note}</span>}
      {warn && (
        <span className="mt-0.5 inline-flex w-fit rounded-md bg-[var(--busy-bg)] px-2 py-0.5 text-xs font-medium text-[var(--busy-fg)]">
          {warn}
        </span>
      )}
    </div>
  );
}

export function ScanReportPanel({ report }: { report: ScanReport | null | undefined }) {
  const t = useT();
  const formatDate = useFormatDate();
  const fmt = useFormatNumber();

  function reasonText(reason?: string): string {
    if (!reason) return "";
    if (KNOWN_REASONS.has(reason)) {
      return t(`report.reason.${reason}` as TranslationKey);
    }
    return reason;
  }

  function missing(reason?: string): string {
    if (!reason || reason === "not_recorded") return t("report.notRecorded");
    return t("report.notRecordedWithReason", { reason: reasonText(reason) });
  }

  function formatSec(seconds: number): string {
    if (seconds >= 60) {
      const mins = Math.floor(seconds / 60);
      const rem = Math.round(seconds - mins * 60);
      return t("report.unitMinSec", { min: fmt(mins, 0), sec: fmt(rem, 0) });
    }
    const digits = seconds < 10 ? 1 : 0;
    return t("report.unitSec", { val: fmt(seconds, digits) });
  }

  if (!report) {
    return (
      <Panel className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-foreground">{t("report.title")}</h2>
        <p className="text-xs text-muted-foreground">{t("report.noReport")}</p>
      </Panel>
    );
  }

  if (report.error) {
    return (
      <Panel className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
          <h2 className="text-sm font-semibold text-foreground">{t("report.title")}</h2>
          <span className="text-xs text-muted-foreground font-mono">
            {t("report.versionOnly", { version: report.version })}
          </span>
        </div>
        <p className="error">{t("report.errorCard", { error: report.error })}</p>
      </Panel>
    );
  }

  const rec = report.recording;
  const net = report.network;
  const proc = report.processing;
  const qual = report.quality;

  const sourceValue =
    rec?.source === "arcore"
      ? t("report.source.arcore")
      : rec?.source === "video"
        ? t("report.source.video")
        : missing();

  const photosValue =
    rec?.map_photos != null
      ? rec.query_photos != null
        ? t("report.photosWithQuery", {
            map: fmt(rec.map_photos, 0),
            query: fmt(rec.query_photos, 0),
          })
        : t("report.photosValue", { map: fmt(rec.map_photos, 0) })
      : missing();

  const footprintNote = rec?.footprint
    ? t("report.footprintFormula", {
        method: rec.footprint.method,
        radius: fmt(rec.footprint.radius_m, 1),
        cell: fmt(rec.footprint.cell_m, 2),
        frame:
          rec.footprint.frame === "aligned_sfm"
            ? t("report.frame.aligned_sfm")
            : t("report.frame.arcore_per_segment"),
      })
    : undefined;

  const stageSummary =
    proc?.stage_seconds && Object.keys(proc.stage_seconds).length > 0
      ? Object.entries(proc.stage_seconds)
          .map(([k, v]) => `${k} ${formatSec(v)}`)
          .join(", ")
      : null;

  const envParts: string[] = [];
  if (proc?.env && typeof proc.env === "object") {
    // Kunci mengikuti spike/env_info.py env(), sumber tunggal lingkungan di summary.run.env.
    const labels: Record<string, string> = {
      cuda_device: "",
      cpu: "",
      eutopos_commit: "commit ",
      pycolmap: "pycolmap ",
      hloc: "hloc ",
    };
    for (const [key, prefix] of Object.entries(labels)) {
      const val = proc.env[key];
      if (typeof val === "string" && val.trim()) {
        envParts.push(prefix + (key === "eutopos_commit" ? val.slice(0, 7) : val));
      }
    }
  }

  const paramParts: string[] = [];
  if (qual?.params && typeof qual.params === "object") {
    for (const [k, v] of Object.entries(qual.params)) {
      if (v !== null && v !== undefined) {
        paramParts.push(`${k}=${String(v)}`);
      }
    }
  }

  return (
    <Panel className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
        <h2 className="text-sm font-semibold text-foreground">{t("report.title")}</h2>
        <span className="text-xs text-muted-foreground">
          {report.computed_at
            ? t("report.versionMeta", {
                version: report.version,
                date: formatDate(report.computed_at),
              })
            : t("report.versionOnly", { version: report.version })}
        </span>
      </div>

      {/* 1. Rekaman */}
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t("report.groupRecording")}
        </h3>
        {rec?.error ? (
          <p className="error">{t("report.sectionError", { error: rec.error })}</p>
        ) : (
          <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <Item label={t("report.source")} value={sourceValue} />
            <Item label={t("report.photos")} value={photosValue} />
            <Item
              label={t("report.segments")}
              value={rec?.segments != null ? fmt(rec.segments, 0) : missing(rec?.segments_reason)}
            />
            <Item
              label={t("report.duration")}
              value={
                rec?.duration_s != null ? formatSec(rec.duration_s) : missing(rec?.duration_s_reason)
              }
            />
            <Item
              label={t("report.pathLength")}
              value={
                rec?.path_length_m != null
                  ? t("report.unitM", { val: fmt(rec.path_length_m, 1) })
                  : missing(rec?.path_length_m_reason)
              }
            />
            <Item
              label={t("report.footprint")}
              value={
                rec?.footprint_m2 != null
                  ? t("report.unitM2", { val: fmt(rec.footprint_m2, 1) })
                  : missing(rec?.footprint_m2_reason)
              }
              note={footprintNote}
              warn={rec?.footprint_upper_bound ? t("report.footprintUpperBound") : undefined}
            />
            <Item
              label={t("report.meanSpeed")}
              value={
                rec?.mean_speed_m_s != null
                  ? t("report.unitMS", { val: fmt(rec.mean_speed_m_s, 2) })
                  : missing(rec?.mean_speed_m_s_reason)
              }
            />
            <Item
              label={t("report.heightRange")}
              value={
                rec?.height_range_m != null
                  ? t("report.unitM", { val: fmt(rec.height_range_m, 2) })
                  : missing(rec?.height_range_m_reason)
              }
              warn={
                rec?.warnings?.includes("multi_floor") ? t("report.multiFloorWarning") : undefined
              }
            />
            <Item
              label={t("report.trackingLosses")}
              value={
                rec?.tracking_losses != null
                  ? t("report.unitCount", { val: fmt(rec.tracking_losses, 0) })
                  : missing(rec?.tracking_losses_reason)
              }
            />
            <Item
              label={t("report.deviceModel")}
              value={rec?.device_model ? rec.device_model : missing(rec?.device_model_reason)}
            />
          </dl>
        )}
      </section>

      {/* 2. Jaringan */}
      <section className="flex flex-col gap-2 border-t border-line/70 pt-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t("report.groupNetwork")}
        </h3>
        {net?.error ? (
          <p className="error">{t("report.sectionError", { error: net.error })}</p>
        ) : net?.uploads == null || net.total_bytes == null || net.seconds == null ? (
          <p className="text-sm text-muted-foreground">{missing(net?.uploads_reason)}</p>
        ) : (
          <dl className="grid grid-cols-1 gap-2">
            <Item
              label={t("report.uploadSummary")}
              value={t("report.uploadSummaryValue", {
                mb: fmt(net.total_bytes / 1e6, 1), // desimal, sama dengan Mbps
                time: formatSec(net.seconds),
                mbps: net.mbps != null ? fmt(net.mbps, 1) : "-",
              })}
              note={t("report.uploadNote")}
            />
          </dl>
        )}
      </section>

      {/* 3. Proses */}
      <section className="flex flex-col gap-2 border-t border-line/70 pt-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t("report.groupProcessing")}
        </h3>
        {proc?.error ? (
          <p className="error">{t("report.sectionError", { error: proc.error })}</p>
        ) : (
          <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <Item
              label={t("report.queueTime")}
              value={proc?.queue_s != null ? formatSec(proc.queue_s) : missing(proc?.queue_s_reason)}
            />
            <Item
              label={t("report.gpuWait")}
              value={
                proc?.gpu_wait_s != null
                  ? formatSec(proc.gpu_wait_s)
                  : missing(proc?.gpu_wait_s_reason)
              }
            />
            <Item
              label={t("report.totalProcessing")}
              value={proc?.total_s != null ? formatSec(proc.total_s) : missing(proc?.total_s_reason)}
            />
            <Item
              label={t("report.environment")}
              value={envParts.length > 0 ? envParts.join(", ") : missing()}
            />
            <div className="sm:col-span-2 lg:col-span-4">
              <Item
                label={t("report.stageSeconds")}
                value={stageSummary ?? missing(proc?.stage_seconds_reason)}
              />
            </div>
          </dl>
        )}
      </section>

      {/* 4. Kualitas peta */}
      <section className="flex flex-col gap-2 border-t border-line/70 pt-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t("report.groupQuality")}
        </h3>
        {qual?.error ? (
          <p className="error">{t("report.sectionError", { error: qual.error })}</p>
        ) : (
          <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <Item
              label={t("report.points3d")}
              value={qual?.points3d != null ? fmt(qual.points3d, 0) : missing()}
            />
            <Item
              label={t("report.reprojectionError")}
              value={
                qual?.mean_reprojection_error_px != null
                  ? t("report.unitPx", { val: fmt(qual.mean_reprojection_error_px, 2) })
                  : missing()
              }
            />
            <Item
              label={t("report.trackLength")}
              value={qual?.mean_track_length != null ? fmt(qual.mean_track_length, 2) : missing()}
            />
            <Item
              label={t("report.obsPerImage")}
              value={
                qual?.mean_observations_per_image != null
                  ? fmt(qual.mean_observations_per_image, 1)
                  : missing()
              }
            />
            {qual?.gate && (
              <Item label={t("report.gate")} value={qual.gate.decision} />
            )}
            {paramParts.length > 0 && (
              <div className="sm:col-span-2 lg:col-span-3">
                <Item label={t("report.params")} value={paramParts.join(", ")} />
              </div>
            )}
          </dl>
        )}
      </section>
    </Panel>
  );
}
