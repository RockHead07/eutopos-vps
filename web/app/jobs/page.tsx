"use client";
import { useEffect, useMemo, useState } from "react";
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

export default function JobsPage() {
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
        <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Job {selectedJob?.id} Properties</SheetTitle>
            <SheetDescription>Read-only details from the server.</SheetDescription>
          </SheetHeader>
          {selectedJob && (
            <div className="grid gap-4 py-4 text-sm">
              <div className="grid grid-cols-[140px_1fr] gap-2 items-start">
                <span className="text-muted-foreground">ID</span>
                <span className="font-mono">{selectedJob.id}</span>

                <span className="text-muted-foreground">Area</span>
                <span>{selectedJob.area_id}</span>

                <span className="text-muted-foreground">Status</span>
                <div><StatusBadge status={selectedJob.status} /></div>

                <span className="text-muted-foreground">Stage</span>
                <span>{selectedJob.stage ?? "-"}</span>

                <span className="text-muted-foreground">Created by</span>
                <span>{selectedJob.created_by || "-"}</span>

                <span className="text-muted-foreground">Created</span>
                <span title={selectedJob.created_at || undefined}>{formatDate(selectedJob.created_at)}</span>

                <span className="text-muted-foreground">Started</span>
                <span title={selectedJob.started_at || undefined}>{formatDate(selectedJob.started_at)}</span>

                <span className="text-muted-foreground">Finished</span>
                <span title={selectedJob.finished_at || undefined}>{formatDate(selectedJob.finished_at)}</span>

                <span className="text-muted-foreground">Duration</span>
                <span>{formatDuration(selectedJob.started_at, selectedJob.finished_at)}</span>

                <span className="text-muted-foreground">Map version ID</span>
                <span>{selectedJob.map_version_id != null ? selectedJob.map_version_id : "-"}</span>
              </div>

              <div className="border-t pt-3">
                <h3 className="font-medium mb-2 text-foreground">Videos</h3>
                {selectedJob.videos && selectedJob.videos.length > 0 ? (
                  <ul className="space-y-1.5 text-xs text-muted-foreground">
                    {selectedJob.videos.map((v, i) => (
                      <li key={i} className="flex justify-between items-center bg-muted/40 p-2 rounded">
                        <span className="font-mono text-foreground truncate max-w-[180px]" title={v.name}>{v.name}</span>
                        <span>{ROLE[v.role] ?? v.role} &middot; {v.size != null ? mb(v.size) : "-"}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </div>

              <div className="border-t pt-3">
                <h3 className="font-medium mb-2 text-foreground">Key Summary</h3>
                <div className="grid grid-cols-[160px_1fr] gap-2 text-xs">
                  <span className="text-muted-foreground">Registered frames</span>
                  <span>
                    {selectedJob.summary?.run?.map_registered != null
                      ? `${selectedJob.summary.run.map_registered} / ${selectedJob.summary.run.map_images ?? "-"}`
                      : "-"}
                  </span>

                  <span className="text-muted-foreground">Map pieces</span>
                  <span>{selectedJob.summary?.inspect?.parts ? selectedJob.summary.inspect.parts.length : "-"}</span>

                  <span className="text-muted-foreground">Accepted photos / queries</span>
                  <span>
                    {selectedJob.summary?.inspect?.accepted != null
                      ? `${selectedJob.summary.inspect.accepted} / ${selectedJob.summary.inspect.queries ?? "-"}`
                      : "-"}
                  </span>
                </div>
              </div>

              {selectedJob.error && (
                <div className="border-t pt-3">
                  <h3 className="font-medium mb-2 text-destructive">Error</h3>
                  <p className="error text-xs">{selectedJob.error}</p>
                </div>
              )}
            </div>
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
