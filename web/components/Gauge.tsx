import { cn } from "@/lib/utils";

export type GaugeLevel = "ok" | "warn" | "bad";

const ARC = {
  ok: "stroke-forest",
  warn: "stroke-amber-600 dark:stroke-[var(--busy-fg)]",
  bad: "stroke-bad-fg",
};
const WORD = { ok: "OK", warn: "Low", bad: "Critical" };

const SIZE = 96;
const R = 38;
const C = 2 * Math.PI * R;
const SWEEP = 0.75; // busur 270 derajat, celah di bawah

/**
 * Pengukur melingkar. `fill` 0 sampai 100 menentukan panjang busur; angka besar di tengah adalah
 * `display`, bukan fill, supaya "132 GB free" terbaca langsung. Status selalu ditulis sebagai kata
 * (bukan hanya warna) kalau `level` diberikan.
 */
export function Gauge({
  label,
  fill,
  display,
  unit,
  level,
  caption,
}: {
  label: string;
  fill: number;
  display: string;
  unit: string;
  level?: GaugeLevel;
  caption?: string;
}) {
  const f = Math.min(100, Math.max(0, fill)) / 100;
  return (
    <div
      className="flex min-w-0 flex-col items-center gap-0.5 text-center"
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(f * 100)}
      aria-valuetext={`${display} ${unit}${level ? `, ${WORD[level]}` : ""}`}
    >
      <div className="relative" style={{ width: SIZE, height: SIZE * 0.86 }}>
        <svg
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          width={SIZE}
          height={SIZE}
          className="absolute left-0 top-0"
          aria-hidden="true"
        >
          <g transform={`rotate(135 ${SIZE / 2} ${SIZE / 2})`} fill="none" strokeWidth={8} strokeLinecap="round">
            <circle cx={SIZE / 2} cy={SIZE / 2} r={R} className="stroke-line" strokeDasharray={`${SWEEP * C} ${C}`} />
            {f > 0 && (
              <circle
                cx={SIZE / 2}
                cy={SIZE / 2}
                r={R}
                className={cn("transition-all duration-300", ARC[level ?? "ok"])}
                strokeDasharray={`${SWEEP * C * f} ${C}`}
              />
            )}
          </g>
        </svg>
        <div className="absolute inset-x-0 top-[31px] flex flex-col items-center leading-none">
          <span className="num text-xl font-semibold text-foreground">{display}</span>
          <span className="mt-1 text-[10px] text-muted-foreground">{unit}</span>
        </div>
      </div>
      <span className="text-[11px] font-medium text-foreground">{label}</span>
      {level && (
        <span
          className={cn(
            "text-[10px] font-semibold uppercase tracking-wide",
            level === "ok" && "text-forest",
            level === "warn" && "text-amber-700 dark:text-[var(--busy-fg)]",
            level === "bad" && "text-bad-fg",
          )}
        >
          {WORD[level]}
        </span>
      )}
      {caption && <span className="num text-[10px] text-muted-foreground">{caption}</span>}
    </div>
  );
}
