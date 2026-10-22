"use client";
import Uppy from "@uppy/core";
import Dashboard from "@uppy/react/dashboard";
import Tus from "@uppy/tus";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ApiError, api, mb, ROLE } from "@/lib/api";
import {
  AREA_ID_MAX,
  AREA_NAME_MAX,
  normalizeAreaId,
  normalizeAreaName,
  validateAreaId,
  validateAreaName,
} from "@/lib/areaFields";
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
import { useT, type TranslationKey } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { Icon } from "@/lib/Icon";
import { PageHead } from "@/lib/PageHead";
import { RETRY_DELAYS, shouldRetryUpload } from "@/lib/uploadRetry";
import { lastUploadProtocol, probeFile, watchUploadProtocol } from "@/lib/uploadDiag";
import { clearSession, fileKey, loadSession, matchUrl, saveSession, type SavedSession } from "@/lib/uploadSession";
import "@uppy/core/css/style.min.css";
import "@uppy/dashboard/css/style.min.css";

const CHUNK = 8 * 1024 * 1024; // 8 MiB (kelipatan 256 KiB), toleran terhadap koneksi ponsel yang putus

type RetryHandler = (msg: string | null) => void;
type TranslateRef = React.RefObject<((k: TranslationKey, vars?: Record<string, string | number>) => string) | null>;

// Setelah galat tanpa respons: bila berkas video tidak lagi terbaca di offset terakhir, itu penyebabnya (bukan jaringan).
async function explainUnreadable(uppy: Uppy, say: RetryHandler, tRef: TranslateRef) {
  for (const f of uppy.getFiles()) {
    if (!f.progress.uploadStarted || f.progress.uploadComplete || !(f.data instanceof Blob)) continue;
    const at = f.progress.bytesUploaded || 0;
    const bad = await probeFile(f.data, at);
    // Bila sudah ada kemajuan lagi, unggahan pulih sendiri: jangan menimpa status dengan kabar basi.
    if (bad && (uppy.getFile(f.id)?.progress.bytesUploaded || 0) === at) {
      say(
        tRef.current
          ? tRef.current("new.cannotReadFile", { bad })
          : `Cannot read the video file (${bad}). Copy it to the Downloads folder, select it again and press Start upload.`,
      );
      return;
    }
  }
}

function createUppy(onRetryRef: React.RefObject<RetryHandler | null>, tRef: TranslateRef) {
  const uppy = new Uppy({
    autoProceed: false,
    restrictions: { allowedFileTypes: ["video/*"], maxNumberOfFiles: 4, maxFileSize: 2 * 1024 ** 3 },
  });
  uppy.use(Tus, {
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
      const proto = lastUploadProtocol();
      onRetryRef.current?.(
        typeof navigator !== "undefined" && !navigator.onLine
          ? tRef.current?.("new.offlineWaiting") ?? "Offline, waiting for connection"
          : tRef.current?.("new.connectionLostRetrying", {
              attempt: retryAttempt + 1,
              cause,
              proto: proto ? `, ${proto}` : "",
            }) ?? `Connection lost, retrying (attempt ${retryAttempt + 1}), ${cause}${proto ? `, ${proto}` : ""}`,
      );
      if (!err.originalResponse) {
        explainUnreadable(uppy, (msg) => onRetryRef.current?.(msg), tRef).catch(() => {});
      }
      return true;
    },
  });
  return uppy;
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

function focusField(id: "area-id" | "area-name") {
  const field = document.getElementById(id);
  field?.scrollIntoView({ block: "center" });
  field?.focus();
}

