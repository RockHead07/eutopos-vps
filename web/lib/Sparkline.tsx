import Link from "@/lib/Link";

export type SparkPoint = { id: number; value: number; tip: string };

/**
 * Grafik garis dan area satu seri, tanpa pustaka. Garis memakai SVG, titik hover memakai tautan HTML
 * (tooltip dari CSS [data-tip]). Sumbu x = urutan job, bukan waktu. Nilai asli dari data, tidak dikarang.
 */
export function Sparkline({ points }: { points: SparkPoint[] }) {
  if (points.length === 0) return null;
  const vals = points.map((p) => p.value);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const span = hi - lo || 1;
  const x = (i: number) => (points.length === 1 ? 50 : 6 + (i * 88) / (points.length - 1));
  // 8 sampai 32 dari 40: ruang di atas dan bawah supaya titik tidak terpotong
  const y = (v: number) => (hi === lo ? 20 : 32 - ((v - lo) / span) * 24);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(2)} ${y(p.value).toFixed(2)}`).join(" ");
  const area = `${line} L${x(points.length - 1).toFixed(2)} 40 L${x(0).toFixed(2)} 40 Z`;
  return (
    <div className="spark">
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true">
        {points.length > 1 && <path className="spark-area" d={area} />}
        {points.length > 1 && <path className="spark-line" d={line} />}
      </svg>
      {points.map((p, i) => (
        <Link
          key={p.id}
          href={`/job/?id=${p.id}`}
          className={i === points.length - 1 ? "spark-dot latest" : "spark-dot"}
          style={{ left: `${x(i)}%`, top: `${(y(p.value) / 40) * 100}%` }}
          data-tip={p.tip}
          aria-label={p.tip}
        />
      ))}
    </div>
  );
}
