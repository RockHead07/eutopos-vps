"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, mb, ROLE } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

function JobDetail() {
  const id = Number(useSearchParams().get("id"));
  const { data: job, error } = usePoll(() => api.job(id), 5000, [id]);
  const [message, setMessage] = useState<string | null>(null);

  async function publish(versionId: number) {
    if (!window.confirm("Publish this map? /localize will use this version.")) return;
    try {
      const r = await api.publish(versionId);
      setMessage(
        r.reload === "started"
          ? `Version ${r.version.version} is loading and goes live once it loads. Follow it in Map versions.`
          : `Version ${r.version.version} is published, but this service serves another area.`,
      );
    } catch (e) {
      setMessage((e as Error).message);
    }
  }

  if (!id) return <p className="error">Missing id parameter.</p>;
  // Galat saat data lama sudah tampil (misalnya sesi login habis) ditampilkan di atas data itu.
  if (!job) return error ? <p className="error">{error}</p> : <p>Loading...</p>;
  const run = job.summary?.run;
  const ins = job.summary?.inspect;
  return (
    <>
      {error && <p className="error">{error}</p>}
      <h1>Job {job.id}: {job.area_id}</h1>
      <p>
        <span className={`badge ${job.status}`}>{job.status}</span>{" "}
        stage {job.stage ?? "-"}, by {job.created_by}
      </p>
      <table>
        <tbody>
          {job.videos.map((v) => (
            <tr key={v.name}>
              <td>{v.name}</td><td>{ROLE[v.role] ?? v.role}</td><td>{v.size === null ? "-" : mb(v.size)}</td>
              <td>{v.uploaded === null ? "from CLI" : v.uploaded ? "uploaded" : "incomplete"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {job.error && <pre className="error">{job.error}</pre>}
      {run && ins && (
        <ul>
          <li>Registered frames: {run.map_registered} of {run.map_images}</li>
          <li>Map pieces: {ins.parts?.length ?? 0} (1 means one connected map)</li>
          <li>Test photos accepted: {ins.accepted} of {ins.queries} (threshold {ins.min_inliers} inliers)</li>
        </ul>
      )}
      {job.map_version_id && (
        <>
          <button onClick={() => publish(job.map_version_id!)}>Publish this version</button>{" "}
          <Link href="/maps/">Map versions</Link>
          {message && <p>{message}</p>}
          <h2>3D view</h2>
          <iframe src={`/api/versions/${job.map_version_id}/report`} title="3D map view" />
        </>
      )}
    </>
  );
}

export default function JobPage() {
  // useSearchParams wajib di dalam Suspense pada static export (tanpa ini next build gagal).
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <JobDetail />
    </Suspense>
  );
}
