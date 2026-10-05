"use client";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Icon, VersionBadge } from "@/lib/Icon";
import Link from "@/lib/Link";
import { useState } from "react";
import { api } from "@/lib/api";
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
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Area</TableHead><TableHead>Version</TableHead><TableHead>Status</TableHead><TableHead>Job</TableHead><TableHead>Published by</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {versions.data.map((v) => (
                <TableRow key={v.id}>
                  <TableCell>{v.area_id}</TableCell>
                  <TableCell className="num">{v.version}</TableCell>
                  <TableCell><VersionBadge status={v.status} /></TableCell>
                  <TableCell className="num">{v.job_id ? <Link href={`/job/?id=${v.job_id}`}>{v.job_id}</Link> : "-"}</TableCell>
                  <TableCell className="text-muted-foreground">{v.published_by ?? "-"}</TableCell>
                  <TableCell>
                    {v.status !== "published" && (
                      <Button variant="outline" className="rounded-full" onClick={() => publish(v.id, v.version)} disabled={reloading}>
                        {v.status === "retired" ? <><Icon name="restore" />Restore</> : <><Icon name="publish" />Publish</>}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>
    </>
  );
}
