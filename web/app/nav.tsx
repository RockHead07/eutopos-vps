"use client";
import Link from "@/lib/Link";
import { usePathname } from "next/navigation";
import { Icon } from "@/lib/Icon";

const LINKS = [
  { href: "/", label: "Overview", icon: "overview", match: (p: string) => p === "/" },
  { href: "/jobs/", label: "Jobs", icon: "stack", match: (p: string) => p.startsWith("/job") },
  { href: "/new/", label: "New map session", icon: "new-session", match: (p: string) => p.startsWith("/new") },
  { href: "/maps/", label: "Map versions", icon: "map-versions", match: (p: string) => p.startsWith("/maps") },
];

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
