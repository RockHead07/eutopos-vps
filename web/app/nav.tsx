"use client";
import Link from "@/lib/Link";
import { usePathname } from "next/navigation";
import { Icon } from "@/lib/Icon";
import { LINKS } from "@/lib/links";

export function Nav() {
  const path = usePathname();
  return (
    <nav className="pills" aria-label="Main">
      {LINKS.map((l) => (
        <Link key={l.href} href={l.href} className="pill" aria-current={l.match(path) ? "page" : undefined}>
          <Icon name={l.icon} />
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
