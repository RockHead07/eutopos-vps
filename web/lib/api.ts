// size dan uploaded null: pekerjaan dari manage job (CLI), videonya tidak lewat unggahan.
export type Video = {
  name: string;
  role: "peta" | "uji";
  size: number | null;
  uploaded: boolean | null;
  recorded_at?: string | null;
};
export type Summary = {
  run?: {
    map_images?: number;
    map_registered?: number;
    queries?: number;
    queries_localized?: number;
    t_map_s?: Record<string, number>; // detik per tahap peta (feature, pairs, matching, reconstruction)
  };
  inspect?: {
    parts?: { label: string; frames: number; ranges: string[] }[];
    queries?: number;
    accepted?: number;
    min_inliers?: number;
  };
};
export type Job = {
  id: number;
  area_id: string;
  status: string;
  stage: string | null;
  created_by: string;
  videos: Video[];
  summary: Summary | null;
  error: string | null;
  map_version_id: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  has_preview?: boolean;
};
export type Version = {
  id: number;
  area_id: string;
  version: number;
  status: string;
  created_at: string;
  published_by: string | null;
  job_id: number | null;
  has_report: boolean;
};
export type ServiceStatus = {
  area_id: string | null;
  map_version: number | null;
  reloading: boolean;
  reload_error: string | null;
};
export type NewJob = {
  area_id: string;
  area_name: string;
  videos: { name: string; role: "peta" | "uji"; size: number }[];
};
export type Me = {
  email: string;
  is_admin: boolean;
};

export type StorageLocation = {
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  percent: number;
};

export type StorageDiagnostics = {
  maps: StorageLocation | null;
  data: StorageLocation | null;
};

export type GpuTelemetry = {
  name: string | null;
  temperature_c: number | null;
  vram_used_mb: number | null;
  vram_total_mb: number | null;
};

export type SystemDiagnostics = {
  storage: StorageDiagnostics;
  gpu: GpuTelemetry | null;
  device: "cuda" | "cpu";
  uptime_s: number;
  area_id: string | null;
  map_version: number | null;
  reloading: boolean;
  reload_error: string | null;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(path, { ...init, headers: { "Content-Type": "application/json" } });
  } catch {
    // Sesi Cloudflare Access habis: permintaan diarahkan ke halaman login lain asal dan gagal.
    throw new Error("Cannot reach the server. If your login session expired, reload the page.");
  }
  if (!r.ok) {
    let detail = `error ${r.status}`;
    try {
      const body = await r.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new Error(detail);
  }
  return (await r.json()) as T;
}

export const api = {
  me: () => call<Me>("/api/me"),
  jobs: () => call<Job[]>("/api/jobs"),
  job: (id: number) => call<Job>(`/api/jobs/${id}`),
  createJob: (body: NewJob) => call<Job>("/api/jobs", { method: "POST", body: JSON.stringify(body) }),
  deleteJob: (id: number) => call<{ status: string }>(`/api/jobs/${id}`, { method: "DELETE" }),
  deleteVersion: (id: number) =>
    call<{ status: string; job_id?: number }>(`/api/versions/${id}`, { method: "DELETE" }),
  versions: () => call<Version[]>("/api/versions"),
  publish: (id: number) =>
    call<{ version: Version; reload: "started" | "other_area" }>(`/api/versions/${id}/publish`, {
      method: "POST",
    }),
  service: () => call<ServiceStatus>("/api/service"),
  system: () => call<SystemDiagnostics>("/api/system"),
};

// Peran video di API tetap peta/uji (kontrak data); yang ditampilkan bahasa Inggris.
export const ROLE: Record<string, string> = { peta: "map", uji: "test" };

export const mb = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(0)} MB`;

const dtf = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "-";
    return dtf.format(d);
  } catch {
    return "-";
  }
}

export function formatDuration(started: string | null | undefined, finished: string | null | undefined): string {
  if (!started || !finished) return "-";
  try {
    const s = new Date(started).getTime();
    const f = new Date(finished).getTime();
    if (isNaN(s) || isNaN(f) || f < s) return "-";
    const totalSec = Math.floor((f - s) / 1000);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const sec = totalSec % 60;
    if (h > 0) return `${h}h ${m}m ${sec}s`;
    if (m > 0) return `${m}m ${sec}s`;
    return `${sec}s`;
  } catch {
    return "-";
  }
}
