"use client";
import { useMemo, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { Panel } from "@/components/Panel";
import { SortableHead, type SortDirection } from "@/components/SortableHead";
import { StatusBadge } from "@/components/StatusBadge";
import { TableFilterBar } from "@/components/TableFilterBar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
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
import { Icon, VersionBadge } from "@/lib/Icon";
import Link from "@/lib/Link";
import { api, formatDate, type Job, type Version } from "@/lib/api";
import { PageHead } from "@/lib/PageHead";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";

export default function MapsPage() {
  const [tick, setTick] = useState(0);
  const service = usePoll(api.service, 3000, [tick]);
  const reloading = service.data?.reloading ?? false;
  // Versi baru ditulis aktif setelah selesai dimuat: muat ulang daftar saat status memuat berubah.
  const versions = usePoll(api.versions, 10000, [tick, reloading]);
  const jobs = usePoll(api.jobs, 10000);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [selectedVersion, setSelectedVersion] = useState<Version | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [areaFilter, setAreaFilter] = useState("all");
  const [sortKey, setSortKey] = useState<string | null>("version");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");

  const statusOptions = [
    { value: "published", label: "Published" },
    { value: "candidate", label: "Candidate" },
    { value: "retired", label: "Retired" },
    { value: "rejected", label: "Rejected" },
  ];

  const areaOptions = useMemo(() => {
    if (!versions.data) return [];
    return Array.from(new Set(versions.data.map((v) => v.area_id))).sort();
  }, [versions.data]);

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
    setSortKey("version");
    setSortDir("desc");
  };

  const filteredAndSortedVersions = useMemo(() => {
    if (!versions.data) return [];
    const q = search.trim().toLowerCase();
    const filtered = versions.data.filter((v) => {
      if (statusFilter !== "all" && v.status !== statusFilter) return false;
      if (areaFilter !== "all" && v.area_id !== areaFilter) return false;
      if (q) {
        const matchVersion = v.version.toString().includes(q);
        const matchArea = v.area_id.toLowerCase().includes(q);
        const matchStatus = v.status.toLowerCase().includes(q);
        const matchJob = v.job_id ? v.job_id.toString().includes(q) : false;
        const matchPublished = v.published_by ? v.published_by.toLowerCase().includes(q) : false;
        return matchVersion || matchArea || matchStatus || matchJob || matchPublished;
      }
      return true;
    });

    if (!sortKey) return filtered;

    return filtered.slice().sort((a, b) => {
      let cmp = 0;
      if (sortKey === "version") cmp = a.version - b.version;
      else if (sortKey === "area_id") cmp = a.area_id.localeCompare(b.area_id);
      else if (sortKey === "status") cmp = a.status.localeCompare(b.status);
      else if (sortKey === "job_id") cmp = (a.job_id ?? 0) - (b.job_id ?? 0);
      else if (sortKey === "published_by") cmp = (a.published_by ?? "").localeCompare(b.published_by ?? "");
      else if (sortKey === "created_at") cmp = (a.created_at || "").localeCompare(b.created_at || "");
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [versions.data, search, statusFilter, areaFilter, sortKey, sortDir]);

  async function publish(id: number, version: number) {
    if (!window.confirm(`Make version ${version} active?`)) return;
    setError(null);
    setMessage(null);
    try {
      const r = await api.publish(id);
      if (r.reload === "other_area") {
        setMessage(`Version ${version} is marked active, but this service serves another area: /localize does not use it.`);
      }
      setTick(tick + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const s = service.data;
  return (
    <>
      <PageHead crumbs={[{ label: "Map versions" }]} title="Map versions">
        Publishing loads the map in the background. /localize keeps the current map until the new one loads.
      </PageHead>
      <section className="stats">
        <Panel>
          <span className="stat-label">Serving area</span>
          <span className="stat-value">{s ? (s.area_id ?? "none") : <span className="skeleton row" />}</span>
        </Panel>
        <Panel>
          <span className="stat-label">Active version</span>
          <span className="stat-value">{s ? (s.map_version ?? "-") : <span className="skeleton row" />}</span>
          {s && <span>{reloading ? <StatusBadge status="running">loading a new version</StatusBadge> : <StatusBadge status="done">ready</StatusBadge>}</span>}
        </Panel>
      </section>
      {s?.reload_error && <p className="error"><Icon name="error-map" /> {s.reload_error}</p>}
      {message && <p className="notice">{message}</p>}
      {(error || versions.error || service.error) && (
        <p className="error">{error ?? versions.error ?? service.error}</p>
      )}
      <Panel>
        <h2>All versions</h2>
        {!versions.data && !versions.error && <Rows />}
        {versions.data && versions.data.length === 0 && (
          <div className="empty"><p>No map versions yet. A finished job adds one.</p></div>
        )}
        {versions.data && versions.data.length > 0 && (
          <>
            <TableFilterBar
              search={search}
              onSearchChange={setSearch}
              searchPlaceholder="Search map versions..."
              statusFilter={statusFilter}
              onStatusChange={setStatusFilter}
              statusOptions={statusOptions}
              areaFilter={areaFilter}
              onAreaChange={setAreaFilter}
              areaOptions={areaOptions}
              totalCount={versions.data.length}
              filteredCount={filteredAndSortedVersions.length}
              onReset={handleReset}
            />
            {filteredAndSortedVersions.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground">
                <p>No map versions match your filter criteria.</p>
                <Button variant="link" size="sm" onClick={handleReset} className="text-xs text-forest mt-1">
                  Clear filters
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableHead column="area_id" label="Area" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <SortableHead column="version" label="Version" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <SortableHead column="status" label="Status" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <SortableHead column="job_id" label="Job" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <SortableHead column="published_by" label="Published by" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <SortableHead column="created_at" label="Created" activeKey={sortKey} direction={sortDir} onSort={handleSort} />
                    <TableHead className="text-left">Action</TableHead>
                    <TableHead className="w-10 text-right"><span className="sr-only">Actions</span></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredAndSortedVersions.map((v) => (
                    <TableRow key={v.id}>
                      <TableCell className="text-left">{v.area_id}</TableCell>
                      <TableCell className="text-left">{v.version}</TableCell>
                      <TableCell className="text-left"><VersionBadge status={v.status} /></TableCell>
                      <TableCell className="text-left">{v.job_id ? <Link href={`/job/?id=${v.job_id}`}>{v.job_id}</Link> : "-"}</TableCell>
                      <TableCell className="text-left text-muted-foreground">{v.published_by ?? "-"}</TableCell>
                      <TableCell className="text-left text-muted-foreground whitespace-nowrap" title={v.created_at || undefined}>
                        {formatDate(v.created_at)}
                      </TableCell>
                      <TableCell className="text-left">
                        {v.status !== "published" ? (
                          <Button variant="outline" className="rounded-full" onClick={() => publish(v.id, v.version)} disabled={reloading}>
                            {v.status === "retired" ? <><Icon name="restore" />Restore</> : <><Icon name="publish" />Publish</>}
                          </Button>
                        ) : (
                          "-"
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className="rounded-full"
                              aria-label={`Actions for version ${v.version}`}
                            >
                              <MoreHorizontal className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => setSelectedVersion(v)}>
                              Properties
                            </DropdownMenuItem>
                            {v.job_id ? (
                              <DropdownMenuItem asChild>
                                <Link href={`/job/?id=${v.job_id}`}>View job</Link>
                              </DropdownMenuItem>
                            ) : null}
                            {v.status !== "published" ? (
                              <DropdownMenuItem
                                onClick={() => publish(v.id, v.version)}
                                disabled={reloading}
                              >
                                {v.status === "retired" ? "Restore" : "Publish"}
                              </DropdownMenuItem>
                            ) : null}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </>
        )}
      </Panel>

      {/* Version Properties Sheet */}
      <Sheet open={!!selectedVersion} onOpenChange={(open) => !open && setSelectedVersion(null)}>
        <SheetContent side="right" className="p-0 gap-0 data-[side=right]:w-full data-[side=right]:sm:max-w-[480px] flex flex-col h-full bg-card">
          {selectedVersion && (() => {
            const sourceJob = selectedVersion.job_id != null ? jobs.data?.find((j) => j.id === selectedVersion.job_id) : undefined;
            const petaVideo = sourceJob?.videos?.find((v) => v.role === "peta" && v.recorded_at);
            const recordedAt = petaVideo?.recorded_at ?? null;

            return (
              <>
                {/* Header */}
                <div className="px-6 pt-6 pb-4 border-b pr-14">
                  <div className="flex items-center gap-2.5">
                    <SheetTitle className="text-base font-semibold text-foreground">
                      Version {selectedVersion.version}
                    </SheetTitle>
                    <VersionBadge status={selectedVersion.status} />
                  </div>
                  <SheetDescription className="sr-only">Version {selectedVersion.version} properties</SheetDescription>
                  <p className="mt-1 text-xs text-muted-foreground truncate" title={selectedVersion.area_id}>
                    {selectedVersion.area_id}
                  </p>
                </div>

                {/* Scrollable Body */}
                <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
                  {/* Preview Card */}
                  {sourceJob?.has_preview ? (
                    <div className="overflow-hidden rounded-xl border border-line/70 bg-card aspect-video">
                      <img
                        src={`/api/jobs/${sourceJob.id}/preview`}
                        alt="First frame of the map video"
                        className="w-full h-full object-cover"
                      />
                    </div>
                  ) : (
                    <div className="rounded-xl border border-line/70 bg-card aspect-video flex items-center justify-center text-xs text-muted-foreground">
                      No preview for this job
                    </div>
                  )}

                  {/* Version Card */}
                  <div className="rounded-xl border border-line/70 bg-card p-4">
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                      Version
                    </div>
                    <dl className="grid grid-cols-[116px_1fr] gap-x-4 gap-y-2.5 text-sm">
                      <dt className="text-muted-foreground">ID</dt>
                      <dd className="font-mono text-foreground min-w-0 break-words tabular-nums">
                        {selectedVersion.id}
                      </dd>

                      <dt className="text-muted-foreground">Area</dt>
                      <dd className="text-foreground min-w-0 break-words">
                        {selectedVersion.area_id}
                      </dd>

                      <dt className="text-muted-foreground">Version</dt>
                      <dd className="text-foreground font-semibold min-w-0 break-words tabular-nums">
                        {selectedVersion.version}
                      </dd>

                      <dt className="text-muted-foreground">Status</dt>
                      <dd>
                        <VersionBadge status={selectedVersion.status} />
                      </dd>

                      <dt className="text-muted-foreground">Created</dt>
                      <dd className="text-foreground min-w-0 break-words tabular-nums" title={selectedVersion.created_at || undefined}>
                        {formatDate(selectedVersion.created_at)}
                      </dd>

                      <dt className="text-muted-foreground">Published by</dt>
                      <dd className="text-foreground min-w-0 break-words">
                        {selectedVersion.published_by ?? "-"}
                      </dd>
                    </dl>
                  </div>

                  {/* Source Job Card */}
                  <div className="rounded-xl border border-line/70 bg-card p-4">
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                      Source job
                    </div>
                    {selectedVersion.job_id != null ? (
                      <dl className="grid grid-cols-[116px_1fr] gap-x-4 gap-y-2.5 text-sm">
                        <dt className="text-muted-foreground">Job</dt>
                        <dd>
                          <Link
                            href={`/job/?id=${selectedVersion.job_id}`}
                            className="text-forest font-medium hover:underline"
                          >
                            Job {selectedVersion.job_id}
                          </Link>
                        </dd>

                        <dt className="text-muted-foreground">Recorded</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums" title={recordedAt || undefined}>
                          {formatDate(recordedAt)}
                        </dd>

                        <dt className="text-muted-foreground">Uploaded</dt>
                        <dd className="text-foreground min-w-0 break-words tabular-nums" title={sourceJob?.created_at || undefined}>
                          {formatDate(sourceJob?.created_at)}
                        </dd>

                        <dt className="text-muted-foreground">Has report</dt>
                        <dd>
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                              selectedVersion.has_report
                                ? "bg-forest/10 text-forest"
                                : "bg-muted text-muted-foreground"
                            }`}
                          >
                            {selectedVersion.has_report ? "Yes" : "No"}
                          </span>
                        </dd>
                      </dl>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        Created from the command line, no job
                      </p>
                    )}
                  </div>
                </div>

                {/* Footer */}
                <div className="border-t px-6 py-4 flex flex-wrap gap-2 mt-auto">
                  {selectedVersion.job_id ? (
                    <Button asChild variant="outline" className="rounded-full">
                      <Link href={`/job/?id=${selectedVersion.job_id}`}>View job</Link>
                    </Button>
                  ) : null}
                  {selectedVersion.status !== "published" ? (
                    <Button
                      variant="outline"
                      className="rounded-full"
                      onClick={() => publish(selectedVersion.id, selectedVersion.version)}
                      disabled={reloading}
                    >
                      {selectedVersion.status === "retired" ? (
                        <>
                          <Icon name="restore" /> Restore
                        </>
                      ) : (
                        <>
                          <Icon name="publish" /> Publish
                        </>
                      )}
                    </Button>
                  ) : null}
                </div>
              </>
            );
          })()}
        </SheetContent>
      </Sheet>
    </>
  );
}
