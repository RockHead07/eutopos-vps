import type { StorageDiagnostics } from "@/lib/api";

export type FreeLevel = "ok" | "warn" | "bad";
export type FreeSource = "host" | "volume";

/**
 * Batas keras per sumber. "volume" = disk yang dilihat container: pekerja menolak membangun peta di
 * bawah 20 GB (MIN_FREE_BYTES di server/worker.py). "host" = drive Windows yang memuat disk virtual
 * WSL: aturan proyek menjaganya di atas 30 GB (tidak ditegakkan kode, hanya peringatan).
 */
export const HARD_LIMIT_GB: Record<FreeSource, number> = { volume: 20, host: 30 };
const WARN_FACTOR = 1.25; // peringatan di 125% batas keras (20 GB menjadi 25 GB, seperti sebelumnya)

export function freeLevel(gb: number, source: FreeSource): FreeLevel {
  const limit = HARD_LIMIT_GB[source];
  return gb < limit ? "bad" : gb < limit * WARN_FACTOR ? "warn" : "ok";
}

/**
 * Ruang yang benar-benar tersedia: yang terkecil di antara disk yang dilihat container dan drive
 * tuan rumah. Disk virtual WSL bisa menampilkan 900 GB bebas padahal drive Windows di bawahnya
 * hanya punya 132 GB, jadi angka container saja menyesatkan. Umpan tuan rumah yang basi diabaikan.
 */
export function effectiveFree(
  s: StorageDiagnostics | null | undefined,
): { gb: number; source: FreeSource; level: FreeLevel } | null {
  if (!s) return null;
  const host = s.host && !s.host.stale ? s.host.free_gb : null;
  const volumes = [s.maps?.free_gb, s.data?.free_gb].filter((v): v is number => v != null);
  const volume = volumes.length ? Math.min(...volumes) : null;
  const candidates: { gb: number; source: FreeSource }[] = [];
  if (volume !== null) candidates.push({ gb: volume, source: "volume" });
  if (host !== null) candidates.push({ gb: host, source: "host" });
  if (!candidates.length) return null;
  // Yang paling dekat ke batas kerasnya yang menentukan, bukan yang angkanya paling kecil: 25 GB di
  // drive tuan rumah (batas 30) lebih genting daripada 22 GB di volume (batas 20).
  const worst = candidates.reduce((a, b) =>
    a.gb - HARD_LIMIT_GB[a.source] <= b.gb - HARD_LIMIT_GB[b.source] ? a : b,
  );
  return { ...worst, level: freeLevel(worst.gb, worst.source) };
}
