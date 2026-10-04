"use client";
import { Icon, VersionBadge } from "@/lib/Icon";
import Link from "@/lib/Link";
import { useState } from "react";
import { api } from "@/lib/api";
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
      <div className="page-head">
        <h1>Map versions</h1>
        <p className="muted">Publishing loads the map in the background. /localize keeps the current map until the new one loads.</p>
      </div>
      <section className="stats">
        <div className="card">
          <span className="stat-label">Serving area</span>
          <span className="stat-value">{s ? (s.area_id ?? "none") : <span className="skeleton row" />}</span>
        </div>
        <div className="card">
          <span className="stat-label">Active version</span>
          <span className="stat-value">{s ? (s.map_version ?? "-") : <span className="skeleton row" />}</span>
          {s && <span>{reloading ? <span className="badge running">loading a new version</span> : <span className="badge done">ready</span>}</span>}
        </div>
      </section>
      {s?.reload_error && <p className="error"><Icon name="error-map" /> {s.reload_error}</p>}
      {message && <p className="notice">{message}</p>}
      {(error || versions.error || service.error) && (
        <p className="error">{error ?? versions.error ?? service.error}</p>
      )}
      <section className="card">
        <h2>All versions</h2>
        {!versions.data && !versions.error && <Rows />}
        {versions.data && versions.data.length === 0 && (
          <div className="empty"><p>No map versions yet. A finished job adds one.</p></div>
        )}
        {versions.data && versions.data.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Area</th><th>Version</th><th>Status</th><th>Job</th><th>Published by</th><th></th></tr>
              </thead>
              <tbody>
                {versions.data.map((v) => (
                  <tr key={v.id}>
                    <td>{v.area_id}</td>
                    <td className="num">{v.version}</td>
                    <td><VersionBadge status={v.status} /></td>
                    <td className="num">{v.job_id ? <Link href={`/job/?id=${v.job_id}`}>{v.job_id}</Link> : "-"}</td>
                    <td className="muted">{v.published_by ?? "-"}</td>
                    <td>
                      {v.status !== "published" && (
                        <button className="secondary" onClick={() => publish(v.id, v.version)} disabled={reloading}>
                          {v.status === "retired" ? <><Icon name="restore" />Restore</> : <><Icon name="publish" />Publish</>}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
