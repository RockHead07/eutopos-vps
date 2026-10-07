"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { api, type Job } from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
const ONE_DAY_MS = 24 * 60 * 60 * 1000;
const SEEN_KEY = "eutopos.notifications.seenAt";

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

function formatRelative(iso: string): string {
  try {
    const time = new Date(iso).getTime();
    if (isNaN(time)) return "-";
    const diffSec = Math.round((time - Date.now()) / 1000);
    const absSec = Math.abs(diffSec);
    if (absSec < 60) return "just now";
    const diffMin = Math.round(diffSec / 60);
    if (Math.abs(diffMin) < 60) return rtf.format(diffMin, "minute");
    const diffHours = Math.round(diffMin / 60);
    if (Math.abs(diffHours) < 24) return rtf.format(diffHours, "hour");
    const diffDays = Math.round(diffHours / 24);
    if (Math.abs(diffDays) < 30) return rtf.format(diffDays, "day");
    const diffMonths = Math.round(diffDays / 30);
    return rtf.format(diffMonths, "month");
  } catch {
    return "-";
  }
}

export function Notifications() {
  const { data: jobs } = usePoll(api.jobs, 10000);
  const [seenAt, setSeenAt] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(SEEN_KEY);
      if (stored) setSeenAt(stored);
    } catch {}
  }, []);

  const eligibleJobs = useMemo(() => {
    if (!jobs) return [];
    const now = Date.now();
    return jobs
      .filter((j) => {
        if (j.status !== "done" && j.status !== "failed") return false;
        if (!j.finished_at) return false;
        const finishedTime = new Date(j.finished_at).getTime();
        if (isNaN(finishedTime)) return false;
        return now - finishedTime <= SEVEN_DAYS_MS;
      })
      .sort((a, b) => new Date(b.finished_at!).getTime() - new Date(a.finished_at!).getTime());
  }, [jobs]);

  const unreadCount = useMemo(() => {
    if (!eligibleJobs.length) return 0;
    const now = Date.now();
    const threshold = seenAt ? new Date(seenAt).getTime() : now - ONE_DAY_MS;
    return eligibleJobs.filter((j) => {
      const finishedTime = new Date(j.finished_at!).getTime();
      return finishedTime > threshold;
    }).length;
  }, [eligibleJobs, seenAt]);

  const items = useMemo(() => eligibleJobs.slice(0, 8), [eligibleJobs]);

  const handleOpenChange = (open: boolean) => {
    if (open) {
      const nowIso = new Date().toISOString();
      try {
        localStorage.setItem(SEEN_KEY, nowIso);
      } catch {}
      setSeenAt(nowIso);
    }
  };

  return (
    <DropdownMenu onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="icon-sm"
          className="relative size-8 rounded-full bg-card hover:bg-mist text-ink border-line shrink-0"
          aria-label="Notifications"
        >
          <Icon name="bell" />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-white tabular-nums">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-80 p-0 rounded-xl border border-line/70 bg-card shadow-md"
      >
        <div className="px-4 py-3 border-b border-line/60">
          <span className="font-semibold text-sm text-foreground">Notifications</span>
        </div>
        <div className="max-h-80 overflow-y-auto p-1">
          {items.length === 0 ? (
            <div className="py-6 text-center text-xs text-muted-foreground">
              No recent activity
            </div>
          ) : (
            items.map((j) => (
              <DropdownMenuItem key={j.id} asChild className="cursor-pointer focus:bg-mist p-0">
                <Link
                  href={`/job/?id=${j.id}`}
                  className="flex items-start gap-2.5 p-2.5 rounded-lg w-full"
                >
                  <span
                    className={`mt-1 size-2 rounded-full shrink-0 ${
                      j.status === "done" ? "bg-forest" : "bg-destructive"
                    }`}
                    aria-hidden="true"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-foreground truncate">
                      Job {j.id} ({j.area_id}) {j.status === "done" ? "finished" : "failed"}
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {j.finished_at ? formatRelative(j.finished_at) : "-"}
                    </p>
                  </div>
                </Link>
              </DropdownMenuItem>
            ))
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
