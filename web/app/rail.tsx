"use client";
import Link from "@/lib/Link";
import { usePathname } from "next/navigation";
import { Icon } from "@/lib/Icon";
import { LINKS } from "@/lib/links";

/**
 * Dock ikon di kiri, hanya tampil di layar lebar (globals.css). Pil di atas tetap navigasi utama:
 * dock ini jalan pintas visual, jadi disembunyikan dari pembaca layar dan urutan Tab supaya tidak ganda.
 */
export function Rail() {
  const path = usePathname();
  return (
    <nav className="rail" aria-hidden="true">
      {LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          tabIndex={-1}
          className="rail-link"
          data-tip={l.label}
          aria-current={l.match(path) ? "page" : undefined}
        >
          <Icon name={l.icon} />
        </Link>
      ))}
    </nav>
  );
}
