"use client";

import { niceStep } from "@/lib/calibration";
import type { CalRow } from "@/lib/api";
import { useT } from "@/lib/i18n";

const W = 640;
const H_MAX = 360;
const H_MIN = 150;
const PAD = 36;

type Pt = { x: number; y: number };

/** Lingkaran = acuan, belah ketupat = uji. Kosong = terukur, terisi = hasil lokalisasi. */
function Marker({ at, role, filled }: { at: Pt; role: CalRow["role"]; filled: boolean }) {
  const common = {
    fill: filled ? "var(--primary)" : "var(--card)",
    stroke: filled ? "var(--card)" : "var(--foreground)",
    strokeWidth: 1.5,
  };
  if (role === "reference") return <circle cx={at.x} cy={at.y} r={5} {...common} />;
  const r = 6.5;
  const d = `M${at.x},${at.y - r} L${at.x + r},${at.y} L${at.x},${at.y + r} L${at.x - r},${at.y} Z`;
  return <path d={d} {...common} />;
}

export function CalibrationPlot({ rows }: { rows: CalRow[] }) {
  const t = useT();
  const xs: number[] = [];
  const ys: number[] = [];
  for (const r of rows) {
    xs.push(r.x_m);
    ys.push(r.y_m);
    if (r.observed_x !== null && r.observed_y !== null) {
      xs.push(r.observed_x);
      ys.push(r.observed_y);
    }
  }
  if (xs.length === 0) return null;
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const spanX = Math.max(Math.max(...xs) - minX, 1);
  const spanY = Math.max(Math.max(...ys) - minY, 1);
  const k = Math.min((W - 2 * PAD) / spanX, (H_MAX - 2 * PAD) / spanY); // px per meter, sumbu sama
  const H = Math.max(H_MIN, spanY * k + 2 * PAD); // koridor panjang tidak menyisakan ruang kosong
  const px = (x: number) => PAD + (x - minX) * k;
  const py = (y: number) => H - PAD - (y - minY) * k; // y ke atas
  // tanda sumbu tidak lebih rapat dari 56 px (x) dan 26 px (y), supaya angkanya tidak bertumpuk
  const stepX = niceStep(spanX, Math.max(1, Math.floor((spanX * k) / 56)));
  const stepY = niceStep(spanY, Math.max(1, Math.floor((spanY * k) / 26)));
  const ticksX = Array.from({ length: Math.floor(spanX / stepX) + 1 }, (_, i) => Math.ceil(minX / stepX) * stepX + i * stepX).filter((v) => v <= minX + spanX + 1e-9);
  const ticksY = Array.from({ length: Math.floor(spanY / stepY) + 1 }, (_, i) => Math.ceil(minY / stepY) * stepY + i * stepY).filter((v) => v <= minY + spanY + 1e-9);

  return (
    <figure className="m-0 flex flex-col gap-2">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("cal.plotAlt")} className="w-full h-auto">
        <rect x={0} y={0} width={W} height={H} rx={12} fill="var(--card)" stroke="var(--border)" />
        {ticksX.map((v) => (
          <g key={`x${v}`}>
            <line x1={px(v)} x2={px(v)} y1={PAD / 2} y2={H - PAD} stroke="var(--border)" strokeWidth={1} />
            <text x={px(v)} y={H - PAD + 14} textAnchor="middle" fontSize={10} fill="var(--muted-foreground)">{+v.toFixed(2)}</text>
          </g>
        ))}
        {ticksY.map((v) => (
          <g key={`y${v}`}>
            <line x1={PAD} x2={W - PAD / 2} y1={py(v)} y2={py(v)} stroke="var(--border)" strokeWidth={1} />
            <text x={PAD - 6} y={py(v) + 3} textAnchor="end" fontSize={10} fill="var(--muted-foreground)">{+v.toFixed(2)}</text>
          </g>
        ))}
        <text x={W - PAD / 2} y={H - 6} textAnchor="end" fontSize={10} fill="var(--muted-foreground)">x (m)</text>
        <text x={6} y={14} fontSize={10} fill="var(--muted-foreground)">y (m)</text>
        {rows.map((r) => {
          const m = { x: px(r.x_m), y: py(r.y_m) };
          const o = r.observed_x !== null && r.observed_y !== null ? { x: px(r.observed_x), y: py(r.observed_y) } : null;
          return (
            <g key={r.point_id}>
              <title>{`${r.point_id}: ${r.error_m === null ? t("cal.noObservation") : `${r.error_m.toFixed(2)} m`}`}</title>
              {o && <line x1={m.x} y1={m.y} x2={o.x} y2={o.y} stroke="var(--bad-fg)" strokeWidth={1.5} />}
              <Marker at={m} role={r.role} filled={false} />
              {o && <Marker at={o} role={r.role} filled />}
              <text x={m.x + 9} y={m.y - 8} fontSize={11} fill="var(--foreground)">{r.point_id}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>{t("cal.legendReference")}</span>
        <span>{t("cal.legendTest")}</span>
        <span>{t("cal.legendMeasured")}</span>
        <span>{t("cal.legendLocalized")}</span>
      </figcaption>
    </figure>
  );
}
