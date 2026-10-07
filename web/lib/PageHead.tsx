"use client";
import { api } from "@/lib/api";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { usePoll } from "@/lib/usePoll";

type Crumb = { label: string; href?: string };

/** Chip status layanan. Isi dari /api/service (bukan teks tetap), jadi sama di setiap halaman. */
function ServiceChips() {
  const { data: s, error } = usePoll(api.service, 5000);
  return (
    <div className="chips">
      {s?.area_id && (
        <span className="chip"><Icon name="active-map" />Serving {s.area_id}{s.map_version !== null && ` v${s.map_version}`}</span>
      )}
      <span className={`chip ${error ? "bad" : s ? "ok" : ""}`} title="From /api/service, refreshed every 5 seconds">
        <span className="dot" aria-hidden="true" />
        {error ? "VPS unreachable" : s ? "VPS online" : "Checking..."}
      </span>
    </div>
  );
}

/** Kepala halaman yang sama di semua halaman: breadcrumb, judul, keterangan, dan chip status. */
export function PageHead({
  crumbs,
  title,
  children,
  controls,
}: {
  crumbs: Crumb[];
  title: string;
  children?: React.ReactNode;
  controls?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <p className="crumbs">
          <Link href="/">eutopos</Link>
          {crumbs.map((c) => (
            <span key={c.label} className="crumb">
              <span aria-hidden="true">/</span>
              {c.href ? <Link href={c.href}>{c.label}</Link> : <span>{c.label}</span>}
            </span>
          ))}
        </p>
        <h1>{title}</h1>
        {children && <div className="muted">{children}</div>}
      </div>
      <div className="flex flex-col gap-2.5 items-start md:items-end">
        <ServiceChips />
        {controls}
      </div>
    </div>
  );
}
