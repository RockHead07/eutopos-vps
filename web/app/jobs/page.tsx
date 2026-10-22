"use client";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { MoreHorizontal } from "lucide-react";
import { Panel } from "@/components/Panel";
import { SortableHead, type SortDirection } from "@/components/SortableHead";
import { StatusBadge } from "@/components/StatusBadge";
import { TableFilterBar } from "@/components/TableFilterBar";
import { DeleteConsentDialog } from "@/components/DeleteConsentDialog";
import { JobFailureDiagnosis } from "@/components/JobFailureDiagnosis";
import { Thumbnail } from "@/components/Thumbnail";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { api, formatDuration, mb, ROLE, type Job } from "@/lib/api";
import { PageHead } from "@/lib/PageHead";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";
import { useFormatDate, useT, type TranslationKey } from "@/lib/i18n";

function compareWithNullLast(
  valA: string | null | undefined,
  valB: string | null | undefined,
  dir: SortDirection
): number {
  const emptyA = !valA || valA === "-";
  const emptyB = !valB || valB === "-";
  if (emptyA && emptyB) return 0;
  if (emptyA) return 1;
  if (emptyB) return -1;
  const cmp = valA.localeCompare(valB);
  return dir === "asc" ? cmp : -cmp;
}

function JobsContent() {
  const t = useT();
  const formatDate = useFormatDate();
  const searchParams = useSearchParams();
  const [tick, setTick] = useState(0);
  const { data: fetchedJobs, error } = usePoll(api.jobs, 5000, [tick]);
  const [jobs, setJobs] = useState<Job[] | null>(null);

  useEffect(() => {
    if (fetchedJobs) setJobs(fetchedJobs);
  }, [fetchedJobs]);

  const { data: me } = usePoll(api.me, 60000);

  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [jobToDelete, setJobToDelete] = useState<Job | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const lastActionTriggerRef = useRef<HTMLButtonElement | null>(null);
  const actionButtonRefs = useRef<Record<number, HTMLButtonElement | null>>({});

  const [search, setSearch] = useState("");

  useEffect(() => {
    const q = searchParams.get("q");
    if (q) {
      setSearch(q);
    }
  }, [searchParams]);

  const [statusFilter, setStatusFilter] = useState("all");
  const [areaFilter, setAreaFilter] = useState("all");
  const [sortKey, setSortKey] = useState<string | null>("id");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");

  const statusOptions = useMemo(
    () => [
      { value: "done", label: t("status.done") },
      { value: "uploading", label: t("status.uploading") },
      { value: "running", label: t("status.running") },
      { value: "queued", label: t("status.queued") },
      { value: "failed", label: t("status.failed") },
      { value: "deleting", label: t("status.deleting") },
    ],
    [t]
  );

  const areaOptions = useMemo(() => {
    if (!jobs) return [];
    return Array.from(new Set(jobs.map((j) => j.area_id))).sort();
  }, [jobs]);

  const handleSort = (col: string) => {
    if (sortKey !== col) {
      setSortKey(col);
      setSortDir("asc");
    } else if (sortDir === "asc") {
      setSortDir("desc");
    } else {
      setSortKey(null);
    }
  };

  const handleReset = () => {
    setSearch("");
    setStatusFilter("all");
    setAreaFilter("all");
    setSortKey("id");
    setSortDir("desc");
  };

  async function handleConfirmDelete() {
    if (!jobToDelete) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteJob(jobToDelete.id);
      const deletedId = jobToDelete.id;
      setJobToDelete(null);
      setIsDeleting(false);
      setJobs((prev) =>
        prev ? prev.map((j) => (j.id === deletedId ? { ...j, status: "deleting" } : j)) : null
      );
      setTick((t) => t + 1);
    } catch (e) {
      setIsDeleting(false);
      setDeleteError((e as Error).message);
    }
  }

  const filteredAndSortedJobs = useMemo(() => {
    if (!jobs) return [];
    const q = search.trim().toLowerCase();
    const filtered = jobs.filter((j) => {
      if (statusFilter !== "all" && j.status !== statusFilter) return false;
      if (areaFilter !== "all" && j.area_id !== areaFilter) return false;
      if (q) {
        const matchId = j.id.toString().includes(q);
        const matchArea = j.area_id.toLowerCase().includes(q);
        const statusLabel = t(`status.${j.status}` as TranslationKey).toLowerCase();
        const matchStatus = j.status.toLowerCase().includes(q) || statusLabel.includes(q);
        const matchBy = j.created_by.toLowerCase().includes(q);
        return matchId || matchArea || matchStatus || matchBy;
      }
      return true;
    });

    if (!sortKey) return filtered;

    return filtered.slice().sort((a, b) => {
      let cmp = 0;
      if (sortKey === "id") cmp = a.id - b.id;
      else if (sortKey === "area_id") cmp = a.area_id.localeCompare(b.area_id);
      else if (sortKey === "status") cmp = a.status.localeCompare(b.status);
      else if (sortKey === "created_by") cmp = a.created_by.localeCompare(b.created_by);
      else if (sortKey === "recorded_at") {
        const recA = a.videos?.find((v) => v.role === "peta" && v.recorded_at)?.recorded_at ?? null;
        const recB = b.videos?.find((v) => v.role === "peta" && v.recorded_at)?.recorded_at ?? null;
        return compareWithNullLast(recA, recB, sortDir);
      } else if (sortKey === "created_at") {
        return compareWithNullLast(a.created_at, b.created_at, sortDir);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [jobs, search, statusFilter, areaFilter, sortKey, sortDir]);

  return (
    <>
      <PageHead crumbs={[{ label: t("nav.jobs") }]} title={t("jobs.pageTitle")}>
        {t("jobs.pageDesc")}
      </PageHead>
      {error && <p className="error">{error}</p>}
      <Panel>
        {!jobs && !error && <Rows />}
        {jobs && jobs.length === 0 && (
          <div className="empty">
            <p>{t("jobs.empty")}</p>
            <Link href="/new/">{t("jobs.startNewSession")}</Link>
          </div>
        )}
        {jobs && jobs.length > 0 && (
          <>
            <TableFilterBar
              search={search}
              onSearchChange={setSearch}
              searchPlaceholder={t("jobs.searchPlaceholder")}
              statusFilter={statusFilter}
              onStatusChange={setStatusFilter}
              statusOptions={statusOptions}
              areaFilter={areaFilter}
              onAreaChange={setAreaFilter}
              areaOptions={areaOptions}
              totalCount={jobs.length}
              filteredCount={filteredAndSortedJobs.length}
              onReset={handleReset}
            />
            {filteredAndSortedJobs.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground">
                <p>{t("jobs.noMatch")}</p>
                <Button variant="link" size="sm" onClick={handleReset} className="text-xs text-forest mt-1">
                  {t("jobs.clearFilters")}
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16 max-sm:hidden"><span className="sr-only">{t("table.previewSr")}</span></TableHead>
                    <SortableHead column="id" label={t("jobs.colId")} activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <SortableHead column="area_id" label={t("jobs.colArea")} activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <SortableHead column="status" label={t("jobs.colStatus")} activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <TableHead className="text-left max-[959px]:hidden">{t("jobs.colStage")}</TableHead>
                    <SortableHead column="created_by" label={t("jobs.colBy")} activeKey={sortKey} direction={sortDir} onSort={handleSort} className="max-[959px]:hidden" />
                    <SortableHead column="recorded_at" label={t("jobs.colRecorded")} activeKey={sortKey} direction={sortDir} onSort={handleSort} className="max-[959px]:hidden" />
                    <SortableHead column="created_at" label={t("jobs.colUploaded")} activeKey={sortKey} direction={sortDir} onSort={handleSort} className="max-[959px]:hidden" />
                    <TableHead className="text-left max-[959px]:hidden">{t("jobs.colDuration")}</TableHead>
                    <TableHead className="text-left sticky right-12 bg-card border-l border-line/70 z-20 max-sm:hidden">{t("jobs.colAction")}</TableHead>
                    <TableHead className="w-12 min-w-12 text-right sticky right-0 bg-card z-20"><span className="sr-only">{t("table.actionsSr")}</span></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredAndSortedJobs.map((j) => {
                    const isDeletingStatus = j.status === "deleting";
                    const canDelete = j.status === "done" || j.status === "failed" || (j.status === "uploading" && j.stalled);
                    const isDeleteDisabled = isDeletingStatus || !canDelete;
                    const deleteDisabledReason = isDeletingStatus
                      ? t("jobs.reasonDeleting")
                      : j.status === "uploading"
                        ? t("jobs.reasonReceiving")
                        : t("jobs.reasonCannotDelete");
                    const petaVideo = j.videos?.find((v) => v.role === "peta" && v.recorded_at);
                    const recordedAt = petaVideo?.recorded_at ?? null;

                    return (
                      <TableRow key={j.id} className="group">
                        <TableCell className="w-16 p-2 max-sm:hidden">
                          <Thumbnail
                            jobId={j.id}
                            hasPreview={j.has_preview}
                            alt={t("jobs.previewAltJob", { id: j.id })}
                            onClick={() => setSelectedJob(j)}
                          />
                        </TableCell>
                        <TableCell className="text-left"><Link href={`/job/?id=${j.id}`}>{j.id}</Link></TableCell>
                        <TableCell className="text-left max-sm:whitespace-normal max-sm:break-words">{j.area_id}</TableCell>
                        <TableCell className="text-left">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <StatusBadge status={j.status} />
                            {j.stalled && <StatusBadge status="stalled" />}
                          </div>
                        </TableCell>
                        <TableCell className="text-left text-muted-foreground max-[959px]:hidden">
                          {j.status === "running" ? (
                            <span className="inline-flex items-center gap-1.5 rounded-full bg-forest/15 px-2 py-0.5 text-[11px] font-medium text-forest whitespace-nowrap">
                              <span className="size-1.5 rounded-full bg-forest animate-pulse" />
                              {j.stage ?? "running"}
                            </span>
                          ) : j.status === "failed" && j.stage ? (
                            <span className="inline-flex items-center rounded bg-bad-bg/60 px-1.5 py-0.5 text-[11px] font-mono text-bad-fg whitespace-nowrap">
                              {t("jobs.failedAt", { stage: j.stage })}
                            </span>
                          ) : j.status === "done" ? (
                            <span className="text-muted-foreground">-</span>
                          ) : (
                            <span className="text-muted-foreground">{j.stage ?? "-"}</span>
                          )}
                        </TableCell>
                        <TableCell className="text-left text-muted-foreground max-[959px]:hidden">{j.created_by}</TableCell>
                        <TableCell className="text-left text-muted-foreground whitespace-nowrap max-[959px]:hidden" title={recordedAt || undefined}>
                          {formatDate(recordedAt)}
                        </TableCell>
                        <TableCell className="text-left text-muted-foreground whitespace-nowrap max-[959px]:hidden" title={j.created_at || undefined}>
                          {formatDate(j.created_at)}
                        </TableCell>
                        <TableCell className="text-left text-muted-foreground whitespace-nowrap font-mono text-xs max-[959px]:hidden">
                          {formatDuration(j.started_at, j.finished_at, { isRunning: j.status === "running" })}
                          {j.status === "running" && (
                            <span className="ml-1 inline-block size-1.5 rounded-full bg-forest animate-pulse" />
                          )}
                        </TableCell>
                        <TableCell className="text-left sticky right-12 bg-card group-hover:bg-muted/50 border-l border-line/70 z-10 max-sm:hidden">
                          <Button asChild variant="outline" size="sm" className="rounded-full gap-1.5 font-medium text-xs whitespace-nowrap">
                            <Link href={`/job/?id=${j.id}`}>
                              <Icon name={j.status === "done" ? "view-3d" : "arrow-up-right"} />
                              <span>{j.status === "done" ? t("jobs.inspectMap") : j.status === "failed" ? t("jobs.viewError") : t("jobs.viewProgress")}</span>
                            </Link>
                          </Button>
                        </TableCell>
                        <TableCell className="w-12 min-w-12 text-right sticky right-0 bg-card group-hover:bg-muted/50 z-10">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                ref={(el) => {
                                   actionButtonRefs.current[j.id] = el;
                                }}
                                variant="ghost"
                                size="icon-sm"
                                className="rounded-full cursor-pointer"
                                aria-label={t("jobs.actionsForJob", { id: j.id })}
                              >
                                <MoreHorizontal className="size-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setSelectedJob(j)}>
                                {t("jobs.actionProperties")}
                              </DropdownMenuItem>
                              <DropdownMenuItem asChild>
                                <Link href={`/job/?id=${j.id}`}>{t("jobs.actionOpen")}</Link>
                              </DropdownMenuItem>
                              {me?.is_admin && (
                                <>
                                  <DropdownMenuSeparator />
                                  {isDeleteDisabled ? (
                                    <DropdownMenuItem
                                      disabled
                                      className="flex flex-col items-start gap-0.5 opacity-50 cursor-not-allowed"
                                    >
                                      <span className="text-destructive font-medium">{t("jobs.actionDelete")}</span>
                                      <span className="text-[11px] text-muted-foreground font-normal">
                                        {deleteDisabledReason}
                                      </span>
                                    </DropdownMenuItem>
                                  ) : (
                                    <DropdownMenuItem
                                      variant="destructive"
                                      className="cursor-pointer"
                                      onClick={() => {
                                        setDeleteError(null);
                                        lastActionTriggerRef.current =
                                          actionButtonRefs.current[j.id] || null;
                                        setJobToDelete(j);
                                      }}
                                    >
                                      {t("jobs.actionDelete")}
                                    </DropdownMenuItem>
                                  )}
                                </>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </>
        )}
      </Panel>

      {/* Properties Sheet */}
      <Sheet open={!!selectedJob} onOpenChange={(open) => !open && setSelectedJob(null)}>
        <SheetContent side="right" className="p-0 gap-0 data-[side=right]:w-full data-[side=right]:sm:max-w-[480px] flex flex-col h-full bg-card">
          {selectedJob && (
            <>
              {/* Header */}
              <div className="px-6 pt-6 pb-4 border-b pr-14">
                <div className="flex items-center gap-2.5">
                  <SheetTitle className="text-base font-semibold text-foreground">
                    {t("jobs.sheetTitle", { id: selectedJob.id })}
                  </SheetTitle>
                  <StatusBadge status={selectedJob.status} />
                  {selectedJob.stalled && <StatusBadge status="stalled" />}
                </div>
                <SheetDescription className="sr-only">{t("jobs.properties", { id: selectedJob.id })}</SheetDescription>
                <p className="mt-1 text-xs text-muted-foreground truncate" title={selectedJob.created_by}>
                  {selectedJob.area_id} &middot; {selectedJob.created_by || "-"}
                </p>
              </div>

              {/* Scrollable Body */}
              <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
                {/* Preview Card */}
                {selectedJob.has_preview ? (
                  <div className="overflow-hidden rounded-xl border border-line/70 bg-card aspect-video">
                    <img
                      src={`/api/jobs/${selectedJob.id}/preview`}
                      alt={t("jobs.previewAlt")}
                      className="w-full h-full object-cover"
                    />
                  </div>
                ) : (
                  <div className="rounded-xl border border-line/70 bg-card aspect-video flex items-center justify-center text-xs text-muted-foreground">
                    {t("jobs.noPreview")}
                  </div>
                )}

                {/* Timeline Card */}
                {(() => {
                  const petaVideo = selectedJob.videos.find((v) => v.role === "peta" && v.recorded_at);
                  const recordedAt = petaVideo?.recorded_at ?? null;
                  return (
                    <div className="rounded-xl border border-line/70 bg-card p-4">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                        {t("jobs.timeline")}
                      </div>
                      <dl className="grid grid-cols-[116px_1fr] gap-x-4 gap-y-2.5 text-sm">
                        <dt className="text-muted-foreground">{t("jobs.colRecorded")}</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums" title={recordedAt || undefined}>
                          {formatDate(recordedAt)}
                        </dd>

                        <dt className="text-muted-foreground">{t("jobs.colUploaded")}</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums" title={selectedJob.created_at || undefined}>
                          {formatDate(selectedJob.created_at)}
                        </dd>

                        <dt className="text-muted-foreground">{t("jobs.started")}</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums" title={selectedJob.started_at || undefined}>
                          {formatDate(selectedJob.started_at)}
                        </dd>

                        <dt className="text-muted-foreground">{t("jobs.finished")}</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums" title={selectedJob.finished_at || undefined}>
                          {formatDate(selectedJob.finished_at)}
                        </dd>

                        <dt className="text-muted-foreground">{t("jobs.colDuration")}</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums">
                          {formatDuration(selectedJob.started_at, selectedJob.finished_at, {
                            isRunning: selectedJob.status === "running",
                          })}
                        </dd>
                      </dl>
                    </div>
                  );
                })()}

                {/* Map Card */}
                {(() => {
                  const run = selectedJob.summary?.run;
                  const ins = selectedJob.summary?.inspect;
                  const regFrames = run?.map_registered;
                  const totalFrames = run?.map_images;
                  const regPct = regFrames != null && totalFrames ? Math.round((regFrames / totalFrames) * 100) : null;
                  const queries = ins?.queries;
                  const accepted = ins?.accepted;
                  const hasTestVideo = queries != null && queries > 0;
                  const testPct = hasTestVideo && accepted != null ? Math.round((accepted / queries) * 100) : null;

                  return (
                    <div className="rounded-xl border border-line/70 bg-card p-4">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                        {t("jobs.map")}
                      </div>
                      <dl className="grid grid-cols-[116px_1fr] gap-x-4 gap-y-2.5 text-sm">
                        <dt className="text-muted-foreground">{t("jobs.mapVersion")}</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums">
                          {selectedJob.map_version_id != null ? (
                            <Link href="/maps/" className="text-forest font-medium hover:underline">
                              {t("jobs.versionLabel", { id: selectedJob.map_version_id })}
                            </Link>
                          ) : (
                            "-"
                          )}
                        </dd>

                        <dt className="text-muted-foreground">{t("jobs.registeredFrames")}</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums">
                          {regFrames != null && totalFrames != null ? (
                            <div>
                              <span>{regFrames} / {totalFrames}</span>
                              {regPct !== null && (
                                <div className="meter mt-1.5" role="img" aria-label={`${regPct}%`}>
                                  <span style={{ width: `${regPct}%` }} />
                                </div>
                              )}
                            </div>
                          ) : (
                            "-"
                          )}
                        </dd>

                        <dt className="text-muted-foreground">{t("jobs.mapPieces")}</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums">
                          {ins?.parts ? ins.parts.length : "-"}
                        </dd>

                        <dt className="text-muted-foreground">{t("jobs.testPhotosAccepted")}</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums">
                          {hasTestVideo ? (
                            <div>
                              <span>{accepted ?? 0} / {queries}</span>
                              {testPct !== null && (
                                <div className="meter mt-1.5" role="img" aria-label={`${testPct}%`}>
                                  <span style={{ width: `${testPct}%` }} />
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="text-muted-foreground">{t("jobs.noTestVideo")}</span>
                          )}
                        </dd>
                      </dl>
                    </div>
                  );
                })()}

                {/* Videos Card */}
                <div className="rounded-xl border border-line/70 bg-card p-4">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                    {t("jobs.videos")}
                  </div>
                  {selectedJob.videos && selectedJob.videos.length > 0 ? (
                    <div className="space-y-2">
                      {selectedJob.videos.map((v, i) => (
                        <div
                          key={i}
                          className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-xs py-1.5 border-b border-line/40 last:border-0"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="font-mono text-foreground truncate max-w-[180px]" title={v.name}>
                              {v.name}
                            </span>
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground capitalize">
                              {ROLE[v.role] ?? v.role}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-muted-foreground whitespace-nowrap text-right">
                            <span>{v.size != null ? mb(v.size) : "-"}</span>
                            <span>&middot;</span>
                            <span title={v.recorded_at || undefined}>
                              {v.recorded_at ? formatDate(v.recorded_at) : "-"}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">-</p>
                  )}
                </div>

                {/* Error Card */}
                {selectedJob.error && (
                  <JobFailureDiagnosis
                    error={selectedJob.error}
                    stage={selectedJob.stage}
                  />
                )}
              </div>

              {/* Footer */}
              <div className="border-t px-6 py-4 flex flex-wrap gap-2 mt-auto">
                <Button asChild variant="outline" className="rounded-full">
                  <Link href={`/job/?id=${selectedJob.id}`}>{t("jobs.openJob")}</Link>
                </Button>
                {me?.is_admin && (
                  <Button
                    variant="outline"
                    className="rounded-full text-destructive border-destructive/30 hover:bg-destructive/10 hover:text-destructive hover:border-destructive cursor-pointer"
                    disabled={
                      selectedJob.status === "deleting" ||
                      (selectedJob.status !== "done" &&
                        selectedJob.status !== "failed" &&
                        !(selectedJob.status === "uploading" && selectedJob.stalled))
                    }
                    onClick={() => {
                      const j = selectedJob;
                      setSelectedJob(null);
                      setTimeout(() => setJobToDelete(j), 100);
                    }}
                  >
                    {t("jobs.actionDelete")}
                  </Button>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      {/* Delete Confirmation Dialog */}
      <DeleteConsentDialog
        open={!!jobToDelete}
        onOpenChange={(open) => !open && setJobToDelete(null)}
        target={
          jobToDelete
            ? {
                type: "job",
                id: jobToDelete.id,
                area_id: jobToDelete.area_id,
              }
            : null
        }
        onConfirm={handleConfirmDelete}
        isDeleting={isDeleting}
        error={deleteError}
        triggerRef={lastActionTriggerRef}
      />
    </>
  );
}

export default function JobsPage() {
  return (
    <Suspense fallback={<div className="page-head"><span className="skeleton row" /></div>}>
      <JobsContent />
    </Suspense>
  );
}

