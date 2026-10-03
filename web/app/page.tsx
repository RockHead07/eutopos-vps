"use client";
import Link from "next/link";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function JobsPage() {
  const { data: jobs, error } = usePoll(api.jobs, 5000);
  return (
    <>
      <h1>Map build jobs</h1>
      {error && <p className="error">{error}</p>}
      {jobs && jobs.length === 0 && <p>No jobs yet. Start from New map session.</p>}
      {jobs && jobs.length > 0 && (
        <table>
          <thead>
            <tr><th>#</th><th>Area</th><th>Status</th><th>Stage</th><th>By</th></tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td><Link href={`/job/?id=${j.id}`}>{j.id}</Link></td>
                <td>{j.area_id}</td>
                <td><span className={`badge ${j.status}`}>{j.status}</span></td>
                <td>{j.stage ?? "-"}</td>
                <td>{j.created_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
