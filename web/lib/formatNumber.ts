// Format angka mengikuti bahasa antarmuka (id: 667.443 dan 24,645; en: 667,443 dan 24.645).
const formats = new Map<string, Intl.NumberFormat>();

export function formatNumber(
  value: number | null | undefined,
  locale: string,
  digits = 0,
): string {
  if (value == null || !Number.isFinite(value)) return "-";
  const loc = locale === "id" ? "id-ID" : "en-US";
  const key = `${loc}:${digits}`;
  let f = formats.get(key);
  if (!f) {
    f = new Intl.NumberFormat(loc, { minimumFractionDigits: digits, maximumFractionDigits: digits });
    formats.set(key, f);
  }
  return f.format(value);
}
