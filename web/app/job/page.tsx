"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, mb, STATUS } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

function JobDetail() {
  const id = Number(useSearchParams().get("id"));
  const { data: job, error } = usePoll(() => api.job(id), 5000, [id]);
  const [message, setMessage] = useState<string | null>(null);

  async function publish(versionId: number) {
    if (!window.confirm("Terbitkan peta ini? /localize akan memakai versi ini.")) return;
    try {
      const r = await api.publish(versionId);
      setMessage(
        r.reload === "started"
          ? `Versi ${r.version.version} sedang dimuat layanan dan aktif setelah berhasil. Pantau di Versi peta.`
          : `Versi ${r.version.version} diterbitkan, tetapi layanan ini melayani area lain.`,
      );
    } catch (e) {
      setMessage((e as Error).message);
    }
  }

  if (!id) return <p className="error">Parameter id tidak ada.</p>;
  // Galat saat data lama sudah tampil (misalnya sesi login habis) ditampilkan di atas data itu.
  if (!job) return error ? <p className="error">{error}</p> : <p>Memuat...</p>;
  const run = job.summary?.run;
  const ins = job.summary?.inspect;
  return (
    <>
      {error && <p className="error">{error}</p>}
      <h1>Pekerjaan {job.id}: {job.area_id}</h1>
      <p>
        <span className={`badge ${job.status}`}>{STATUS[job.status] ?? job.status}</span>{" "}
        tahap {job.stage ?? "-"}, oleh {job.created_by}
      </p>
      <table>
        <tbody>
          {job.videos.map((v) => (
            <tr key={v.name}>
              <td>{v.name}</td><td>{v.role}</td><td>{v.size === null ? "-" : mb(v.size)}</td>
              <td>{v.uploaded === null ? "dari terminal" : v.uploaded ? "terunggah" : "belum lengkap"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {job.error && <pre className="error">{job.error}</pre>}
      {run && ins && (
        <ul>
          <li>Frame terdaftar: {run.map_registered} dari {run.map_images}</li>
          <li>Potongan peta: {ins.parts?.length ?? 0} (1 berarti utuh)</li>
          <li>Foto uji diterima: {ins.accepted} dari {ins.queries} (ambang {ins.min_inliers} inlier)</li>
        </ul>
      )}
      {job.map_version_id && (
        <>
          <button onClick={() => publish(job.map_version_id!)}>Terbitkan versi ini</button>{" "}
          <Link href="/maps/">Versi peta</Link>
          {message && <p>{message}</p>}
          <h2>Tampilan 3D</h2>
          <iframe src={`/api/versions/${job.map_version_id}/report`} title="Tampilan 3D peta" />
        </>
      )}
    </>
  );
}

export default function JobPage() {
  // useSearchParams wajib di dalam Suspense pada static export (tanpa ini next build gagal).
  return (
    <Suspense fallback={<p>Memuat...</p>}>
      <JobDetail />
    </Suspense>
  );
}
