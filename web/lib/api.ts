// size dan uploaded null: pekerjaan dari manage job (CLI), videonya tidak lewat unggahan.
export type Video = {
  name: string;
  role: "peta" | "uji";
  size: number | null;
  uploaded: boolean | null;
  recorded_at?: string | null;
  received?: number | null;
  activity_at?: string | null;
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
  stalled?: boolean;
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

/** Drive fisik yang memuat disk virtual WSL, dari umpan yang ditulis autodeploy.sh. Tidak ada kalau umpan belum ada. */
export type HostDisk = {
  mount: string;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  percent: number;
  age_s: number;
  stale: boolean;
};

export type StorageDiagnostics = {
  maps: StorageLocation | null;
  data: StorageLocation | null;
  host?: HostDisk | null;
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

// Sesuai validasi server di server/uploads.py (JobIn.area_id)
export const AREA_ID_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;

export type ApiField = "area_id" | "area_name" | "videos";

const FIELD_LABELS: Record<string, string> = {
  area_id: "Area ID",
  area_name: "Area name",
  videos: "Videos",
};

type ApiIssue = {
  field: string;
  label: string;
  message: string;
  type: string;
};

/** Satu item 422 FastAPI menjadi pesan dan field asalnya. */
function parseIssue(item: unknown): ApiIssue | null {
  if (!item || typeof item !== "object") return null;
  const loc = Array.isArray((item as { loc?: unknown[] }).loc)
    ? (item as { loc: unknown[] }).loc
    : [];
  const field = loc.length > 0 ? String(loc[loc.length - 1]) : "";
  const label = FIELD_LABELS[field] ?? field;

  const type =
    typeof (item as { type?: unknown }).type === "string"
      ? (item as { type: string }).type
      : "";
  let message = "";
  if (type === "string_pattern_mismatch") {
    message = "has invalid characters or the wrong format";
  } else if (type === "string_too_long") {
    message = "is too long";
  } else if (type === "string_too_short") {
    message = "is too short";
  } else if (type === "missing") {
    message = "is required";
  } else if (
    typeof (item as { msg?: unknown }).msg === "string" &&
    (item as { msg: string }).msg
  ) {
    message = (item as { msg: string }).msg;
  }

  if (!message) return null;
  return { field, label, message, type };
}

export function formatApiError(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail.trim().length > 0) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const formatted = detail
      .map(parseIssue)
      .filter((issue): issue is ApiIssue => issue !== null)
      .map((issue) => (issue.label ? `${issue.label}: ${issue.message}` : issue.message));

    if (formatted.length > 0) {
      return formatted.join("; ");
    }
  }
  return `error ${status}`;
}

/** Pesan per field dari 422 FastAPI, tanpa label berkolon, siap dipasang di dekat kolom. */
export function fieldErrorsFromApi(detail: unknown): Partial<Record<ApiField, string>> {
  const fields: Partial<Record<ApiField, string>> = {};
  if (!Array.isArray(detail)) return fields;
  for (const item of detail) {
    const issue = parseIssue(item);
    if (!issue) continue;
    const field = issue.field;
    if (field === "area_id" || field === "area_name" || field === "videos") {
      fields[field] = fieldSentence(issue);
    }
  }
  return fields;
}

function fieldSentence(issue: ApiIssue): string {
  if (issue.type === "string_too_long") {
    if (issue.field === "area_id") return "Area ID is too long (maximum 40 characters).";
    if (issue.field === "area_name") return "Area name is too long (maximum 100 characters).";
  }
  if (issue.type === "string_too_short" || issue.type === "missing") {
    return `${issue.label} is required.`;
  }
  const sentence = issue.label ? `${issue.label} ${issue.message}` : issue.message;
  return /[.!?]$/.test(sentence) ? sentence : `${sentence}.`;
}

/** Galat HTTP dengan pesan yang sama seperti sebelumnya, plus pesan per field bila ada. */
export class ApiError extends Error {
  status: number;
  fields: Partial<Record<ApiField, string>>;

  constructor(message: string, status: number, fields: Partial<Record<ApiField, string>> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(path, { ...init, headers: { "Content-Type": "application/json" } });
  } catch {
    // Sesi Cloudflare Access habis: permintaan diarahkan ke halaman login lain asal dan gagal.
    throw new ApiError("Cannot reach the server. If your login session expired, reload the page.", 0);
  }
  if (!r.ok) {
    let detail = `error ${r.status}`;
    let fields: Partial<Record<ApiField, string>> = {};
    try {
      const body = await r.json();
      detail = formatApiError(body?.detail, r.status);
      fields = fieldErrorsFromApi(body?.detail);
    } catch {}
    throw new ApiError(detail, r.status, fields);
  }
  if (r.status === 204) return undefined as T; // DELETE tanpa isi
  return (await r.json()) as T;
}

