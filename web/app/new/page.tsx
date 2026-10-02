"use client";
import Uppy from "@uppy/core";
import Dashboard from "@uppy/react/dashboard";
import Tus from "@uppy/tus";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, mb } from "@/lib/api";
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
      let result;
      if (last.current?.key === key) {
        result = await uppy.retryAll();
      } else {
        const job = await api.createJob({ area_id: areaId, area_name: areaName, videos });
        last.current = { id: job.id, key };
        uppy.setMeta({ job_id: String(job.id) });
        uppy.resetProgress(); // pekerjaan baru butuh semua video, termasuk yang sudah terunggah
        result = await uppy.upload();
      }
      if (result?.failed?.length) {
        throw new Error(`${result.failed.length} video gagal diunggah. Tekan tombol lagi untuk mengulang.`);
      }
      router.push(`/job/?id=${last.current.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Sesi peta baru</h1>
      <label>
        ID area (huruf kecil, angka, tanda hubung){" "}
        <input value={areaId} onChange={(e) => setAreaId(e.target.value)} pattern="[a-z0-9][a-z0-9-]{0,39}" />
      </label>
      <label>
        Nama area <input value={areaName} onChange={(e) => setAreaName(e.target.value)} />
      </label>
      <Dashboard uppy={uppy} hideUploadButton proudlyDisplayPoweredByUppy={false} height={320} />
      {files.length > 0 && (
        <table>
          <thead>
            <tr><th>Video</th><th>Ukuran</th><th>Peran</th></tr>
          </thead>
          <tbody>
            {files.map((f, i) => (
              <tr key={f.id}>
                <td>{f.name}</td>
                <td>{mb(f.size)}</td>
                <td>
                  <select value={roleOf(f, i)} onChange={(e) => setRoles({ ...roles, [f.id]: e.target.value as Role })}>
                    <option value="peta">peta</option>
                    <option value="uji">uji</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>Peta produksi: tandai semua video sebagai peta. Jangan tutup tab sampai unggahan selesai.</p>
      <button onClick={start} disabled={busy || files.length === 0}>
        {busy ? "Mengunggah..." : "Mulai unggah"}
      </button>
      {error && <p className="error">{error}</p>}
    </>
  );
}
