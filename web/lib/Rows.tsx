"use client";
import { useT } from "@/lib/i18n";

/** Kerangka baris selama data pertama dimuat, pengganti teks "Loading...". */
export function Rows({ n = 3 }: { n?: number }) {
  const t = useT();
  return (
    <div className="rows" aria-label={t("generic.loading")}>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="skeleton row" />
      ))}
    </div>
  );
}
