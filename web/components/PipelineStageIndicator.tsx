"use client";

import { Panel } from "@/components/Panel";

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
}

type StageState = "done" | "active" | "failed" | "pending";

function fmtSec(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

function getStageState(status: string, currentStageIndex: number, idx: number): StageState {
  if (status === "done") return "done";
  if (status === "running" && idx === currentStageIndex) return "active";
  if (status === "failed" && idx === currentStageIndex) return "failed";
  if ((status === "running" || status === "failed") && currentStageIndex > idx) return "done";
  return "pending";
}

function getStageTiming(
  stageId: PipelineStageId,
  state: StageState,
  timings?: Record<string, number>,
): string | null {
  if (state !== "done" || !timings) return null;
  if (stageId === "extract") {
    return timings.local_extract ? fmtSec(timings.local_extract) : null;
  }
  if (stageId === "build") {
    const buildTotal = (timings.pairs ?? 0) + (timings.match ?? 0) + (timings.reconstruction ?? 0);
    return buildTotal > 0 ? fmtSec(buildTotal) : null;
  }
  return null;
}

function getStageStateLabel(state: StageState): string {
  if (state === "done") return "Completed";
  if (state === "active") return "Running";
  if (state === "failed") return "Failed";
  return "Pending";
}

function CheckMark() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="size-3.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3.5 8.5l3 3 6-7" />
    </svg>
  );
}

function CrossMark() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="size-3.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  );
}

export function PipelineStageIndicator({
  status,
  currentStage,
  timings,
}: PipelineStageIndicatorProps) {
  const currentStageIndex = PIPELINE_STAGES.findIndex((s) => s.id === currentStage);
  const currentStageLabel = currentStageIndex >= 0 ? PIPELINE_STAGES[currentStageIndex].label : null;

  const states = PIPELINE_STAGES.map((_, idx) => getStageState(status, currentStageIndex, idx));

  const completedCount = states.filter((state) => state === "done").length;

  let summary = "Not started";
  if (status === "done") summary = "All stages finished";
  else if (status === "running") {
    summary = currentStageLabel
      ? `Stage ${currentStageIndex + 1} of ${PIPELINE_STAGES.length}: ${currentStageLabel}`
      : "Starting the first stage";
  } else if (status === "failed") {
    summary = currentStageLabel ? `Stopped at ${currentStageLabel}` : "Stopped before the first stage";
  } else if (status === "queued") summary = "Waiting for a worker";
  else if (status === "uploading") summary = "Waiting for the upload to finish";
  else if (status === "deleting") summary = "Deleting this job";

  const tone =
    status === "done" ? "ok" : status === "running" ? "live" : status === "failed" ? "bad" : "idle";

  return (
    <Panel className="pipeline" data-tone={tone} role="region" aria-labelledby="pipeline-title">
      <div className="pipeline-head">
        <div className="pipeline-heading">
          <h2 id="pipeline-title" className="pipeline-title">
            Reconstruction pipeline
          </h2>
          <p className="pipeline-summary">{summary}</p>
        </div>
        <span className="pipeline-fraction">
          <strong>{completedCount}</strong> / {PIPELINE_STAGES.length} done
        </span>
      </div>

      <ol className="pipeline-steps">
        {PIPELINE_STAGES.map((stage, idx) => {
          const state = states[idx];
          const timingNote = getStageTiming(stage.id, state, timings);
          const stateLabel = getStageStateLabel(state);

          return (
            <li
              key={stage.id}
              className="pipeline-step"
              data-state={state}
              aria-current={state === "active" ? "step" : undefined}
            >
              <span className="pipeline-node" aria-hidden="true">
                {state === "done" ? (
                  <CheckMark />
                ) : state === "failed" ? (
                  <CrossMark />
                ) : (
                  <span className="pipeline-node-number">{String(idx + 1).padStart(2, "0")}</span>
                )}
              </span>
              {idx < PIPELINE_STAGES.length - 1 && (
                <span className="pipeline-connector" aria-hidden="true" />
              )}

              <div className="pipeline-copy">
                <div className="pipeline-label-row">
                  <span className="pipeline-label">{stage.label}</span>
                  {state === "active" && <span className="pipeline-live">Running</span>}
                  {state === "failed" && <span className="pipeline-failed">Failed</span>}
                </div>
                <span className="pipeline-desc">{stage.desc}</span>
                {timingNote && <span className="pipeline-time">{timingNote}</span>}
                <span className="sr-only">{stateLabel}</span>
              </div>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
