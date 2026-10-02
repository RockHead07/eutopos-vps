"use client";
import Link from "next/link";
import { useState } from "react";
import { api, STATUS } from "@/lib/api";
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
    if (!window.confirm(`Jadikan versi ${version} aktif?`)) return;
    setError(null);
    setMessage(null);
    try {
      const r = await api.publish(id);
      if (r.reload === "other_area") {
        setMessage(`Versi ${version} ditandai aktif, tetapi layanan ini melayani area lain: /localize tidak memakainya.`);
      }
      setTick(tick + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const s = service.data;
  return (
    <>
      <h1>Versi peta</h1>
      {s && (
        <p>
          Layanan melayani area <strong>{s.area_id ?? "-"}</strong> versi {s.map_version ?? "-"}
          {s.reloading && ", sedang memuat versi baru..."}
        </p>
      )}
      {s?.reload_error && <p className="error">{s.reload_error}</p>}
      {message && <p>{message}</p>}
      {(error || versions.error || service.error) && (
        <p className="error">{error ?? versions.error ?? service.error}</p>
      )}
      <table>
        <thead>
          <tr><th>Area</th><th>Versi</th><th>Status</th><th>Pekerjaan</th><th>Diterbitkan oleh</th><th></th></tr>
        </thead>
        <tbody>
          {versions.data?.map((v) => (
            <tr key={v.id}>
              <td>{v.area_id}</td>
              <td>{v.version}</td>
              <td><span className={`badge ${v.status}`}>{STATUS[v.status] ?? v.status}</span></td>
              <td>{v.job_id ? <Link href={`/job/?id=${v.job_id}`}>{v.job_id}</Link> : "-"}</td>
              <td>{v.published_by ?? "-"}</td>
              <td>
                {v.status !== "published" && (
                  <button onClick={() => publish(v.id, v.version)} disabled={reloading}>
                    {v.status === "retired" ? "Kembalikan" : "Terbitkan"}
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
