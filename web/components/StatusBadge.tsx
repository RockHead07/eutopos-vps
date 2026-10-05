import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Warna dari palet eutopos (globals.css). Status selalu ditulis sebagai teks, tidak hanya warna.
const TONE: Record<string, string> = {
  done: "bg-[var(--ok-bg)] text-[var(--ok-fg)]",
  published: "bg-[var(--ok-bg)] text-[var(--ok-fg)]",
  failed: "bg-[var(--bad-bg)] text-[var(--bad-fg)]",
  rejected: "bg-[var(--bad-bg)] text-[var(--bad-fg)]",
  running: "bg-[var(--busy-bg)] text-[var(--busy-fg)]",
  uploading: "bg-[var(--busy-bg)] text-[var(--busy-fg)]",
  queued: "bg-[var(--busy-bg)] text-[var(--busy-fg)]",
};
const IDLE = "bg-[var(--idle-bg)] text-[var(--idle-fg)]";

export function StatusBadge({ status, className, children }: { status: string; className?: string; children?: React.ReactNode }) {
  return (
    <Badge className={cn("h-auto rounded-lg px-2.5 py-0.5 text-[0.8rem] font-semibold", TONE[status] ?? IDLE, className)}>
      {children ?? status}
    </Badge>
  );
}
