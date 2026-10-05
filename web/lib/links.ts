/** Tujuan navigasi: dipakai pil di atas (app/nav.tsx) dan dock ikon di kiri (app/rail.tsx). */
export const LINKS = [
  { href: "/", label: "Overview", icon: "overview", match: (p: string) => p === "/" },
  { href: "/jobs/", label: "Jobs", icon: "stack", match: (p: string) => p.startsWith("/job") },
  { href: "/new/", label: "New map session", icon: "new-session", match: (p: string) => p.startsWith("/new") },
  { href: "/maps/", label: "Map versions", icon: "map-versions", match: (p: string) => p.startsWith("/maps") },
];
