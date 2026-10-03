"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
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
      <h1>Map versions</h1>
      {s && (
        <p>
          Serving area <strong>{s.area_id ?? "-"}</strong> version {s.map_version ?? "-"}
          {s.reloading && ", loading a new version..."}
        </p>
      )}
      {s?.reload_error && <p className="error">{s.reload_error}</p>}
      {message && <p>{message}</p>}
      {(error || versions.error || service.error) && (
        <p className="error">{error ?? versions.error ?? service.error}</p>
      )}
      <table>
        <thead>
          <tr><th>Area</th><th>Version</th><th>Status</th><th>Job</th><th>Published by</th><th></th></tr>
        </thead>
        <tbody>
          {versions.data?.map((v) => (
            <tr key={v.id}>
              <td>{v.area_id}</td>
              <td>{v.version}</td>
              <td><span className={`badge ${v.status}`}>{v.status}</span></td>
              <td>{v.job_id ? <Link href={`/job/?id=${v.job_id}`}>{v.job_id}</Link> : "-"}</td>
              <td>{v.published_by ?? "-"}</td>
              <td>
                {v.status !== "published" && (
                  <button onClick={() => publish(v.id, v.version)} disabled={reloading}>
                    {v.status === "retired" ? "Restore" : "Publish"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
