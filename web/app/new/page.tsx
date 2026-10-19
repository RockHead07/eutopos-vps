"use client";
import Uppy from "@uppy/core";
import Dashboard from "@uppy/react/dashboard";
import Tus from "@uppy/tus";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, AREA_ID_RE, mb, ROLE } from "@/lib/api";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Icon } from "@/lib/Icon";
import { PageHead } from "@/lib/PageHead";
import { shouldRetryUpload, stalledFileIds } from "@/lib/uploadRetry";
import "@uppy/core/css/style.min.css";
import "@uppy/dashboard/css/style.min.css";

const CHUNK = 8 * 1024 * 1024; // 8 MiB (kelipatan 256 KiB), toleran terhadap koneksi ponsel yang putus

type RetryHandler = (msg: string | null) => void;

function createUppy(onRetryRef: React.RefObject<RetryHandler | null>) {
  return new Uppy({
    autoProceed: false,
    restrictions: { allowedFileTypes: ["video/*"], maxNumberOfFiles: 4, maxFileSize: 2 * 1024 ** 3 },
  }).use(Tus, {
    endpoint: "/files/",
    chunkSize: CHUNK,
    retryDelays: [0, 1000, 3000, 5000, 10000, 20000, 30000, 60000, 60000, 60000],
    allowedMetaFields: ["job_id", "name"], // dicocokkan hook pre-create dengan video terdaftar
    // Unggahan lama terikat ke pekerjaan lamanya: jangan dilanjutkan ke pekerjaan baru.
    storeFingerprintForResuming: false,
    // Aturan sendiri (lib/uploadRetry.ts), bukan next(err): aturan bawaan tidak mengulang 429 dan berhenti saat offline.
    onShouldRetry(err, retryAttempt) {
      if (!shouldRetryUpload(err.originalResponse?.getStatus())) {
        onRetryRef.current?.(null);
        return false;
      }
      onRetryRef.current?.(`Connection lost, retrying (attempt ${retryAttempt + 1})`);
      return true;
    },
  });
}

type Role = "peta" | "uji";
type Picked = { id: string; name: string; size: number };

