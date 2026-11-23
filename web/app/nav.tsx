"use client";
import Link from "@/lib/Link";
import { usePathname } from "next/navigation";
import { Icon } from "@/lib/Icon";
import { LINKS, type NavLink } from "@/lib/links";
import { useT } from "@/lib/i18n";
import { api } from "@/lib/api";
import { useSharedPoll } from "@/lib/usePoll";

const TOKEN_LINK: NavLink = {
  href: "/tokens/",
  labelKey: "nav.tokens",
  icon: "stack",
  match: (path) => path === "/tokens" || path === "/tokens/",
};

function useLinks() {
  const { data: me, error } = useSharedPoll(api.me, 60_000);
  return me?.is_admin && !error ? [...LINKS, TOKEN_LINK] : LINKS;
}

export function Nav() {
  const path = usePathname();
  const t = useT();
  const links = useLinks();
  return (
    <nav className="pills" aria-label={t("nav.main")}>
      {links.map((l) => (
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
  const links = useLinks();
  return (
    <nav
      className="mobile-nav"
      aria-label={t("nav.main")}
      style={{ gridTemplateColumns: `repeat(${links.length}, minmax(0, 1fr))` }}
    >
      {links.map((l) => (
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