export default function NewSessionPage() {
  const router = useRouter();
  const t = useT();
  const { resolvedTheme } = useTheme();
  const tRef = useRef<((k: TranslationKey, vars?: Record<string, string | number>) => string) | null>(null);
  tRef.current = t;

  const [retryStatus, setRetryStatus] = useState<string | null>(null);
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  const onRetryRef = useRef<RetryHandler | null>(null);
  onRetryRef.current = setRetryStatus;
  const [uppy] = useState(() => createUppy(onRetryRef, tRef));
  const [files, setFiles] = useState<Picked[]>([]);
  const [roles, setRoles] = useState<Record<string, Role>>({});
  const [areaId, setAreaId] = useState("floor10");
  const [areaName, setAreaName] = useState("Lantai 10");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState({ id: false, name: false });
  const [serverFieldErrors, setServerFieldErrors] = useState<{
    area_id?: string;
    area_name?: string;
  }>({});
  // Pekerjaan dari klik sebelumnya. Isian sama = ulangi video yang gagal ke pekerjaan yang sama,
  // supaya pekerjaan tidak tertinggal setengah terunggah sampai kedaluwarsa 24 jam.
  const last = useRef<{ id: number; key: string } | null>(null);
  const sessionRef = useRef<SavedSession | null>(null);
  const offlinePaused = useRef(false);
  const wakeLockRef = useRef<any>(null);

  useEffect(() => watchUploadProtocol(), []);

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
          ? t("new.receivedOf", {
              received: mb(job.videos.reduce((sum, video) => sum + (video.received as number), 0)),
              total: mb(job.videos.reduce((sum, video) => sum + (video.size as number), 0)),
            })
          : "";
        setSessionNotice(
          t("new.unfinishedFound", { progress }),
        );
      })
      .catch(() => {
        if (!cancelled) clearSession();
      });

    return () => {
      cancelled = true;
    };
  }, [uppy, t]);

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
        // Abaikan penolakan wake lock (misalnya baterai lemah)
      }
    };
    acquireLock();

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        acquireLock();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Standar browser modern: returnValue perlu diisi agar dialog konfirmasi muncul.
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);

    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("beforeunload", onBeforeUnload);
      if (wakeLockRef.current) {
        wakeLockRef.current.release().catch(() => {});
        wakeLockRef.current = null;
      }
    };
  }, [busy]);

  // Pantau online/offline untuk pause/resume otomatis
  useEffect(() => {
    const onOffline = () => {
      if (busy) {
        offlinePaused.current = true;
        uppy.pauseAll();
        setRetryStatus(t("new.offlineWaiting"));
      }
    };

    const onOnline = () => {
      if (offlinePaused.current) {
        offlinePaused.current = false;
        setRetryStatus(null);
        uppy.resumeAll();
      }
    };

    window.addEventListener("offline", onOffline);
    window.addEventListener("online", onOnline);

    return () => {
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online", onOnline);
    };
  }, [uppy, busy, t]);

  useEffect(() => {
    const clearRetry = () =>
      setRetryStatus((current) =>
        current && (current.startsWith("Connection lost") || current.startsWith("Offline") || current.startsWith("Koneksi terputus")) ? null : current,
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

  const idValidation = validateAreaId(areaId);
  const nameValidation = validateAreaName(areaName);
  const idError =
    serverFieldErrors.area_id ??
    (touched.id && !idValidation.ok
      ? idValidation.messageKey
        ? t(idValidation.messageKey, idValidation.messageVars)
        : idValidation.message
      : null);
  const nameError =
    serverFieldErrors.area_name ??
    (touched.name && !nameValidation.ok
      ? nameValidation.messageKey
        ? t(nameValidation.messageKey, nameValidation.messageVars)
        : nameValidation.message
      : null);
  const idSuggestion = touched.id && !idValidation.ok ? idValidation.suggestion : undefined;
  const idLength = normalizeAreaId(areaId).length;
  const nameLength = normalizeAreaName(areaName).length;
  const idCounter =
    idLength >= Math.ceil(AREA_ID_MAX * 0.8) && idLength <= AREA_ID_MAX
      ? `${idLength} / ${AREA_ID_MAX}`
      : null;
  const nameCounter =
    nameLength >= Math.ceil(AREA_NAME_MAX * 0.8) && nameLength <= AREA_NAME_MAX
      ? `${nameLength} / ${AREA_NAME_MAX}`
      : null;

  async function start() {
    setError(null);
    setServerFieldErrors({});
    setTouched({ id: true, name: true });

    const idCheck = validateAreaId(areaId);
    const nameCheck = validateAreaName(areaName);
    if (!idCheck.ok) {
      focusField("area-id");
      return;
    }
    if (!nameCheck.ok) {
      focusField("area-name");
      return;
    }
    const area = idCheck.value;
    const name = nameCheck.value;

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
          t("new.missingVideos", { missing: missing.join(", ") }),
        );
      }
      clearSession();
      sessionRef.current = null;
      router.push(`/job/?id=${job.id}`);
    } catch (e) {
      if (e instanceof ApiError && (e.fields.area_id || e.fields.area_name)) {
        setServerFieldErrors({
          area_id: e.fields.area_id,
          area_name: e.fields.area_name,
        });
        focusField(e.fields.area_id ? "area-id" : "area-name");
      } else {
        setError((e as Error).message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead crumbs={[{ label: t("nav.newSession") }]} title={t("new.pageTitle")}>
        {t("new.pageDesc")}
      </PageHead>
      <div className="split">
      <Panel>
        <h2>{t("new.areaCard")}</h2>
        <div className="grid gap-3.5">
          <div className="grid gap-1.5">
            <Label htmlFor="area-id">{t("new.areaIdLabel")}</Label>
            <Input
              id="area-id"
              value={areaId}
              onChange={(e) => {
                setAreaId(e.target.value);
                if (serverFieldErrors.area_id) {
                  setServerFieldErrors((current) => ({ ...current, area_id: undefined }));
                }
              }}
              onBlur={() => {
                setAreaId((current) => normalizeAreaId(current));
                setTouched((current) => ({ ...current, id: true }));
              }}
              pattern="[a-z0-9][a-z0-9-]{0,39}"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              autoComplete="off"
              aria-invalid={idError ? true : undefined}
              aria-describedby="area-id-msg"
              aria-required="true"
            />
            <p id="area-id-msg" className="min-h-5" aria-live="polite">
              {idError ? (
                <span className="text-destructive">{idError}</span>
              ) : (
                <span className="muted">{t("new.areaIdHint")}</span>
              )}
              {idCounter && <span className="muted"> {idCounter}</span>}
            </p>
            {idSuggestion && (
              <Button
                type="button"
                variant="link"
                size="lg"
                className="underline cursor-pointer"
                onClick={() => {
                  setAreaId(idSuggestion);
                  setServerFieldErrors((current) => ({ ...current, area_id: undefined }));
                }}
              >
                {t("new.useSuggestion", { suggestion: idSuggestion })}
              </Button>
            )}
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="area-name">{t("new.areaNameLabel")}</Label>
            <Input
              id="area-name"
              value={areaName}
              onChange={(e) => {
                setAreaName(e.target.value);
                if (serverFieldErrors.area_name) {
                  setServerFieldErrors((current) => ({ ...current, area_name: undefined }));
                }
              }}
              onBlur={() => setTouched((current) => ({ ...current, name: true }))}
              aria-invalid={nameError ? true : undefined}
              aria-describedby="area-name-msg"
              aria-required="true"
            />
            <p id="area-name-msg" className="min-h-5" aria-live="polite">
              {nameError ? (
                <span className="text-destructive">{nameError}</span>
              ) : (
                <span className="muted">{t("new.areaNameHint")}</span>
              )}
              {nameCounter && <span className="muted"> {nameCounter}</span>}
            </p>
          </div>
        </div>
      </Panel>
      <Panel>
        <h2>{t("new.videosCard")}</h2>
        {sessionNotice && <p className="muted" role="status">{sessionNotice}</p>}
        <Dashboard uppy={uppy} hideUploadButton proudlyDisplayPoweredByUppy={false} height={300} width="100%" theme={resolvedTheme} />
        {files.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("new.videoCol")}</TableHead>
                <TableHead>{t("new.sizeCol")}</TableHead>
                <TableHead>{t("new.roleCol")}</TableHead>
              </TableRow>
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
                      <SelectTrigger className="w-28 text-xs cursor-pointer" aria-label={t("new.selectRoleAria")}>
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
        <p className="muted">{t("new.uploadTip")}</p>
        <div className="actions">
          <Button className="rounded-full cursor-pointer" onClick={start} disabled={busy || files.length === 0}>
            <Icon name="upload" />
            {busy ? t("new.uploading") : t("new.startUpload")}
          </Button>
        </div>
        {retryStatus && <p className="notice" role="status" aria-live="polite">{retryStatus}</p>}
        {error && <p className="error" role="alert">{error}</p>}
      </Panel>
      </div>
    </>
  );
}
