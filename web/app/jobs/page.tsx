"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { MoreHorizontal } from "lucide-react";
import { Panel } from "@/components/Panel";
import { SortableHead, type SortDirection } from "@/components/SortableHead";
import { StatusBadge } from "@/components/StatusBadge";
import { TableFilterBar } from "@/components/TableFilterBar";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { api, formatDate, formatDuration, mb, ROLE, type Job } from "@/lib/api";
import { PageHead } from "@/lib/PageHead";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";

function JobsContent() {
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

  const statusOptions = [
    { value: "done", label: "Done" },
    { value: "uploading", label: "Uploading" },
    { value: "running", label: "Running" },
    { value: "queued", label: "Queued" },
    { value: "failed", label: "Failed" },
    { value: "deleting", label: "Deleting" },
  ];

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
        const matchStatus = j.status.toLowerCase().includes(q);
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
      else if (sortKey === "created_at") cmp = (a.created_at || "").localeCompare(b.created_at || "");
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [jobs, search, statusFilter, areaFilter, sortKey, sortDir]);

  return (
    <>
      <PageHead crumbs={[{ label: "Jobs" }]} title="Map build jobs">
        Every upload becomes a job: extract frames, build the map, inspect it. Refreshes every 5 seconds.
      </PageHead>
      {error && <p className="error">{error}</p>}
      <Panel>
        {!jobs && !error && <Rows />}
        {jobs && jobs.length === 0 && (
          <div className="empty">
            <p>No jobs yet. Record a walk-through video, then upload it.</p>
            <Link href="/new/">Start a new map session</Link>
          </div>
        )}
        {jobs && jobs.length > 0 && (
          <>
            <TableFilterBar
              search={search}
              onSearchChange={setSearch}
              searchPlaceholder="Search jobs..."
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
                <p>No jobs match your filter criteria.</p>
                <Button variant="link" size="sm" onClick={handleReset} className="text-xs text-forest mt-1">
                  Clear filters
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableHead column="id" label="#" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <SortableHead column="area_id" label="Area" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <SortableHead column="status" label="Status" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <TableHead className="text-left">Stage</TableHead>
                    <SortableHead column="created_by" label="By" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <SortableHead column="created_at" label="Created" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <TableHead className="text-left">Duration</TableHead>
                    <TableHead className="text-left">Action</TableHead>
                    <TableHead className="w-10 text-right"><span className="sr-only">Actions</span></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredAndSortedJobs.map((j) => {
                    const isDeletingStatus = j.status === "deleting";
                    const isNotDoneOrFailed = j.status !== "done" && j.status !== "failed";
                    const isDeleteDisabled = isDeletingStatus || isNotDoneOrFailed;
                    const deleteDisabledReason = isDeletingStatus
                      ? "Job is already being deleted"
                      : "Only completed or failed jobs can be deleted";

                    return (
                      <TableRow key={j.id}>
                        <TableCell className="text-left"><Link href={`/job/?id=${j.id}`}>{j.id}</Link></TableCell>
                        <TableCell className="text-left">{j.area_id}</TableCell>
                        <TableCell className="text-left"><StatusBadge status={j.status} /></TableCell>
                        <TableCell className="text-left text-muted-foreground">{j.status === "done" ? "-" : (j.stage ?? "-")}</TableCell>
                        <TableCell className="text-left text-muted-foreground">{j.created_by}</TableCell>
                        <TableCell className="text-left text-muted-foreground whitespace-nowrap" title={j.created_at || undefined}>
                          {formatDate(j.created_at)}
                        </TableCell>
                        <TableCell className="text-left text-muted-foreground whitespace-nowrap">
                          {formatDuration(j.started_at, j.finished_at)}
                        </TableCell>
                        <TableCell className="text-left">
                          <Button asChild variant="outline" size="sm" className="rounded-full gap-1.5 font-medium text-xs whitespace-nowrap">
                            <Link href={`/job/?id=${j.id}`}>
                              <Icon name={j.status === "done" ? "view-3d" : "arrow-up-right"} />
                              <span>{j.status === "done" ? "Inspect map" : j.status === "failed" ? "View error" : "View progress"}</span>
                            </Link>
                          </Button>
                        </TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                className="rounded-full"
                                aria-label={`Actions for job ${j.id}`}
                              >
                                <MoreHorizontal className="size-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setSelectedJob(j)}>
                                Properties
                              </DropdownMenuItem>
                              <DropdownMenuItem asChild>
                                <Link href={`/job/?id=${j.id}`}>Open</Link>
                              </DropdownMenuItem>
                              {me?.is_admin && (
                                <>
                                  <DropdownMenuSeparator />
                                  {isDeleteDisabled ? (
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <div className="w-full">
                                          <DropdownMenuItem
                                            disabled
                                            variant="destructive"
                                            className="w-full cursor-not-allowed opacity-50"
                                          >
                                            Delete
                                          </DropdownMenuItem>
                                        </div>
                                      </TooltipTrigger>
                                      <TooltipContent>{deleteDisabledReason}</TooltipContent>
                                    </Tooltip>
                                  ) : (
                                    <DropdownMenuItem
                                      variant="destructive"
                                      onClick={() => {
                                        setDeleteError(null);
                                        setJobToDelete(j);
                                      }}
                                    >
                                      Delete
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
                    Job {selectedJob.id}
                  </SheetTitle>
                  <StatusBadge status={selectedJob.status} />
                </div>
                <SheetDescription className="sr-only">Job {selectedJob.id} properties</SheetDescription>
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
                      alt="First frame of the map video"
                      className="w-full h-full object-cover"
                    />
                  </div>
                ) : (
                  <div className="rounded-xl border border-line/70 bg-card aspect-video flex items-center justify-center text-xs text-muted-foreground">
                    No preview for this job
                  </div>
                )}

                {/* Timeline Card */}
                {(() => {
                  const petaVideo = selectedJob.videos.find((v) => v.role === "peta" && v.recorded_at);
                  const recordedAt = petaVideo?.recorded_at ?? null;
                  return (
                    <div className="rounded-xl border border-line/70 bg-card p-4">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                        Timeline
                      </div>
                      <dl className="grid grid-cols-[116px_1fr] gap-x-4 gap-y-2.5 text-sm">
                        <dt className="text-muted-foreground">Recorded</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums" title={recordedAt || undefined}>
                          {formatDate(recordedAt)}
                        </dd>

                        <dt className="text-muted-foreground">Uploaded</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums" title={selectedJob.created_at || undefined}>
                          {formatDate(selectedJob.created_at)}
                        </dd>

                        <dt className="text-muted-foreground">Started</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums" title={selectedJob.started_at || undefined}>
                          {formatDate(selectedJob.started_at)}
                        </dd>

                        <dt className="text-muted-foreground">Finished</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums" title={selectedJob.finished_at || undefined}>
                          {formatDate(selectedJob.finished_at)}
                        </dd>

                        <dt className="text-muted-foreground">Duration</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums">
                          {formatDuration(selectedJob.started_at, selectedJob.finished_at)}
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
                        Map
                      </div>
                      <dl className="grid grid-cols-[116px_1fr] gap-x-4 gap-y-2.5 text-sm">
                        <dt className="text-muted-foreground">Map version</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums">
                          {selectedJob.map_version_id != null ? (
                            <Link href="/maps/" className="text-forest font-medium hover:underline">
                              Version {selectedJob.map_version_id}
                            </Link>
                          ) : (
                            "-"
                          )}
                        </dd>

                        <dt className="text-muted-foreground">Registered frames</dt>
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

                        <dt className="text-muted-foreground">Map pieces</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums">
                          {ins?.parts ? ins.parts.length : "-"}
                        </dd>

                        <dt className="text-muted-foreground">Test photos accepted</dt>
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
                            <span className="text-muted-foreground">No test video in this job</span>
                          )}
                        </dd>
                      </dl>
                    </div>
                  );
                })()}

                {/* Videos Card */}
                <div className="rounded-xl border border-line/70 bg-card p-4">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                    Videos
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
                  <div className="rounded-xl border border-line/70 bg-card p-4">
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-destructive mb-2">
                      Error
                    </div>
                    <pre className="font-mono text-xs text-destructive bg-destructive/10 p-3 rounded-lg overflow-x-auto max-h-48 whitespace-pre-wrap break-words">
                      {selectedJob.error}
                    </pre>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="border-t px-6 py-4 flex flex-wrap gap-2 mt-auto">
                <Button asChild variant="outline" className="rounded-full">
                  <Link href={`/job/?id=${selectedJob.id}`}>Open job</Link>
                </Button>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      {/* Delete Confirmation AlertDialog */}
      <AlertDialog open={!!jobToDelete} onOpenChange={(open) => !open && setJobToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Delete job {jobToDelete?.id} ({jobToDelete?.area_id})?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This will remove the generated map and database rows. Extracted frames in data/jobs/ will be kept.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && <p className="error text-sm">{deleteError}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel autoFocus disabled={isDeleting}>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={isDeleting}
              onClick={handleConfirmDelete}
            >
              {isDeleting ? "Deleting..." : "Delete"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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

