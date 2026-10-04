"use client";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, mb, ROLE } from "@/lib/api";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";

function Stat({ label, value, of, note }: { label: string; value?: number; of?: number; note?: string }) {
  const pct = value !== undefined && of ? Math.round((value / of) * 100) : null;
  return (
    <div className="card">
      <span className="stat-label">{label}</span>
      <span className="stat-value">
        {value ?? "-"}
        {of !== undefined && <small> / {of}</small>}
      </span>
      {pct !== null && (
        <div className="meter" role="img" aria-label={`${pct}%`}>
          <span style={{ width: `${pct}%` }} />
        </div>
      )}
      {note && <span className="muted">{note}</span>}
    </div>
  );
}

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
  if (!job) return error ? <p className="error">{error}</p> : <Loading />;
  const run = job.summary?.run;
  const ins = job.summary?.inspect;
  return (
    <>
      {error && <p className="error">{error}</p>}
      <div className="page-head">
        <p className="muted"><Link href="/jobs/">Jobs</Link> / {job.id}</p>
        <h1>Job {job.id} · {job.area_id}</h1>
        <p className="muted">
          <span className={`badge ${job.status}`}>{job.status}</span>{" "}
          {job.status !== "done" && job.stage && <>stage {job.stage} · </>}by {job.created_by}
        </p>
      </div>
      {job.error && <pre className="error">{job.error}</pre>}
      {run && ins && (
        <section className="stats">
          <Stat label="Registered frames" value={run.map_registered} of={run.map_images} />
          <Stat
            label="Map pieces"
            value={ins.parts?.length ?? 0}
            note={(ins.parts?.length ?? 0) === 1 ? "One connected map" : "Split map: re-record the gaps"}
          />
          <Stat
            label="Test photos accepted"
            value={ins.accepted}
            of={ins.queries || undefined}
            note={ins.queries ? `At least ${ins.min_inliers} inliers each` : "No test video in this job"}
          />
        </section>
      )}
      <section className="card">
        <h2>Videos</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Name</th><th>Role</th><th>Size</th><th>Upload</th></tr>
            </thead>
            <tbody>
              {job.videos.map((v) => (
                <tr key={v.name}>
                  <td>{v.name}</td>
                  <td>{ROLE[v.role] ?? v.role}</td>
                  <td className="num">{v.size === null ? "-" : mb(v.size)}</td>
                  <td className="muted">{v.uploaded === null ? "from CLI" : v.uploaded ? "uploaded" : "incomplete"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {job.map_version_id && (
        <section className="card">
          <div className="actions">
            <h2><Icon name="view-3d" /> 3D view</h2>
            <span className="muted">Map and cameras in blue, accepted test photos in green, rejected in orange.</span>
          </div>
          <iframe src={`/api/versions/${job.map_version_id}/report`} title="3D map view" />
          <div className="actions">
            <button onClick={() => publish(job.map_version_id!)}><Icon name="publish" />Publish this version</button>
            <Link href="/maps/">Map versions</Link>
          </div>
          {message && <p className="notice">{message}</p>}
        </section>
      )}
    </>
  );
}

function Loading() {
  return (
    <>
      <div className="page-head"><span className="skeleton row" /></div>
      <section className="stats">
        <div className="skeleton block" />
        <div className="skeleton block" />
        <div className="skeleton block" />
      </section>
      <section className="card"><Rows /></section>
    </>
  );
}

export default function JobPage() {
  // useSearchParams wajib di dalam Suspense pada static export (tanpa ini next build gagal).
  return (
    <Suspense fallback={<Loading />}>
      <JobDetail />
    </Suspense>
  );
}
