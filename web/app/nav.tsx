"use client";
import Link from "@/lib/Link";
import { usePathname } from "next/navigation";
import { Icon } from "@/lib/Icon";
import { LINKS } from "@/lib/links";
import { useT } from "@/lib/i18n";

export function Nav() {
  const path = usePathname();
  const t = useT();
  return (
    <nav className="pills" aria-label={t("nav.main")}>
      {LINKS.map((l) => (
        <Link key={l.href} href={l.href} className="pill" aria-current={l.match(path) ? "page" : undefined}>
          <Icon name={l.icon} />
          {t(l.labelKey)}
        </Link>
      ))}
    </nav>
  );
}

export function MobileNav() {
  const path = usePathname();
  const t = useT();
  return (
    <nav className="mobile-nav" aria-label={t("nav.main")}>
      {LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className="mobile-nav-link"
          aria-current={l.match(path) ? "page" : undefined}
        >
          <Icon name={l.icon} />
          <span>{t(l.labelKey)}</span>
        </Link>
      ))}
    </nav>
  );
}
