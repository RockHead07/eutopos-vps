"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/StatusBadge";
import { PipelineStageIndicator } from "@/components/PipelineStageIndicator";
import { JobFailureDiagnosis } from "@/components/JobFailureDiagnosis";
import { DeleteConsentDialog } from "@/components/DeleteConsentDialog";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { api, formatDuration, formatRelativeTime, mb, ROLE } from "@/lib/api";
import { PageHead } from "@/lib/PageHead";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";
import { useFormatDate, useT } from "@/lib/i18n";

function Stat({ label, value, of, note }: { label: string; value?: number; of?: number; note?: string }) {
  const pct = value !== undefined && of ? Math.round((value / of) * 100) : null;
  return (
    <Panel>
      <span className="stat-label">{label}</span>
      <span className="stat-value">
        {value ?? "-"}
        {of !== undefined && <small> / {of}</small>}
      </span>
      {pct !== null && (
        <div className="meter" role="img" aria-label={`${pct}%`}>
          <span style={{ width: `${pct}%` }} />
        </div>
      )}
      {note && <span className="muted">{note}</span>}
    </Panel>
  );
}

function JobDetail() {
  const t = useT();
  const formatDate = useFormatDate();
  const router = useRouter();
  const id = Number(useSearchParams().get("id"));
  const { data: job, error } = usePoll(() => api.job(id), 5000, [id]);
  const { data: me } = usePoll(api.me, 60000);
  const [message, setMessage] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Update clock every second while viewing a running or uploading job so elapsed duration and relative time stay fresh
  useEffect(() => {
    if (job?.status === "running" || job?.status === "uploading") {
      const interval = setInterval(() => setNow(Date.now()), 1000);
      return () => clearInterval(interval);
    }
  }, [job?.status]);

  async function handleDelete() {
    if (!job) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteJob(job.id);
      setDeleteDialogOpen(false);
      router.push("/jobs/");
    } catch (e) {
      setDeleteError((e as Error).message);
    } finally {
      setIsDeleting(false);
    }
  }

  async function publish(versionId: number) {
    if (!window.confirm(t("job.publishConfirm"))) return;
    try {
      const r = await api.publish(versionId);
      setMessage(
        r.reload === "started"
          ? t("job.publishLoadingNotice", { version: r.version.version })
          : t("job.publishOtherAreaNotice", { version: r.version.version }),
      );
    } catch (e) {
      setMessage((e as Error).message);
    }
  }

  if (!id) return <p className="error">{t("job.missingId")}</p>;
  if (!job) return error ? <p className="error">{error}</p> : <Loading />;

  const run = job.summary?.run;
  const ins = job.summary?.inspect;
  const isRunning = job.status === "running";
  const durationStr = formatDuration(job.started_at, job.finished_at, {
    isRunning,
    nowMs: now,
  });

  return (
    <>
      {error && <p className="error">{error}</p>}
      <PageHead
        crumbs={[{ label: t("nav.jobs"), href: "/jobs/" }, { label: t("job.crumbJob", { id: job.id }) }]}
        title={t("job.titleJob", { id: job.id, area: job.area_id })}
      >
        <div className="flex flex-wrap items-center gap-2 mt-1 text-xs">
          <StatusBadge status={job.status} />
          {job.stalled && <StatusBadge status="stalled" />}
          {job.stage && job.status !== "done" && (
            <span className="text-muted-foreground">
              {t("job.stage", { stage: job.stage })}
            </span>
          )}
          <span className="text-muted-foreground">· {t("job.createdBy", { name: job.created_by })}</span>
        </div>
      </PageHead>

      {/* Stalled upload warning and delete action */}
      {job.status === "uploading" && job.stalled && (
        <Panel className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border border-[var(--bad-fg)]/30 bg-[var(--bad-bg)]">
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <StatusBadge status="stalled" />
              <span className="font-semibold text-[var(--bad-fg)] text-sm">{t("job.uploadStalled")}</span>
            </div>
            <p className="text-xs text-muted-foreground">
              {t("job.uploadStalledDesc")}
            </p>
          </div>
          {me?.is_admin && (
            <Button
              variant="destructive"
              size="sm"
              className="rounded-full cursor-pointer shrink-0"
              onClick={() => setDeleteDialogOpen(true)}
            >
              {t("job.deleteStalled")}
            </Button>
          )}
        </Panel>
      )}

      {/* Execution Status Card */}
      <Panel className="flex flex-col gap-3">
        <div className="flex items-center justify-between border-b border-line pb-2">
          <h2 className="text-sm font-semibold text-foreground">{t("job.executionStatus")}</h2>
          <span className="text-xs text-muted-foreground font-mono">{t("job.jobId", { id: job.id })}</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground">{t("job.uploadedCreated")}</span>
            <span className="font-medium text-foreground whitespace-nowrap">
              {formatDate(job.created_at)}
            </span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground">{t("job.executionStarted")}</span>
            <span className="font-medium text-foreground whitespace-nowrap">
              {job.started_at ? formatDate(job.started_at) : t("jobs.pendingStart")}
            </span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground">{t("job.executionFinished")}</span>
            <span className="font-medium text-foreground whitespace-nowrap">
              {job.finished_at ? formatDate(job.finished_at) : isRunning ? t("job.inProgress") : "-"}
            </span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground">{t("job.processingDuration")}</span>
            <span className="font-medium text-foreground font-mono">
              {durationStr}
              {isRunning && (
                <span className="ml-1.5 inline-block size-2 rounded-full bg-forest animate-pulse" />
              )}
            </span>
          </div>
        </div>
      </Panel>

      {/* Pipeline Stage Indicator */}
      <PipelineStageIndicator
        status={job.status}
        currentStage={job.stage}
        timings={run?.t_map_s}
      />

      {/* Failure Diagnosis Panel */}
      {job.error && (
        <JobFailureDiagnosis error={job.error} stage={job.stage} />
      )}

      {/* Reconstruction Results */}
      {run && ins && (
        <section className="stats">
          <Stat
            label={t("jobs.registeredFrames")}
            value={run.map_registered}
            of={run.map_images}
            note={t("job.statCoverageNote")}
          />
          <Stat
            label={t("jobs.mapPieces")}
            value={ins.parts?.length ?? 0}
            note={(ins.parts?.length ?? 0) === 1 ? t("job.oneConnectedMap") : t("job.splitMapNote")}
          />
          <Stat
            label={t("jobs.testPhotosAccepted")}
            value={ins.accepted}
            of={ins.queries || undefined}
            note={
              ins.queries
                ? t("job.testPhotosNote", { min: ins.min_inliers ?? 0 })
                : t("jobs.noTestVideo")
            }
          />
        </section>
      )}

      {/* Videos List */}
      <Panel>
        <h2>{t("job.videos")}</h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("job.thName")}</TableHead>
              <TableHead>{t("job.thRole")}</TableHead>
              <TableHead>{t("job.thSize")}</TableHead>
              <TableHead>{t("jobs.colRecorded")}</TableHead>
              <TableHead>{t("job.thUpload")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {job.videos.map((v) => {
              let uploadContent: React.ReactNode;
              if (v.uploaded) {
                uploadContent = t("job.uploaded");
              } else if (v.received != null && v.activity_at) {
                const pct = v.size ? Math.round((v.received / v.size) * 100) : null;
                uploadContent = (
                  <div className="flex flex-col gap-0.5">
                    <span>
                      {mb(v.received)} / {v.size === null ? "-" : mb(v.size)}
                      {pct !== null ? ` (${pct}%)` : ""}
                    </span>
                    <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                      {t("job.lastDataAgo", { time: formatRelativeTime(v.activity_at, now) })}
                    </span>
                  </div>
                );
              } else {
                uploadContent = t("job.noProgressData");
              }

              return (
                <TableRow key={v.name}>
                  <TableCell className="font-medium">{v.name}</TableCell>
                  <TableCell>{ROLE[v.role] ?? v.role}</TableCell>
                  <TableCell className="num">{v.size === null ? "-" : mb(v.size)}</TableCell>
                  <TableCell className="text-muted-foreground whitespace-nowrap">
                    {v.recorded_at ? formatDate(v.recorded_at) : "-"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {uploadContent}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Panel>

      {/* 3D Map View and Actions */}
      {job.map_version_id && (
        <Panel>
          <div className="actions">
            <h2><Icon name="view-3d" /> {t("job.view3D")}</h2>
            <span className="muted">{t("job.view3DDesc")}</span>
          </div>
          <iframe src={`/api/versions/${job.map_version_id}/report`} title={t("job.iframe3DTitle")} />
          <div className="actions">
            <Button className="rounded-full cursor-pointer" onClick={() => publish(job.map_version_id!)}>
              <Icon name="publish" />{t("job.publishVersion")}
            </Button>
            <Link href="/maps/">{t("nav.mapVersions")}</Link>
          </div>
          {message && <p className="notice">{message}</p>}
        </Panel>
      )}

      {job.status === "uploading" && job.stalled && (
        <DeleteConsentDialog
          target={{ type: "job", id: job.id, area_id: job.area_id }}
          open={deleteDialogOpen}
          onOpenChange={setDeleteDialogOpen}
          onConfirm={handleDelete}
          isDeleting={isDeleting}
          error={deleteError}
        />
      )}
    </>
  );
}

function Loading() {
  return (
    <>
      <div className="page-head"><span className="skeleton row" /></div>
      <section className="stats">
        <div className="skeleton block" />
        <div className="skeleton block" />
        <div className="skeleton block" />
      </section>
      <Panel><Rows /></Panel>
    </>
  );
}

export default function JobPage() {
  // useSearchParams wajib di dalam Suspense pada static export (tanpa ini next build gagal).
  return (
    <Suspense fallback={<Loading />}>
      <JobDetail />
    </Suspense>
  );
}
