import type { CalPointIn, CalRole } from "@/lib/api";

// Batas dan aturan sama dengan server/calibration.py dan server/calibration_api.py.
export const MAX_POINTS = 500;
export const MAX_ID_LEN = 40;
export const MIN_REFERENCE = 4;
export const MIN_SPREAD = 0.05;

export type ParsedPoint = { point_id: string; x_m: number; y_m: number };
export type ParsedPoints = { points: ParsedPoint[]; errors: { line: number; message: string }[] };

/** Tempel `point,x_m,y_m` per baris (pemisah koma, titik koma, atau tab); baris judul dilewati. */
export function parsePoints(text: string): ParsedPoints {
  const points: ParsedPoint[] = [];
  const errors: ParsedPoints["errors"] = [];
  const seen = new Set<string>();
  const lines = text.split(/\r?\n/);
  lines.forEach((raw, i) => {
    const line = raw.trim();
    if (!line) return;
    const cells = line.split(/[,;\t]/).map((c) => c.trim());
    if (points.length === 0 && /^point(_id)?$/i.test(cells[0])) return;
    const n = i + 1;
    if (cells.length !== 3) return void errors.push({ line: n, message: "columns" });
    const [id, xs, ys] = cells;
    const x = Number(xs);
    const y = Number(ys);
    if (!id || id.length > MAX_ID_LEN || /\s/.test(id)) {
      return void errors.push({ line: n, message: "id" });
    }
    if (xs === "" || ys === "" || !Number.isFinite(x) || !Number.isFinite(y)) {
      return void errors.push({ line: n, message: "number" });
    }
    if (seen.has(id)) return void errors.push({ line: n, message: "duplicate" });
    seen.add(id);
    points.push({ point_id: id, x_m: x, y_m: y });
  });
  if (points.length > MAX_POINTS) errors.push({ line: 0, message: "too_many" });
  return { points, errors };
}

/** Rasio nilai singular kedua/pertama koordinat acuan; mendekati 0 = nyaris segaris. */
export function pointSpread(points: { x_m: number; y_m: number }[]): number {
  const n = points.length;
  if (n < 2) return 0;
  const mx = points.reduce((s, p) => s + p.x_m, 0) / n;
  const my = points.reduce((s, p) => s + p.y_m, 0) / n;
  let a = 0;
  let b = 0;
  let c = 0;
  for (const p of points) {
    const dx = p.x_m - mx;
    const dy = p.y_m - my;
    a += dx * dx;
    b += dx * dy;
    c += dy * dy;
  }
  const mid = (a + c) / 2;
  const rad = Math.hypot((a - c) / 2, b);
  const l1 = mid + rad;
  const l2 = Math.max(mid - rad, 0);
  return l1 > 0 ? Math.sqrt(l2 / l1) : 0;
}

export type PointsProblem = "too_few_reference" | "collinear" | null;

export function pointsProblem(points: CalPointIn[]): PointsProblem {
  const refs = points.filter((p) => p.role === "reference");
  if (refs.length < MIN_REFERENCE) return "too_few_reference";
  if (pointSpread(refs) < MIN_SPREAD) return "collinear";
  return null;
}

export const withRoles = (points: ParsedPoint[], roles: Record<string, CalRole>): CalPointIn[] =>
  points.map((p) => ({ ...p, role: roles[p.point_id] ?? "reference" }));

/** Titik periksa: jarak dari koordinat dibanding jarak yang diukur dengan meteran. */
export function checkDistance(
  a: ParsedPoint | undefined,
  b: ParsedPoint | undefined,
  measured: number,
): { computed: number; diff: number; tolerance: number; ok: boolean } | null {
  if (!a || !b || a.point_id === b.point_id || !Number.isFinite(measured) || measured <= 0) {
    return null;
  }
  const computed = Math.hypot(a.x_m - b.x_m, a.y_m - b.y_m);
  const diff = Math.abs(computed - measured);
  const tolerance = Math.max(0.2, 0.02 * computed);
  return { computed, diff, tolerance, ok: diff <= tolerance };
}

/** Langkah sumbu "bagus" (1, 2, 5 x 10^k) supaya tanda meter di plot terbaca. */
export function niceStep(span: number, target = 5): number {
  const raw = span / target;
  if (!(raw > 0)) return 1;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const f = raw / pow;
  return (f >= 5 ? 5 : f >= 2 ? 2 : 1) * pow;
}
