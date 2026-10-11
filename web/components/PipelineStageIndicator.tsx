"use client";

import { cn } from "@/lib/utils";

export const PIPELINE_STAGES = [
  { id: "extract", label: "Extract", desc: "Frame & feature extraction" },
  { id: "build", label: "Build", desc: "Structure-from-Motion" },
  { id: "inspect", label: "Inspect", desc: "Map inspection & evaluation" },
  { id: "register", label: "Register", desc: "Map version registration" },
] as const;

export type PipelineStageId = (typeof PIPELINE_STAGES)[number]["id"];

interface PipelineStageIndicatorProps {
  status: string; // uploading, queued, running, done, failed, deleting
  currentStage: string | null; // extract, build, inspect, register
  timings?: Record<string, number>; // summary.run.t_map_s
  className?: string;
}

function fmtSec(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

export function PipelineStageIndicator({
  status,
  currentStage,
  timings,
  className,
}: PipelineStageIndicatorProps) {
  const currentStageIndex = PIPELINE_STAGES.findIndex((s) => s.id === currentStage);

  return (
    <div className={cn("flex flex-col gap-3 rounded-lg border border-line bg-card p-4", className)}>
      <div className="flex items-center justify-between border-b border-line pb-2.5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Reconstruction Pipeline
          </span>
          {status === "running" && (
            <span className="flex items-center gap-1.5 rounded-full bg-forest/15 px-2 py-0.5 text-[11px] font-medium text-forest">
              <span className="size-1.5 rounded-full bg-forest animate-pulse" />
              Running: {currentStage ? currentStage.toUpperCase() : "Active"}
            </span>
          )}
          {status === "failed" && (
            <span className="rounded-full bg-bad-bg px-2 py-0.5 text-[11px] font-medium text-bad-fg">
              Failed at {currentStage ?? "initialization"}
            </span>
          )}
          {status === "done" && (
            <span className="rounded-full bg-forest/15 px-2 py-0.5 text-[11px] font-medium text-forest">
              All stages completed
            </span>
          )}
          {status === "queued" && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
              Queued (waiting for worker)
            </span>
          )}
        </div>
        <span className="text-[11px] text-muted-foreground">
          {status === "running"
            ? "Indeterminate progress (no simulated %)"
            : status === "done"
              ? "4 of 4 stages"
              : status === "failed"
                ? "Terminated"
                : "Sequential"}
        </span>
      </div>

      {/* Stepper Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 pt-1">
        {PIPELINE_STAGES.map((st, idx) => {
          const isDoneJob = status === "done";
          const isRunningJob = status === "running";
          const isFailedJob = status === "failed";
          const isCurrentStage = currentStage === st.id;
          const isPastInSequence = currentStageIndex > -1 && idx < currentStageIndex;

          let stepState: "done" | "active" | "failed" | "past" | "pending" = "pending";
          if (isDoneJob) {
            stepState = "done";
          } else if (isFailedJob) {
            if (isCurrentStage) stepState = "failed";
            else if (isPastInSequence) stepState = "past";
            else stepState = "pending";
          } else if (isRunningJob) {
            if (isCurrentStage) stepState = "active";
            else if (isPastInSequence) stepState = "past";
            else stepState = "pending";
          }

          // Optional timing details for done jobs
          let timingNote: string | null = null;
          if (isDoneJob && timings) {
            if (st.id === "extract" && timings.local_extract) {
              timingNote = fmtSec(timings.local_extract);
            } else if (st.id === "build") {
              const buildTotal =
                (timings.pairs ?? 0) + (timings.match ?? 0) + (timings.reconstruction ?? 0);
              if (buildTotal > 0) timingNote = fmtSec(buildTotal);
            }
          }

          return (
            <div
              key={st.id}
              className={cn(
                "relative flex flex-col gap-1 rounded-md p-2.5 text-xs transition-colors border",
                stepState === "done" && "bg-forest/5 border-forest/20 text-foreground",
                stepState === "active" && "bg-forest/10 border-forest ring-1 ring-forest/30 text-foreground",
                stepState === "failed" && "bg-bad-bg/60 border-bad-fg/30 text-bad-fg",
                stepState === "past" && "bg-canvas/50 border-line text-muted-foreground",
                stepState === "pending" && "bg-canvas/30 border-line/50 text-muted-foreground/60"
              )}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-[10px] font-semibold">0{idx + 1}</span>
                {stepState === "done" && (
                  <span className="text-[10px] font-semibold text-forest">✓ Done</span>
                )}
                {stepState === "active" && (
                  <span className="flex items-center gap-1 text-[10px] font-semibold text-forest">
                    <span className="size-1.5 rounded-full bg-forest animate-ping" />
                    Active
                  </span>
                )}
                {stepState === "failed" && (
                  <span className="text-[10px] font-semibold text-bad-fg">✕ Failed</span>
                )}
                {stepState === "past" && (
                  <span className="text-[10px] text-muted-foreground">Prior</span>
                )}
                {stepState === "pending" && (
                  <span className="text-[10px] text-muted-foreground/50">Pending</span>
                )}
              </div>

              <div className="font-semibold text-foreground mt-0.5">{st.label}</div>
              <div className="text-[11px] text-muted-foreground leading-tight">{st.desc}</div>

              {timingNote && (
                <div className="mt-1 text-[10px] font-mono text-forest/90 font-medium">
                  {timingNote}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
