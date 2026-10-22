"use client";

import { Panel } from "@/components/Panel";
import { useT } from "@/lib/i18n";
import type { TranslationKey } from "@/lib/i18n";

export const PIPELINE_STAGES = [
  { id: "extract", label: "Extract", descKey: "pipeline.descExtract" as TranslationKey },
  { id: "build", label: "Build", descKey: "pipeline.descBuild" as TranslationKey },
  { id: "inspect", label: "Inspect", descKey: "pipeline.descInspect" as TranslationKey },
  { id: "register", label: "Register", descKey: "pipeline.descRegister" as TranslationKey },
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

function getStageStateLabel(state: StageState, t: (k: TranslationKey) => string): string {
  if (state === "done") return t("pipeline.completed");
  if (state === "active") return t("pipeline.running");
  if (state === "failed") return t("pipeline.failed");
  return t("pipeline.pending");
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
  const t = useT();
  const currentStageIndex = PIPELINE_STAGES.findIndex((s) => s.id === currentStage);
  const currentStageLabel = currentStageIndex >= 0 ? PIPELINE_STAGES[currentStageIndex].label : null;

  const states = PIPELINE_STAGES.map((_, idx) => getStageState(status, currentStageIndex, idx));

  const completedCount = states.filter((state) => state === "done").length;

  let summary = t("pipeline.notStarted");
  if (status === "done") summary = t("pipeline.allStagesFinished");
  else if (status === "running") {
    summary = currentStageLabel
      ? t("pipeline.stageXofY", {
          current: currentStageIndex + 1,
          total: PIPELINE_STAGES.length,
          stage: currentStageLabel,
        })
      : t("pipeline.startingFirst");
  } else if (status === "failed") {
    summary = currentStageLabel
      ? t("pipeline.stoppedAt", { stage: currentStageLabel })
      : t("pipeline.stoppedBeforeFirst");
  } else if (status === "queued") summary = t("pipeline.waitingWorker");
  else if (status === "uploading") summary = t("pipeline.waitingUpload");
  else if (status === "deleting") summary = t("pipeline.deletingJob");

  const tone =
    status === "done" ? "ok" : status === "running" ? "live" : status === "failed" ? "bad" : "idle";

  return (
    <Panel className="pipeline" data-tone={tone} role="region" aria-labelledby="pipeline-title">
      <div className="pipeline-head">
        <div className="pipeline-heading">
          <h2 id="pipeline-title" className="pipeline-title">
            {t("pipeline.reconstructionPipeline")}
          </h2>
          <p className="pipeline-summary">{summary}</p>
        </div>
        <span className="pipeline-fraction">
          <strong>{completedCount}</strong> / {PIPELINE_STAGES.length} {t("pipeline.doneFraction")}
        </span>
      </div>

      <ol className="pipeline-steps">
        {PIPELINE_STAGES.map((stage, idx) => {
          const state = states[idx];
          const timingNote = getStageTiming(stage.id, state, timings);
          const stateLabel = getStageStateLabel(state, t);

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
                  {state === "active" && <span className="pipeline-live">{t("pipeline.running")}</span>}
                  {state === "failed" && <span className="pipeline-failed">{t("pipeline.failed")}</span>}
                </div>
                <span className="pipeline-desc">{t(stage.descKey)}</span>
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
