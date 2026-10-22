import type { TranslationKey } from "./i18n";

export interface NavLink {
  href: string;
  labelKey: TranslationKey;
  icon: string;
  match: (p: string) => boolean;
}

/** Tujuan navigasi: dipakai pil di atas (app/nav.tsx) dan dock ikon di kiri (app/rail.tsx). */
export const LINKS: NavLink[] = [
  { href: "/", labelKey: "nav.overview", icon: "overview", match: (p: string) => p === "/" },
  { href: "/jobs/", labelKey: "nav.jobs", icon: "stack", match: (p: string) => p.startsWith("/job") },
  { href: "/new/", labelKey: "nav.newSession", icon: "new-session", match: (p: string) => p.startsWith("/new") },
  { href: "/maps/", labelKey: "nav.mapVersions", icon: "map-versions", match: (p: string) => p.startsWith("/maps") },
];