export default function NewSessionPage() {
  const router = useRouter();
  const [retryStatus, setRetryStatus] = useState<string | null>(null);
  const onRetryRef = useRef<RetryHandler | null>(null);
  onRetryRef.current = setRetryStatus;
  const [uppy] = useState(() => createUppy(onRetryRef));
  const [files, setFiles] = useState<Picked[]>([]);
  const [roles, setRoles] = useState<Record<string, Role>>({});
  const [areaId, setAreaId] = useState("floor10");
  const [areaName, setAreaName] = useState("Lantai 10");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Pekerjaan dari klik sebelumnya. Isian sama = ulangi video yang gagal ke pekerjaan yang sama,
  // supaya pekerjaan tidak tertinggal setengah terunggah sampai kedaluwarsa 24 jam.
  const last = useRef<{ id: number; key: string } | null>(null);
  const wakeLockRef = useRef<any>(null);

  // Wake lock dan beforeunload saat unggahan berjalan
  useEffect(() => {
    if (!busy) return;

    const acquireLock = async () => {
      try {
        if ("wakeLock" in navigator && !wakeLockRef.current) {
          wakeLockRef.current = await (navigator as any).wakeLock.request("screen");
          wakeLockRef.current.addEventListener("release", () => {
            wakeLockRef.current = null;
          });
        }
      } catch {
        // Feature detection / permission failure: abaikan tanpa error
      }
    };

    acquireLock();

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        acquireLock();
      }
    };

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("beforeunload", handleBeforeUnload);
      if (wakeLockRef.current) {
        try {
          wakeLockRef.current.release();
        } catch {
          // ignore
        }
        wakeLockRef.current = null;
      }
    };
  }, [busy]);

  // Pengawas: permintaan yang menggantung (respons hilang di jalan) tidak pernah menjadi galat, jadi tus tidak
  // mengulangnya. Tanpa kemajuan byte selama STALL_MS, jeda lalu lanjutkan berkas itu: tus membatalkan
  // permintaan, bertanya offset ke server (HEAD), dan meneruskan dari sana.
  const lastProgress = useRef(new Map<string, number>());
  useEffect(() => {
    if (!busy) return;
    const mark = (file?: { id: string }) => {
      if (file) lastProgress.current.set(file.id, Date.now());
    };
    const markAll = (started: { id: string }[]) => started.forEach(mark);
    uppy.on("upload-start", markAll);
    uppy.on("upload-progress", mark);
    const timer = setInterval(() => {
      for (const id of stalledFileIds(uppy.getFiles(), lastProgress.current, Date.now())) {
        lastProgress.current.set(id, Date.now()); // satu pemicu per STALL_MS
        setRetryStatus("No data for 90 seconds, reconnecting");
        uppy.pauseResume(id);
        setTimeout(() => uppy.pauseResume(id), 500);
      }
    }, 10_000);
    return () => {
      clearInterval(timer);
      uppy.off("upload-start", markAll);
      uppy.off("upload-progress", mark);
    };
  }, [uppy, busy]);

  useEffect(() => {
    const clearRetry = () => setRetryStatus(null);
    uppy.on("upload-progress", clearRetry);
    uppy.on("upload-success", clearRetry);
    uppy.on("complete", clearRetry);
    uppy.on("error", clearRetry);
    const onCancel = () => {
      clearRetry();
      setBusy(false);
    };
    uppy.on("cancel-all", onCancel);
    return () => {
      uppy.off("upload-progress", clearRetry);
      uppy.off("upload-success", clearRetry);
      uppy.off("complete", clearRetry);
      uppy.off("error", clearRetry);
      uppy.off("cancel-all", onCancel);
    };
  }, [uppy]);

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
    setError(null);
    const area = areaId.trim().toLowerCase();
    const name = areaName.trim();
    if (!area) {
      setError("Area ID is required.");
      return;
    }
    if (!AREA_ID_RE.test(area)) {
      setError(
        "Area ID must start with a lowercase letter or digit and contain only lowercase letters, digits and hyphens (max 40 characters)."
      );
      return;
    }
    if (!name) {
      setError("Area name is required.");
      return;
    }

    setBusy(true);
    try {
      const videos = files.map((f, i) => ({ name: f.name, size: f.size, role: roleOf(f, i) }));
      const key = JSON.stringify([area, name, videos]);
      if (last.current?.key !== key) {
        const job = await api.createJob({ area_id: area, area_name: name, videos });
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
      <PageHead crumbs={[{ label: "New map session" }]} title="New map session">
        Walk the area with your back to the wall, camera facing the room. Videos are uploaded in 8 MiB chunks.
      </PageHead>
      <div className="split">
      <Panel>
        <h2>Area</h2>
        <div className="grid gap-3.5">
          <div className="grid gap-1.5">
            <Label htmlFor="area-id">Area ID (lowercase letters, digits, hyphens)</Label>
            <Input
              id="area-id"
              value={areaId}
              onChange={(e) => setAreaId(e.target.value)}
              onBlur={() => setAreaId(areaId.trim().toLowerCase())}
              pattern="[a-z0-9][a-z0-9-]{0,39}"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              autoComplete="off"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="area-name">Area name</Label>
            <Input id="area-name" value={areaName} onChange={(e) => setAreaName(e.target.value)} />
          </div>
        </div>
      </Panel>
      <Panel>
        <h2>Videos</h2>
        <Dashboard uppy={uppy} hideUploadButton proudlyDisplayPoweredByUppy={false} height={300} width="100%" />
        {files.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow><TableHead>Video</TableHead><TableHead>Size</TableHead><TableHead>Role</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {files.map((f, i) => (
                <TableRow key={f.id}>
                  <TableCell>{f.name}</TableCell>
                  <TableCell className="num">{mb(f.size)}</TableCell>
                  <TableCell>
                    <Select
                      value={roleOf(f, i)}
                      onValueChange={(val) => setRoles({ ...roles, [f.id]: val as Role })}
                    >
                      <SelectTrigger className="w-28 text-xs" aria-label="Select role">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="peta">{ROLE.peta}</SelectItem>
                        <SelectItem value="uji">{ROLE.uji}</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <p className="muted">For a production map, mark every video as map. Keep this tab open until the upload finishes.</p>
        <div className="actions">
          <Button className="rounded-full" onClick={start} disabled={busy || files.length === 0}>
            <Icon name="upload" />
            {busy ? "Uploading..." : "Start upload"}
          </Button>
        </div>
        {retryStatus && <p className="notice" role="status" aria-live="polite">{retryStatus}</p>}
        {error && <p className="error" role="alert">{error}</p>}
      </Panel>
      </div>
    </>
  );
}
