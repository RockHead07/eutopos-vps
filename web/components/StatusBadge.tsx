"use client";
import React from "react";
import { Badge } from "@/components/ui/badge";
import { useT, type TranslationKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";

// Warna dari palet eutopos (globals.css). Status selalu ditulis sebagai teks, tidak hanya warna.
const TONE: Record<string, string> = {
  done: "bg-[var(--ok-bg)] text-[var(--ok-fg)]",
  published: "bg-[var(--ok-bg)] text-[var(--ok-fg)]",
  failed: "bg-[var(--bad-bg)] text-[var(--bad-fg)]",
  rejected: "bg-[var(--bad-bg)] text-[var(--bad-fg)]",
  stalled: "bg-[var(--bad-bg)] text-[var(--bad-fg)]",
  running: "bg-[var(--busy-bg)] text-[var(--busy-fg)]",
  uploading: "bg-[var(--busy-bg)] text-[var(--busy-fg)]",
  queued: "bg-[var(--busy-bg)] text-[var(--busy-fg)]",
  deleting: "bg-[var(--busy-bg)] text-[var(--busy-fg)]",
};
const IDLE = "bg-[var(--idle-bg)] text-[var(--idle-fg)]";

export function StatusBadge({
  status,
  icon,
  className,
  children,
}: {
  status: string;
  icon?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}) {
  const t = useT();
  const key = `status.${status}` as TranslationKey;
  const translated = t(key);
  const display = translated !== key ? translated : status;

  return (
    <Badge
      className={cn(
        "h-auto rounded-lg px-2.5 py-0.5 text-[0.8rem] font-semibold inline-flex items-center gap-1",
        TONE[status] ?? IDLE,
        className
      )}
    >
      {icon}
      {children ?? display}
    </Badge>
  );
}