export type HealthStatus = {
  status: "ok" | "no_map";
  area_id: string | null;
  map_version: number | null;
  map_images: number;
  device: string | null;
  aligned: boolean;
};

export type XY = [number, number];
export type NavNode = { id: string; x: number; y: number };
export type NavGraph = {
  frame: string;
  units: string;
  nodes: NavNode[];
  edges: [string, string][];
  targets: { node: string; name: string }[];
};
export type Room = { id: number; name: string; x: number; y: number };
export type EditKind = "add_edge" | "remove_edge" | "move_node";
export type RouteEdit = { id: number; kind: EditKind; a: XY; b: XY };
export type AreaGraph = {
  base: NavGraph;
  edits: RouteEdit[];
  rooms: Room[];
  draft: NavGraph;
  warnings: string[];
  unmatched_edits: number[];
  published_at: string | null;
};
export type PlanMeta = {
  origin_x: number;
  origin_y: number;
  res_m: number;
  width: number;
  height: number;
  trajectory: XY[];
};
export type StrokeMode = "paint" | "erase";
export type WalkableData = {
  cell_m: number;
  origin: XY;
  width: number;
  height: number;
  bits: string; // base64, row-major, LSB first, row 0 = lowest y
  walkable_cells: number;
  strokes: { id: number; mode: StrokeMode; radius: number; points_count: number }[];
  warnings: string[];
};
export type RouteResult =
  | { status: "ok"; points: XY[]; length_m: number }
  | { status: "unreachable" };

const area = (id: string) => `/api/areas/${encodeURIComponent(id)}`;
export const planImageUrl = (id: string) => `${area(id)}/plan.png`;
export const photoUrl = (id: string, [x, y]: XY) => `${area(id)}/photo?x=${x}&y=${y}`;

export const areaApi = {
  graph: (id: string) => call<AreaGraph>(`${area(id)}/graph`),
  plan: (id: string) => call<PlanMeta>(`${area(id)}/plan`),
  addRoom: (id: string, room: Omit<Room, "id">) =>
    call<Room>(`${area(id)}/rooms`, { method: "POST", body: JSON.stringify(room) }),
  editRoom: (id: string, roomId: number, patch: Partial<Omit<Room, "id">>) =>
    call<Room>(`${area(id)}/rooms/${roomId}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteRoom: (id: string, roomId: number) => call<void>(`${area(id)}/rooms/${roomId}`, { method: "DELETE" }),
  addEdit: (id: string, edit: Omit<RouteEdit, "id">) =>
    call<RouteEdit>(`${area(id)}/edits`, { method: "POST", body: JSON.stringify(edit) }),
  deleteEdit: (id: string, editId: number) => call<void>(`${area(id)}/edits/${editId}`, { method: "DELETE" }),
  walkable: (id: string) => call<WalkableData>(`${area(id)}/walkable`),
  addStroke: (id: string, stroke: { mode: StrokeMode; radius: number; points: XY[] }) =>
    call<{ id: number }>(`${area(id)}/strokes`, { method: "POST", body: JSON.stringify(stroke) }),
  deleteStroke: (id: string, strokeId: number) =>
    call<void>(`${area(id)}/strokes/${strokeId}`, { method: "DELETE" }),
  resetStrokes: (id: string) => call<void>(`${area(id)}/strokes`, { method: "DELETE" }),
  route: (id: string, from: XY, roomId: number) =>
    call<RouteResult>(`${area(id)}/route`, { method: "POST", body: JSON.stringify({ from, room_id: roomId }) }),
  publish: (id: string) =>
    call<{ published_at: string; warnings: string[] }>(`${area(id)}/publish-graph`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
};

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
  health: () => call<HealthStatus>("/health"),
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

export function formatDuration(
  started: string | null | undefined,
  finished: string | null | undefined,
  options?: { isRunning?: boolean; nowMs?: number }
): string {
  if (!started) return "-";
  if (!finished && !options?.isRunning) return "-";
  try {
    const s = new Date(started).getTime();
    if (isNaN(s)) return "-";
    const f = finished ? new Date(finished).getTime() : (options?.nowMs ?? Date.now());
    if (isNaN(f) || f < s) return "-";
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

export function formatRelativeTime(
  iso: string | null | undefined,
  nowMs: number = Date.now()
): string {
  if (!iso) return "-";
  try {
    const t = new Date(iso).getTime();
    if (isNaN(t)) return "-";
    const diffSec = Math.max(0, Math.floor((nowMs - t) / 1000));
    if (diffSec < 60) return `${diffSec}s`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m`;
    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d`;
  } catch {
    return "-";
  }
}
