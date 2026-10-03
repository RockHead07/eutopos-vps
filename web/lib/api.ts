// size dan uploaded null: pekerjaan dari manage job (CLI), videonya tidak lewat unggahan.
export type Video = { name: string; role: "peta" | "uji"; size: number | null; uploaded: boolean | null };
export type Summary = {
  run?: { map_images?: number; map_registered?: number; queries?: number; queries_localized?: number };
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
  jobs: () => call<Job[]>("/api/jobs"),
  job: (id: number) => call<Job>(`/api/jobs/${id}`),
  createJob: (body: NewJob) => call<Job>("/api/jobs", { method: "POST", body: JSON.stringify(body) }),
  versions: () => call<Version[]>("/api/versions"),
  publish: (id: number) =>
    call<{ version: Version; reload: "started" | "other_area" }>(`/api/versions/${id}/publish`, {
      method: "POST",
    }),
  service: () => call<ServiceStatus>("/api/service"),
};

// Peran video di API tetap peta/uji (kontrak data); yang ditampilkan bahasa Inggris.
export const ROLE: Record<string, string> = { peta: "map", uji: "test" };

export const mb = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(0)} MB`;
