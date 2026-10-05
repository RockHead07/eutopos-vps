"use client";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/StatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import Link from "@/lib/Link";
import { api } from "@/lib/api";
import { PageHead } from "@/lib/PageHead";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";

export default function JobsPage() {
  const { data: jobs, error } = usePoll(api.jobs, 5000);
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
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead><TableHead>Area</TableHead><TableHead>Status</TableHead><TableHead>Stage</TableHead><TableHead>By</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((j) => (
                <TableRow key={j.id}>
                  <TableCell className="num"><Link href={`/job/?id=${j.id}`}>{j.id}</Link></TableCell>
                  <TableCell>{j.area_id}</TableCell>
                  <TableCell><StatusBadge status={j.status} /></TableCell>
                  <TableCell className="text-muted-foreground">{j.status === "done" ? "-" : (j.stage ?? "-")}</TableCell>
                  <TableCell className="text-muted-foreground">{j.created_by}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>
    </>
  );
}
