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
import { RETRY_DELAYS, shouldRetryUpload, stalledFileIds } from "@/lib/uploadRetry";
import { clearSession, fileKey, loadSession, matchUrl, saveSession, type SavedSession } from "@/lib/uploadSession";
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
    retryDelays: RETRY_DELAYS,
    allowedMetaFields: ["job_id", "name"], // dicocokkan hook pre-create dengan video terdaftar
    // Unggahan lama terikat ke pekerjaan lamanya: jangan dilanjutkan ke pekerjaan baru.
    storeFingerprintForResuming: false,
    // Aturan sendiri (lib/uploadRetry.ts), bukan next(err): aturan bawaan tidak mengulang 429 dan berhenti saat offline.
    onShouldRetry(err, retryAttempt) {
      const status = err.originalResponse?.getStatus();
      if (!shouldRetryUpload(status)) {
        onRetryRef.current?.(null);
        return false;
      }
      const cause = err.originalResponse
        ? `server answered ${status}`
        : "no response from the server";
      onRetryRef.current?.(
        typeof navigator !== "undefined" && !navigator.onLine
          ? "Offline, waiting for connection"
          : `Connection lost, retrying (attempt ${retryAttempt + 1}), ${cause}`,
      );
      return true;
    },
  });
}

type Role = "peta" | "uji";
type Picked = { id: string; name: string; size: number };

function fileIdentity(file: { name?: string; size?: number | null; data?: unknown }) {
  if (typeof file.name !== "string" || typeof file.size !== "number") return null;
  const data = file.data;
  const lastModified =
    data && typeof data === "object" && "lastModified" in data
      ? (data as { lastModified?: unknown }).lastModified
      : undefined;
  return {
    name: file.name,
    size: file.size,
    lastModified: typeof lastModified === "number" ? lastModified : undefined,
  };
}

export default function NewSessionPage() {
  const router = useRouter();
  const [retryStatus, setRetryStatus] = useState<string | null>(null);
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
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
  const sessionRef = useRef<SavedSession | null>(null);
  const offlinePaused = useRef(false);
  const wakeLockRef = useRef<any>(null);

  useEffect(() => {
    const saved = loadSession(Date.now());
    if (!saved) return;

    let cancelled = false;
    api
      .job(saved.jobId)
      .then((job) => {
        if (cancelled) return;
        if (job.status !== "uploading" || !job.videos.some((video) => !video.uploaded)) {
          clearSession();
          return;
        }

        sessionRef.current = saved;
        last.current = { id: saved.jobId, key: saved.key };
        uppy.setMeta({ job_id: String(saved.jobId) });
        setAreaId(saved.areaId);
        setAreaName(saved.areaName);

        const progressKnown =
          job.videos.length > 0 &&
          job.videos.every(
            (video) =>
              typeof video.size === "number" &&
              Number.isFinite(video.size) &&
              typeof video.received === "number" &&
              Number.isFinite(video.received),
          );
        const progress = progressKnown
          ? `: ${mb(job.videos.reduce((sum, video) => sum + (video.received as number), 0))} of ${mb(job.videos.reduce((sum, video) => sum + (video.size as number), 0))} received`
          : "";
        setSessionNotice(
          `Unfinished upload found${progress}. Select the same video file again and press Start upload to continue.`,
        );
      })
      .catch(() => {
        if (!cancelled) clearSession();
      });

    return () => {
      cancelled = true;
    };
  }, [uppy]);

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

  useEffect(() => {
    if (!busy) return;

    const handleOffline = () => {
      if (offlinePaused.current) return;
      offlinePaused.current = true;
      uppy.pauseAll();
      setRetryStatus("Offline, waiting for connection");
    };
    const handleOnline = () => {
      if (!offlinePaused.current) return;
      offlinePaused.current = false;
      uppy.resumeAll();
      setRetryStatus(null);
    };

    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    uppy.on("is-offline", handleOffline);
    uppy.on("back-online", handleOnline);
    if (!navigator.onLine) handleOffline();

    return () => {
      offlinePaused.current = false;
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
      uppy.off("is-offline", handleOffline);
      uppy.off("back-online", handleOnline);
    };
  }, [uppy, busy]);

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
    const clearRetry = () =>
      setRetryStatus((current) =>
        current === "Offline, waiting for connection" &&
        typeof navigator !== "undefined" &&
        !navigator.onLine
          ? current
          : null,
      );
    uppy.on("upload-progress", clearRetry);
    uppy.on("upload-success", clearRetry);
    uppy.on("complete", clearRetry);
    uppy.on("error", clearRetry);
    const onCancel = () => {
      setRetryStatus(null);
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
    const saveUploadUrl = (file: ReturnType<typeof uppy.getFile> | undefined) => {
      const session = sessionRef.current;
      const currentFile = file && uppy.getFile(file.id);
      const identity = currentFile && fileIdentity(currentFile);
      const uploadUrl = currentFile?.tus?.uploadUrl;
      if (!session || !identity || typeof uploadUrl !== "string" || !uploadUrl) return;
      if (!session.videos.some((video) => video.name === identity.name && video.size === identity.size)) {
        return;
      }

      const key = fileKey(identity);
      if (session.urls[key] === uploadUrl) return;
      const updated = {
        ...session,
        urls: { ...session.urls, [key]: uploadUrl },
        savedAt: Date.now(),
      };
      sessionRef.current = updated;
      saveSession(updated);
    };

    uppy.on("upload-progress", saveUploadUrl);
    return () => {
      uppy.off("upload-progress", saveUploadUrl);
    };
  }, [uppy]);

  useEffect(() => {
    const sync = () =>
      setFiles(uppy.getFiles().map((f) => ({ id: f.id, name: f.name ?? "", size: f.size ?? 0 })));
    const restoreFile = (file: ReturnType<typeof uppy.getFile>) => {
      const session = sessionRef.current;
      const identity = fileIdentity(file);
      if (!session || !identity) return;

      const video = session.videos.find((item) => item.name === identity.name && item.size === identity.size);
      if (video && (video.role === "peta" || video.role === "uji")) {
        setRoles((current) => ({ ...current, [file.id]: video.role as Role }));
      }

      const uploadUrl = matchUrl(session, identity);
      if (uploadUrl) {
        uppy.setFileState(file.id, { tus: { ...file.tus, uploadUrl } });
      }
    };
    uppy.on("file-added", sync);
    uppy.on("file-added", restoreFile);
    uppy.on("file-removed", sync);
    return () => {
      uppy.off("file-added", sync);
      uppy.off("file-added", restoreFile);
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
        clearSession();
        for (const file of uppy.getFiles()) {
          if (file.tus?.uploadUrl) {
            uppy.setFileState(file.id, { tus: { ...file.tus, uploadUrl: undefined } });
          }
        }
        const session: SavedSession = {
          jobId: job.id,
          key,
          areaId: area,
          areaName: name,
          videos,
          urls: {},
          savedAt: Date.now(),
        };
        sessionRef.current = session;
        saveSession(session);
        setSessionNotice(null);
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
      clearSession();
      sessionRef.current = null;
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
        {sessionNotice && <p className="muted" role="status">{sessionNotice}</p>}
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
