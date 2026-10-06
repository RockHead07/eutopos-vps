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
import { api, formatDate, type Version } from "@/lib/api";
import { PageHead } from "@/lib/PageHead";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";

export default function MapsPage() {
  const [tick, setTick] = useState(0);
  const service = usePoll(api.service, 3000, [tick]);
  const reloading = service.data?.reloading ?? false;
  // Versi baru ditulis aktif setelah selesai dimuat: muat ulang daftar saat status memuat berubah.
  const versions = usePoll(api.versions, 10000, [tick, reloading]);
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
        <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Version {selectedVersion?.version} Properties</SheetTitle>
            <SheetDescription>Read-only details from the server.</SheetDescription>
          </SheetHeader>
          {selectedVersion && (
            <div className="grid gap-4 py-4 text-sm">
              <div className="grid grid-cols-[140px_1fr] gap-2 items-start">
                <span className="text-muted-foreground">ID</span>
                <span className="font-mono">{selectedVersion.id}</span>

                <span className="text-muted-foreground">Area</span>
                <span>{selectedVersion.area_id}</span>

                <span className="text-muted-foreground">Version</span>
                <span className="font-semibold">{selectedVersion.version}</span>

                <span className="text-muted-foreground">Status</span>
                <div><VersionBadge status={selectedVersion.status} /></div>

                <span className="text-muted-foreground">Created</span>
                <span title={selectedVersion.created_at || undefined}>{formatDate(selectedVersion.created_at)}</span>

                <span className="text-muted-foreground">Published by</span>
                <span>{selectedVersion.published_by ?? "-"}</span>

                <span className="text-muted-foreground">Job ID</span>
                <span>
                  {selectedVersion.job_id ? (
                    <Link href={`/job/?id=${selectedVersion.job_id}`}>{selectedVersion.job_id}</Link>
                  ) : (
                    "-"
                  )}
                </span>

                <span className="text-muted-foreground">Has report</span>
                <span>{selectedVersion.has_report ? "Yes" : "No"}</span>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
