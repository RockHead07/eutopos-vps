"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Overview", match: (p: string) => p === "/" },
  { href: "/jobs/", label: "Jobs", match: (p: string) => p.startsWith("/job") },
  { href: "/new/", label: "New map session", match: (p: string) => p.startsWith("/new") },
  { href: "/maps/", label: "Map versions", match: (p: string) => p.startsWith("/maps") },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="pills" aria-label="Main">
      {LINKS.map((l) => (
        <Link key={l.href} href={l.href} className="pill" aria-current={l.match(path) ? "page" : undefined}>
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
