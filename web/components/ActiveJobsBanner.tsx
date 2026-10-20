import { Fragment } from "react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/lib/Icon";
import Link from "@/lib/Link";
import { describeActive, summarizeActiveJobs } from "@/lib/activeJobs";
import type { Job } from "@/lib/api";

export function ActiveJobsBanner({ jobs }: { jobs: Job[] }) {
  const summary = summarizeActiveJobs(jobs);
  if (
    summary.building.length === 0 &&
    summary.uploading.length === 0 &&
    summary.stalled.length === 0
  ) {
    return null;
  }

  const { primary, secondary } = describeActive(summary);
  const runningCount = summary.building.length + summary.uploading.length;
  const singleJob =
    runningCount === 1 && summary.stalled.length === 0
      ? summary.building[0] ?? summary.uploading[0]
      : null;
  const action = singleJob
    ? { href: `/job/?id=${singleJob.id}`, label: `Open job #${singleJob.id}` }
    : summary.stalled.length > 0 && runningCount === 0
      ? { href: "/jobs/?q=uploading", label: "Review uploads" }
      : { href: "/jobs/", label: "View jobs" };
  const hasRunning = runningCount > 0;
  const iconName = summary.building.length > 0 ? "stack" : "upload";

  return (
    <div
      role="status"
      aria-live="polite"
      className="mb-4 flex flex-col gap-3 rounded-lg border border-border bg-mist p-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex min-w-0 items-start gap-3">
        <div className="relative flex size-8 shrink-0 items-center justify-center rounded-lg bg-forest/10 text-forest">
          <Icon name={iconName} />
          {hasRunning && (
            <span
              aria-hidden="true"
              className="absolute right-1 top-1 size-1.5 rounded-full bg-forest motion-safe:animate-pulse"
            />
          )}
        </div>
        <div className="min-w-0">
          <p className="m-0 text-sm">{primary}</p>
          {secondary && (
            <p className="muted m-0">
              {secondary.split(" · ").map((part, index) => (
                <Fragment key={`${index}-${part}`}>
                  {index > 0 ? " · " : null}
                  <span
                    className={
                      part.includes("stopped receiving data") ? "text-destructive" : undefined
                    }
                  >
                    {part}
                  </span>
                </Fragment>
              ))}
            </p>
          )}
        </div>
      </div>
      <Button asChild variant="outline" size="sm" className="w-full sm:w-auto">
        <Link href={action.href}>{action.label}</Link>
      </Button>
    </div>
  );
}
