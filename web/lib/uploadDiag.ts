/** Diagnostik unggahan: kenapa permintaan gagal tanpa respons (berkas tak terbaca, atau protokol jaringan). */

const PROBE_BYTES = 64 * 1024;

/**
 * Nama galat bila berkas tidak bisa dibaca di offset itu (di Android, NotReadableError bila berkas berubah atau izinnya
 * dicabut; permintaan PATCH lalu gagal seketika tanpa pernah sampai ke server), null bila terbaca.
 */
export async function probeFile(data: Blob, offset: number): Promise<string | null> {
  const start = Math.max(0, Math.min(offset, data.size - 1));
  try {
    await data.slice(start, Math.min(data.size, start + PROBE_BYTES)).arrayBuffer();
    return null;
  } catch (e) {
    return (e as { name?: string } | null)?.name || "Error";
  }
}

let protocol: string | null = null;

/** Mencatat protokol HTTP permintaan /files/ terakhir (h3, h2, http/1.1). Memakai observer: buffer resource timing penuh setelah 250 entri. */
export function watchUploadProtocol(): void {
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        const r = e as PerformanceResourceTiming;
        if (r.name.includes("/files/") && r.nextHopProtocol) protocol = r.nextHopProtocol;
      }
    }).observe({ type: "resource", buffered: true });
  } catch {
    // PerformanceObserver tidak tersedia: diagnostik protokol dilewati
  }
}

export function lastUploadProtocol(): string | null {
  return protocol;
}
