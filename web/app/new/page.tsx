"use client";
import Uppy from "@uppy/core";
import Dashboard from "@uppy/react/dashboard";
import Tus from "@uppy/tus";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, mb, ROLE } from "@/lib/api";
import "@uppy/core/css/style.min.css";
import "@uppy/dashboard/css/style.min.css";

const CHUNK = 50 * 1024 * 1024; // di bawah batas Cloudflare Free 100 MB per permintaan

function createUppy() {
  return new Uppy({
    autoProceed: false,
    restrictions: { allowedFileTypes: ["video/*"], maxNumberOfFiles: 4, maxFileSize: 2 * 1024 ** 3 },
  }).use(Tus, {
    endpoint: "/files/",
    chunkSize: CHUNK,
    retryDelays: [0, 1000, 3000, 5000, 10000],
    allowedMetaFields: ["job_id", "name"], // dicocokkan hook pre-create dengan video terdaftar
    // Unggahan lama terikat ke pekerjaan lamanya: jangan dilanjutkan ke pekerjaan baru.
    storeFingerprintForResuming: false,
  });
}

type Role = "peta" | "uji";
type Picked = { id: string; name: string; size: number };

export default function NewSessionPage() {
  const router = useRouter();
  const [uppy] = useState(createUppy);
  const [files, setFiles] = useState<Picked[]>([]);
  const [roles, setRoles] = useState<Record<string, Role>>({});
  const [areaId, setAreaId] = useState("floor10");
  const [areaName, setAreaName] = useState("Lantai 10");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Pekerjaan dari klik sebelumnya. Isian sama = ulangi video yang gagal ke pekerjaan yang sama,
  // supaya pekerjaan tidak tertinggal setengah terunggah sampai kedaluwarsa 24 jam.
  const last = useRef<{ id: number; key: string } | null>(null);

  useEffect(() => {
    const sync = () =>
      setFiles(uppy.getFiles().map((f) => ({ id: f.id, name: f.name ?? "", size: f.size ?? 0 })));
    uppy.on("file-added", sync);
    uppy.on("file-removed", sync);
    return () => {
      uppy.off("file-added", sync);
      uppy.off("file-removed", sync);
    };
  }, [uppy]);

  // Bawaan seperti uji 2026-09-30: video pertama untuk peta, sisanya untuk uji.
  const roleOf = (f: Picked, i: number): Role => roles[f.id] ?? (i === 0 ? "peta" : "uji");

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const videos = files.map((f, i) => ({ name: f.name, size: f.size, role: roleOf(f, i) }));
      const key = JSON.stringify([areaId, areaName, videos]);
      if (last.current?.key !== key) {
        const job = await api.createJob({ area_id: areaId, area_name: areaName, videos });
        last.current = { id: job.id, key };
        uppy.setMeta({ job_id: String(job.id) });
        uppy.resetProgress(); // pekerjaan baru butuh semua video, termasuk yang sudah terunggah
      }
      // upload() mengulang video yang gagal dan mengunggah yang belum dimulai (termasuk yang
      // dihapus lalu ditambah lagi).
      await uppy.upload();
      // Server pemilik kebenaran: hasil Uppy tidak menghitung video yang dibatalkan atau dihapus.
      const job = await api.job(last.current.id);
      const missing = job.videos.filter((v) => !v.uploaded).map((v) => v.name);
      if (missing.length) {
        throw new Error(
          `Not uploaded yet: ${missing.join(", ")}. Add them again if removed, then press the button ` +
            "to retry. If your login session expired, reload the page (the upload starts over).",
        );
      }
      router.push(`/job/?id=${job.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>New map session</h1>
        <p className="muted">Walk the area with your back to the wall, camera facing the room. Videos are uploaded in 50 MiB chunks.</p>
      </div>
      <section className="card">
        <h2>Area</h2>
        <div className="fields">
          <label>
            Area ID (lowercase letters, digits, hyphens)
            <input value={areaId} onChange={(e) => setAreaId(e.target.value)} pattern="[a-z0-9][a-z0-9-]{0,39}" />
          </label>
          <label>
            Area name
            <input value={areaName} onChange={(e) => setAreaName(e.target.value)} />
          </label>
        </div>
      </section>
      <section className="card">
        <h2>Videos</h2>
        <Dashboard uppy={uppy} hideUploadButton proudlyDisplayPoweredByUppy={false} height={300} width="100%" />
        {files.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Video</th><th>Size</th><th>Role</th></tr>
              </thead>
              <tbody>
                {files.map((f, i) => (
                  <tr key={f.id}>
                    <td>{f.name}</td>
                    <td className="num">{mb(f.size)}</td>
                    <td>
                      <select value={roleOf(f, i)} onChange={(e) => setRoles({ ...roles, [f.id]: e.target.value as Role })}>
                        <option value="peta">{ROLE.peta}</option>
                        <option value="uji">{ROLE.uji}</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">For a production map, mark every video as map. Keep this tab open until the upload finishes.</p>
        <div className="actions">
          <button onClick={start} disabled={busy || files.length === 0}>
            {busy ? "Uploading..." : "Start upload"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>
    </>
  );
}
