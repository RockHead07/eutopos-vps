/** Aturan ulang dan pengawas unggahan tus (halaman New map session). Fungsi murni supaya bisa diuji tanpa browser. */

/** Tanpa kemajuan byte selama ini, unggahan dianggap menggantung dan dipicu ulang. Lebih panjang dari jeda ulang terbesar (60 s). */
export const STALL_MS = 90_000;

/**
 * Apakah unggahan diulang setelah galat. `status` adalah kode HTTP respons, atau undefined kalau tidak ada
 * respons (koneksi putus). Aturan bawaan tus-js-client tidak mengulang 4xx selain 409 dan 423, dan berhenti
 * sama sekali saat navigator.onLine false; di sini 429 diulang dan koneksi putus selalu diulang, dengan jeda
 * dari retryDelays sebagai batas.
 */
export function shouldRetryUpload(status: number | undefined): boolean {
  if (status === 401 || status === 403 || status === 413) return false; // sesi habis atau berkas ditolak: mengulang tidak membantu
  if (status == null || status === 0) return true;
  return status >= 500 || status === 409 || status === 423 || status === 429;
}

type Watched = {
  id: string;
  isPaused?: boolean;
  error?: string | null; // berkas yang sudah gagal tidak dihidupkan lagi oleh pengawas
  progress: { uploadStarted?: number | null; uploadComplete?: boolean };
};

/** ID berkas yang sedang diunggah tetapi tidak ada kemajuan byte selama stallMs. */
export function stalledFileIds(
  files: Watched[],
  lastProgress: ReadonlyMap<string, number>,
  now: number,
  stallMs: number = STALL_MS,
): string[] {
  return files
    .filter((f) => f.progress.uploadStarted && !f.progress.uploadComplete && !f.isPaused && !f.error)
    .filter((f) => now - (lastProgress.get(f.id) ?? f.progress.uploadStarted ?? now) > stallMs)
    .map((f) => f.id);
}
