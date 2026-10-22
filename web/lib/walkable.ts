import type { WalkableData } from "@/lib/api";

/** Bit sel `i` (row-major, LSB dulu, baris 0 = y terendah), sama dengan server/walkable.py encode(). */
export function decodeBits(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export const cellOn = (bits: Uint8Array, i: number) => (bits[i >> 3] >> (i & 7)) & 1;

export function countCells(bits: Uint8Array, n: number): number {
  let c = 0;
  for (let i = 0; i < n; i++) c += cellOn(bits, i);
  return c;
}

/** Overlay hijau (forest #5A7863, transparan) dari grid rencana sebagai data URL; baris 0 = dasar gambar. */
export function overlayImage(w: Pick<WalkableData, "width" | "height" | "bits">): string {
  const canvas = document.createElement("canvas");
  canvas.width = w.width;
  canvas.height = w.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  const bits = decodeBits(w.bits);
  const img = ctx.createImageData(w.width, w.height);
  for (let row = 0; row < w.height; row++) {
    const dst = (w.height - 1 - row) * w.width;
    for (let col = 0; col < w.width; col++) {
      if (!cellOn(bits, row * w.width + col)) continue;
      const k = (dst + col) * 4;
      img.data[k] = 0x5a;
      img.data[k + 1] = 0x78;
      img.data[k + 2] = 0x63;
      img.data[k + 3] = 105;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL();
}
