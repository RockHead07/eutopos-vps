"use client";
import { useMemo, useState } from "react";
import { Panel } from "@/components/Panel";
import { SortableHead, type SortDirection } from "@/components/SortableHead";
import { StatusBadge } from "@/components/StatusBadge";
import { TableFilterBar } from "@/components/TableFilterBar";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { api } from "@/lib/api";
import { PageHead } from "@/lib/PageHead";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";

export default function JobsPage() {
  const { data: jobs, error } = usePoll(api.jobs, 5000);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [areaFilter, setAreaFilter] = useState("all");
  const [sortKey, setSortKey] = useState<string | null>("id");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");

  const statusOptions = [
    { value: "done", label: "Done" },
    { value: "running", label: "Running" },
    { value: "queued", label: "Queued" },
    { value: "failed", label: "Failed" },
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
                    <TableHead className="text-left">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredAndSortedJobs.map((j) => (
                    <TableRow key={j.id}>
                      <TableCell className="text-left"><Link href={`/job/?id=${j.id}`}>{j.id}</Link></TableCell>
                      <TableCell className="text-left">{j.area_id}</TableCell>
                      <TableCell className="text-left"><StatusBadge status={j.status} /></TableCell>
                      <TableCell className="text-left text-muted-foreground">{j.status === "done" ? "-" : (j.stage ?? "-")}</TableCell>
                      <TableCell className="text-left text-muted-foreground">{j.created_by}</TableCell>
                      <TableCell className="text-left">
                        <Button asChild variant="outline" size="sm" className="rounded-full gap-1.5 font-medium text-xs whitespace-nowrap">
                          <Link href={`/job/?id=${j.id}`}>
                            <Icon name={j.status === "done" ? "view-3d" : "arrow-up-right"} />
                            <span>{j.status === "done" ? "Inspect map" : j.status === "failed" ? "View error" : "View progress"}</span>
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </>
        )}
      </Panel>
    </>
  );
}
