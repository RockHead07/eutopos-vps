"use client";
import Link from "@/lib/Link";
import { api } from "@/lib/api";
import { Rows } from "@/lib/Rows";
import { usePoll } from "@/lib/usePoll";

export default function JobsPage() {
  const { data: jobs, error } = usePoll(api.jobs, 5000);
  return (
    <>
      <div className="page-head">
        <h1>Map build jobs</h1>
        <p className="muted">Every upload becomes a job: extract frames, build the map, inspect it. Refreshes every 5 seconds.</p>
      </div>
      {error && <p className="error">{error}</p>}
      <section className="card">
        {!jobs && !error && <Rows />}
        {jobs && jobs.length === 0 && (
          <div className="empty">
            <p>No jobs yet. Record a walk-through video, then upload it.</p>
            <Link href="/new/">Start a new map session</Link>
          </div>
        )}
        {jobs && jobs.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>#</th><th>Area</th><th>Status</th><th>Stage</th><th>By</th></tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td className="num"><Link href={`/job/?id=${j.id}`}>{j.id}</Link></td>
                    <td>{j.area_id}</td>
                    <td><span className={`badge ${j.status}`}>{j.status}</span></td>
                    <td className="muted">{j.status === "done" ? "-" : (j.stage ?? "-")}</td>
                    <td className="muted">{j.created_by}</td>
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
