"use client";
import Link from "next/link";
import { api, type Job } from "@/lib/api";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";

const BUSY = ["uploading", "queued", "running"];

export default function OverviewPage() {
  const jobs = usePoll(api.jobs, 5000);
  const versions = usePoll(api.versions, 10000);
  const service = usePoll(api.service, 5000);
  const error = jobs.error ?? versions.error ?? service.error;

  const all = jobs.data ?? [];
  // Pekerjaan selesai yang punya foto uji, urut lama ke baru (id naik).
  const scored = all
    .filter((j) => j.status === "done" && (j.summary?.inspect?.queries ?? 0) > 0)
    .sort((a, b) => a.id - b.id);
  const latest = all.filter((j) => j.status === "done").sort((a, b) => b.id - a.id)[0];
  const counts = [
    { status: "done", label: "Done", n: all.filter((j) => j.status === "done").length },
    { status: "running", label: "In progress", n: all.filter((j) => BUSY.includes(j.status)).length },
    { status: "failed", label: "Failed", n: all.filter((j) => j.status === "failed").length },
  ];
  const s = service.data;

  return (
    <>
      <div className="page-head">
        <h1>Overview</h1>
        <p className="muted">Map builds, map quality, and the map /localize is serving.</p>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="overview">
        <section className="card area-active">
          <span className="stat-label">Active map</span>
          {s ? (
            <>
              <span className="stat-value">
                {s.area_id ?? "none"}
                {s.map_version !== null && <small> v{s.map_version}</small>}
              </span>
              <span>
                {s.reloading ? <span className="badge running">loading a new version</span> : <span className="badge done">ready</span>}
              </span>
            </>
          ) : (
            <span className="skeleton row" />
          )}
          {s?.reload_error && <p className="error">{s.reload_error}</p>}
          <h2>Recent versions</h2>
          {!versions.data && <Rows n={3} />}
          {versions.data && versions.data.length === 0 && <p className="muted">No map versions yet.</p>}
          <ul className="list">
            {[...(versions.data ?? [])]
              .sort((a, b) => b.id - a.id)
              .slice(0, 5)
              .map((v) => (
                <li key={v.id}>
                  <div>
                    <strong>{v.area_id} v{v.version}</strong>
                    <span className="muted">{v.job_id ? <Link href={`/job/?id=${v.job_id}`}>job {v.job_id}</Link> : "from CLI"}</span>
                  </div>
                  <span className={`badge ${v.status}`}>{v.status}</span>
                </li>
              ))}
          </ul>
          <Link href="/maps/">All map versions</Link>
        </section>

        <section className="card area-accept">
          <div>
            <h2>Test photos accepted</h2>
            <p className="muted">Share of each job&apos;s test photos localized with at least 50 inliers.</p>
          </div>
          {!jobs.data && <div className="skeleton block" />}
          {jobs.data && scored.length === 0 && (
            <p className="muted">No finished job with a test video yet. Add a test video to a map session to see this.</p>
          )}
          {scored.length > 0 && <AcceptChart jobs={scored} />}
          <Link href="/jobs/">View as table</Link>
        </section>

        <section className="card area-jobs">
          <span className="stat-label">Jobs</span>
          <span className="stat-value">{jobs.data ? all.length : <span className="skeleton row" />}</span>
          <ul className="status-bars">
            {counts.map((c) => (
              <li key={c.status}>
                <span className={`badge ${c.status}`}>{c.label}</span>
                <span className="track" aria-hidden="true">
                  <span style={{ width: all.length ? `${(c.n / all.length) * 100}%` : "0%" }} />
                </span>
                <span className="num">{c.n}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="card area-latest">
          <div className="actions">
            <h2>Latest map</h2>
            {latest && <Link href={`/job/?id=${latest.id}`}>Job {latest.id} · {latest.area_id}</Link>}
          </div>
          {!jobs.data && <div className="skeleton block" />}
          {jobs.data && !latest && <p className="muted">No finished job yet.</p>}
          {latest && <LatestStats job={latest} />}
        </section>
      </div>
    </>
  );
}

/** Satu seri: persen foto uji diterima per pekerjaan. Batang terbaru disorot dan diberi nilai. */
function AcceptChart({ jobs }: { jobs: Job[] }) {
  const last = jobs[jobs.length - 1].id;
  return (
    <div className="bars" role="img" aria-label="Test photos accepted per job">
      {jobs.map((j) => {
        const ins = j.summary!.inspect!;
        const pct = Math.round(((ins.accepted ?? 0) / (ins.queries ?? 1)) * 100);
        const tip = `Job ${j.id} (${j.area_id}): ${ins.accepted} of ${ins.queries} accepted, ${pct}%`;
        return (
          <Link key={j.id} href={`/job/?id=${j.id}`} className={j.id === last ? "bar latest" : "bar"} title={tip} aria-label={tip}>
            {j.id === last && <span className="bar-value num">{pct}%</span>}
            <span className="bar-fill" style={{ height: `${Math.max(pct, 2)}%` }} />
            <span className="bar-label num">#{j.id}</span>
          </Link>
        );
      })}
    </div>
  );
}

function LatestStats({ job }: { job: Job }) {
  const run = job.summary?.run;
  const ins = job.summary?.inspect;
  const items = [
    { label: "Registered frames", value: run?.map_registered, of: run?.map_images },
    { label: "Map pieces", value: ins?.parts?.length },
    { label: "Test photos accepted", value: ins?.accepted, of: ins?.queries || undefined },
  ];
  return (
    <div className="stats-inline">
      {items.map((it) => (
        <div key={it.label}>
          <span className="stat-label">{it.label}</span>
          <span className="stat-value">
            {it.value ?? "-"}
            {it.of !== undefined && <small> / {it.of}</small>}
          </span>
        </div>
      ))}
    </div>
  );
}
