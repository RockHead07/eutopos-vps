import type { Job } from "./api";

const FIXED_COLUMNS = [
  "id",
  "area_id",
  "status",
  "created_at",
  "report.version",
  "report.error",
] as const;

const KNOWN_NON_SCALAR = new Set([
  "network.uploads",
  "recording.warnings",
  "quality.gate.reasons",
]);

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function collectPaths(
  obj: Record<string, unknown>,
  prefix: string,
  objectPaths: Set<string>,
  arrayPaths: Set<string>,
  leafPaths: Set<string>,
): void {
  for (const [key, value] of Object.entries(obj)) {
    if (!prefix && (key === "version" || key === "error")) {
      continue;
    }
    const path = prefix ? `${prefix}.${key}` : key;
    if (Array.isArray(value)) {
      arrayPaths.add(path);
    } else if (isPlainObject(value)) {
      objectPaths.add(path);
      collectPaths(value, path, objectPaths, arrayPaths, leafPaths);
    } else {
      leafPaths.add(path);
    }
  }
}

export function reportColumns(jobs: Job[]): string[] {
  const objectPaths = new Set<string>();
  const arrayPaths = new Set<string>();
  const leafPaths = new Set<string>();

  for (const job of jobs) {
    const report = job.summary?.report;
    if (isPlainObject(report)) {
      collectPaths(report, "", objectPaths, arrayPaths, leafPaths);
    }
  }

  const dynamicCols = Array.from(leafPaths)
    .filter((p) => !objectPaths.has(p) && !arrayPaths.has(p) && !KNOWN_NON_SCALAR.has(p))
    .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

  return [...FIXED_COLUMNS, ...dynamicCols];
}

function escapeCell(raw: string): string {
  if (/[",\r\n]/.test(raw)) {
    return `"${raw.replace(/"/g, '""')}"`;
  }
  return raw;
}

function readPath(root: unknown, path: string): string {
  if (!isPlainObject(root)) return "";
  let cur: unknown = root;
  for (const part of path.split(".")) {
    if (!isPlainObject(cur) || !(part in cur)) return "";
    cur = cur[part];
  }
  if (cur === null || cur === undefined || typeof cur === "object") return "";
  return String(cur);
}

function cellValue(job: Job, col: string): string {
  if (col === "id") return String(job.id);
  if (col === "area_id") return job.area_id;
  if (col === "status") return job.status;
  if (col === "created_at") return job.created_at;
  const report = job.summary?.report;
  if (col === "report.version") {
    return report && report.version != null ? String(report.version) : "";
  }
  if (col === "report.error") {
    return report && typeof report.error === "string" ? report.error : "";
  }
  return readPath(report, col);
}

export function reportCsv(jobs: Job[]): string {
  const cols = reportColumns(jobs);
  const lines: string[] = [`# rows: ${jobs.length}`, cols.map(escapeCell).join(",")];
  for (const job of jobs) {
    lines.push(cols.map((col) => escapeCell(cellValue(job, col))).join(","));
  }
  return `${lines.join("\r\n")}\r\n`;
}
