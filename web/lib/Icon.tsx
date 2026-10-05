import { StatusBadge } from "@/components/StatusBadge";

/** Ikon dari public/icons. CSS mask, bukan <img>, supaya warnanya mengikuti teks (currentColor). */
export function Icon({ name }: { name: string }) {
  return <span className="icon" aria-hidden="true" style={{ maskImage: `url(/icons/${name}.svg)` }} />;
}

const VERSION_ICON: Record<string, string> = {
  published: "active-map",
  candidate: "inactive-map",
  retired: "inactive-map",
  rejected: "error-map",
};

/** Status versi peta: ikon dan teks, tidak hanya warna. */
export function VersionBadge({ status }: { status: string }) {
  return (
    <StatusBadge status={status}>
      {VERSION_ICON[status] && <Icon name={VERSION_ICON[status]} />}
      {status}
    </StatusBadge>
  );
}
