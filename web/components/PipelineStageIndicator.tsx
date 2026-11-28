"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Panel } from "@/components/Panel";
import type { Job, Version } from "@/lib/api";
import { useFormatNumber, useLocale, useT } from "@/lib/i18n";
import type { TranslationKey } from "@/lib/i18n";
import {
  GRAPH_NODE_ORDER,
  derivePipelineGraph,
  type CoreStageId,
  type GraphNodeId,
  type GraphNodeModel,
  type NodeVisualState,
} from "@/lib/pipelineGraph";
import {
  buildPipelineWires,
  type BoxRect,
  type BuiltWireGeometry,
  type GraphLayoutMode,
  type PortSide,
  type TileRect,
} from "@/lib/pipelineWires";

export const PIPELINE_STAGES = [
  { id: "extract", label: "Extract", descKey: "pipeline.descExtract" as TranslationKey },
  { id: "build", label: "Build", descKey: "pipeline.descBuild" as TranslationKey },
  { id: "inspect", label: "Inspect", descKey: "pipeline.descInspect" as TranslationKey },
  { id: "register", label: "Register", descKey: "pipeline.descRegister" as TranslationKey },
  { id: "align", labelKey: "pipeline.align" as TranslationKey, descKey: "pipeline.descAlign" as TranslationKey },
  { id: "gate", labelKey: "pipeline.gate" as TranslationKey, descKey: "pipeline.descGate" as TranslationKey },
] as const;

export type PipelineStageId = CoreStageId;

/**
 * Slot aset ikon berdasarkan ID node. Tahap ini memakai placeholder seragam agar
 * ikon final pilihan Bagus dapat dipasang per ID node tanpa mengubah kotak 42x42 px
 * ataupun posisi port kabel.
 */
export type NodeIconSlotMap = Partial<Record<GraphNodeId, ReactNode>>;

export interface PipelineStageIndicatorProps {
  job: Job;
  version: Version | null;
  versionLoading?: boolean;
  versionError?: string | null;
  publishActionError?: string | null;
  isStale?: boolean;
  staleError?: string | null;
  isVersionStale?: boolean;
  nowMs?: number;
  /** Peta opsional untuk mengganti placeholder pada node tertentu berdasarkan ID node. */
  nodeIcons?: NodeIconSlotMap;
}

const WIDE_BREAKPOINT = 760;
const NARROW_BREAKPOINT = 480;

const STATE_SYMBOL: Record<NodeVisualState, string> = {
  done: "✓",
  active: "●",
  wait: "◷",
  warn: "!",
  failed: "×",
  skipped: "↷",
  legacy: "○",
  optional: "○",
  ready: "◈",
  unknown: "?",
  pending: "·",
  off: "·",
};

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return reduced;
}

function formatSecondsText(
  seconds: number | null | undefined,
  t: (k: TranslationKey, vars?: Record<string, string | number>) => string,
  fmt: (v: number | null | undefined, digits?: number) => string,
): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  if (seconds >= 3600) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.round(seconds % 60);
    return t("pgraph.unitHourMinSec", { h: fmt(h, 0), m: fmt(m, 0), s: fmt(s, 0) });
  }
  if (seconds >= 60) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds - m * 60);
    return t("report.unitMinSec", { min: fmt(m, 0), sec: fmt(s, 0) });
  }
  if (seconds === 0) {
    return t("report.unitSec", { val: fmt(0, 0) });
  }
  const digits = seconds < 10 ? 1 : 0;
  return t("report.unitSec", { val: fmt(seconds, digits) });
}

function nodeTitle(id: GraphNodeId, t: (k: TranslationKey) => string): string {
  const map: Record<GraphNodeId, TranslationKey> = {
    video: "pgraph.node.video",
    zip: "pgraph.node.zip",
    extract: "pipeline.stageExtract",
    build: "pipeline.stageBuild",
    inspect: "pipeline.stageInspect",
    register: "pipeline.stageRegister",
    align: "pipeline.align",
    gate: "pipeline.gate",
    reject: "pgraph.node.reject",
    hold: "pgraph.node.hold",
    pass: "pgraph.node.pass",
    publish: "pgraph.node.publish",
    splat: "pgraph.node.splat",
  };
  return t(map[id]);
}

function nodeDesc(id: GraphNodeId, t: (k: TranslationKey) => string): string {
  const map: Record<GraphNodeId, TranslationKey> = {
    video: "pgraph.desc.video",
    zip: "pgraph.desc.zip",
    extract: "pipeline.descExtract",
    build: "pipeline.descBuild",
    inspect: "pipeline.descInspect",
    register: "pipeline.descRegister",
    align: "pipeline.descAlign",
    gate: "pipeline.descGate",
    reject: "pgraph.desc.reject",
    hold: "pgraph.desc.hold",
    pass: "pgraph.desc.pass",
    publish: "pgraph.desc.publish",
    splat: "pgraph.desc.splat",
  };
  return t(map[id]);
}

function translateStatusCode(
  node: GraphNodeModel,
  t: (k: TranslationKey, vars?: Record<string, string | number>) => string,
): string {
  switch (node.statusCode) {
    case "done":
      return t("pipeline.completed");
    case "running":
      return t("pipeline.running");
    case "failed":
      return t("pipeline.failed");
    case "pending":
      return t("pipeline.pending");
    case "rejected":
      return t("pgraph.status.rejected");
    case "align_applied":
      return t("job.alignStatus.applied");
    case "align_skipped":
      return t("job.alignStatus.skipped");
    case "align_failed_continued":
      return t("pgraph.status.alignFailedContinued");
    case "legacy_not_recorded":
      return t("pgraph.status.legacyNotRecorded");
    case "gate_passed":
    case "gate_branch_passed":
      return t("pgraph.status.gatePassed");
    case "gate_held":
    case "gate_branch_held":
      return t("pgraph.status.gateHeld");
    case "gate_branch_rejected":
      return t("pgraph.status.gateRejected");
    case "gate_branch_inactive":
      return t("pgraph.status.branchInactive");
    case "source_used":
      return t("pgraph.status.sourceUsed");
    case "source_ready":
      return t("pgraph.status.sourceReady");
    case "source_unused":
      return t("pgraph.status.sourceUnused");
    case "uploading":
      return t("pgraph.status.uploading");
    case "uploading_stalled":
      return t("pgraph.status.stalled");
    case "waiting_map":
      return t("pgraph.status.waitingMap");
    case "blocked_by_gate":
      return t("pgraph.status.blockedByGate");
    case "not_reached":
      return t("pgraph.status.notReached");
    case "version_loading":
      return t("pgraph.status.versionLoading");
    case "version_unknown":
      return t("pgraph.status.versionUnknown");
    case "version_published":
      return t("pgraph.status.published");
    case "version_ready":
      return t("pgraph.status.ready");
    case "version_candidate":
      return t("pgraph.status.candidate");
    case "version_retired":
      return t("pgraph.status.retired");
    case "version_rejected":
      return t("pgraph.status.rejected");
    case "publish_failed":
      return t("pgraph.status.publishFailed");
    case "splat_queued":
      return t("splat.status.queued");
    case "splat_gpu_wait":
      return t("pgraph.status.waitingGpu");
    case "splat_running":
      return node.splatStage
        ? t("pgraph.status.splatStage", { stage: node.splatStage })
        : t("splat.status.running");
    case "splat_starting":
      return t("splat.status.running");
    case "splat_done":
      return t("pipeline.completed");
    case "splat_failed":
      return t("pipeline.failed");
    case "splat_optional":
      return t("pgraph.status.optional");
    case "splat_not_scheduled":
      return t("pgraph.status.notScheduled");
    default:
      return t("pipeline.pending");
  }
}

function translateReason(
  node: GraphNodeModel,
  t: (k: TranslationKey, vars?: Record<string, string | number>) => string,
): string | null {
  if (node.id === "align" && node.reasonText) {
    if (node.reasonText === "no_frames") return t("job.alignNoFrames");
    if (node.reasonText === "residual_too_high") return t("job.alignHighResidual");
    return node.reasonText;
  }
  return node.reasonText;
}

function translateVersionStatus(status: string, t: (k: TranslationKey) => string): string {
  switch (status) {
    case "published":
      return t("pgraph.status.published");
    case "ready":
      return t("pgraph.status.ready");
    case "candidate":
      return t("pgraph.status.candidate");
    case "retired":
      return t("pgraph.status.retired");
    case "rejected":
      return t("pgraph.status.rejected");
    default:
      return status;
  }
}

/** Baris ringkas di luar kotak ikon (1 baris status/durasi yang terbaca tanpa warna). */
function compactMetaText(
  node: GraphNodeModel,
  statusLabel: string,
  t: (k: TranslationKey, vars?: Record<string, string | number>) => string,
  fmt: (v: number | null | undefined, digits?: number) => string,
): string {
  const sym = STATE_SYMBOL[node.state];
  if (node.showStageDuration) {
    const dur = formatSecondsText(node.recordedSeconds, t, fmt);
    if (node.state === "done") return `${sym} ${dur}`;
    if (node.state === "pending") return `${sym} ${dur}`;
    return `${sym} ${statusLabel} · ${dur}`;
  }
  if (node.id === "splat" && node.state === "done" && node.splatTrainSeconds != null) {
    return `${sym} ${formatSecondsText(node.splatTrainSeconds, t, fmt)}`;
  }
  return `${sym} ${statusLabel}`;
}

/** Slot ikon 42x42 px berbasis ID node; bawaan memakai placeholder persegi netral seragam. */
function NodeIconSlot({ nodeId, customIcon }: { nodeId: GraphNodeId; customIcon?: ReactNode }) {
  return (
    <span className="pgraph-icon-slot" data-icon-slot={nodeId} aria-hidden="true">
      {customIcon ?? <span className="pgraph-placeholder" />}
    </span>
  );
}

export function PipelineStageIndicator({
  job,
  version,
  versionLoading = false,
  versionError = null,
  publishActionError = null,
  isStale = false,
  staleError = null,
  isVersionStale = false,
  nowMs,
  nodeIcons,
}: PipelineStageIndicatorProps) {
  const t = useT();
  const { locale } = useLocale();
  const fmt = useFormatNumber();
  const reducedMotion = usePrefersReducedMotion();
  const [userPaused, setUserPaused] = useState(false);

  const model = useMemo(
    () =>
      derivePipelineGraph({
        job,
        version,
        versionLoading,
        versionError,
        publishActionError,
        isStale,
        isVersionStale,
        nowMs,
      }),
    [job, version, versionLoading, versionError, publishActionError, isStale, isVersionStale, nowMs],
  );

  // Pilih node default per job; pertahankan pilihan pengguna selama melihat job yang sama.
  const [selectedState, setSelectedState] = useState<{ jobId: number; nodeId: GraphNodeId } | null>(null);
  const selectedId: GraphNodeId =
    selectedState && selectedState.jobId === job.id ? selectedState.nodeId : model.defaultSelectedNode;

  const panelRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const tileRefs = useRef<Partial<Record<GraphNodeId, HTMLSpanElement | null>>>({});
  const nodeRefs = useRef<Partial<Record<GraphNodeId, HTMLButtonElement | null>>>({});

  const [layoutMode, setLayoutMode] = useState<GraphLayoutMode>("wide");
  const [svgSize, setSvgSize] = useState({ width: 0, height: 0 });
  const [wireGeom, setWireGeom] = useState<BuiltWireGeometry>({
    baseSegments: [],
    flowPulses: [],
    activePorts: {},
  });

  const motionPaused = userPaused || isStale || reducedMotion;

  const recomputeGeometry = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const cRect = canvas.getBoundingClientRect();
    if (cRect.width === 0 || cRect.height === 0) return;

    const panelWidth = panelRef.current?.getBoundingClientRect().width ?? cRect.width;
    const nextLayout: GraphLayoutMode =
      panelWidth < NARROW_BREAKPOINT ? "narrow" : panelWidth < WIDE_BREAKPOINT ? "medium" : "wide";

    setLayoutMode((prev) => (prev === nextLayout ? prev : nextLayout));
    setSvgSize((prev) =>
      Math.abs(prev.width - cRect.width) < 0.5 && Math.abs(prev.height - cRect.height) < 0.5
        ? prev
        : { width: cRect.width, height: cRect.height },
    );

    const tiles: Partial<Record<GraphNodeId, TileRect>> = {};
    const copies: Partial<Record<GraphNodeId, BoxRect>> = {};
    for (const id of GRAPH_NODE_ORDER) {
      const tileEl = tileRefs.current[id];
      if (!tileEl) continue;
      const r = tileEl.getBoundingClientRect();
      const left = r.left - cRect.left;
      const right = r.right - cRect.left;
      const top = r.top - cRect.top;
      const bottom = r.bottom - cRect.top;
      tiles[id] = {
        left,
        right,
        top,
        bottom,
        cx: (left + right) / 2,
        cy: (top + bottom) / 2,
      };
      const copyEl = nodeRefs.current[id]?.querySelector<HTMLElement>(".pgraph-node-copy");
      if (copyEl) {
        const cr = copyEl.getBoundingClientRect();
        copies[id] = {
          left: cr.left - cRect.left,
          right: cr.right - cRect.left,
          top: cr.top - cRect.top,
          bottom: cr.bottom - cRect.top,
        };
      }
    }

    const built = buildPipelineWires({
      wires: model.wires,
      outputOrigin: model.outputOrigin,
      outputsBlockedByGate: model.outputsBlockedByGate,
      layout: nextLayout,
      tiles,
      copies,
      canvasWidth: cRect.width,
    });
    setWireGeom(built);
  }, [model.wires, model.outputOrigin, model.outputsBlockedByGate]);

  useLayoutEffect(() => {
    recomputeGeometry();
  }, [recomputeGeometry, locale, layoutMode, selectedId, job.id]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let rafId = 0;
    const schedule = () => {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        rafId = 0;
        recomputeGeometry();
      });
    };

    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(schedule) : null;
    if (observer) {
      if (panelRef.current) observer.observe(panelRef.current);
      observer.observe(canvas);
      for (const id of GRAPH_NODE_ORDER) {
        const el = nodeRefs.current[id];
        if (el) observer.observe(el);
      }
    }
    window.addEventListener("resize", schedule);
    document.fonts?.ready?.then(schedule).catch(() => {});

    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      observer?.disconnect();
      window.removeEventListener("resize", schedule);
    };
  }, [recomputeGeometry]);

  // Ringkasan status header berdasarkan kondisi nyata API
  let summaryText = t("pipeline.notStarted");
  if (model.summaryCode === "done_publish") {
    summaryText = t("pgraph.summary.donePublish");
  } else if (model.summaryCode === "done_hold") {
    summaryText = t("pgraph.summary.doneHold");
  } else if (model.summaryCode === "done_legacy") {
    summaryText = t("pipeline.allStagesFinished");
  } else if (model.summaryCode === "failed_gate") {
    summaryText = t("pgraph.summary.failedGate");
  } else if (model.summaryCode === "failed_publish") {
    summaryText = t("pgraph.summary.failedPublish");
  } else if (model.summaryCode === "failed_stage" && model.failedCoreStage) {
    summaryText = t("pipeline.stoppedAt", { stage: nodeTitle(model.failedCoreStage, t) });
  } else if (model.summaryCode === "failed_before_first") {
    summaryText = t("pipeline.stoppedBeforeFirst");
  } else if (model.summaryCode === "running_gpu_wait") {
    summaryText = t("pipeline.waitingGpu");
  } else if (model.summaryCode === "running_stage" && model.activeCoreStage) {
    summaryText = t("pgraph.summary.runningStage", { stage: nodeTitle(model.activeCoreStage, t) });
  } else if (model.summaryCode === "running_starting") {
    summaryText = t("pipeline.startingFirst");
  } else if (model.summaryCode === "queued") {
    summaryText = t("pipeline.waitingWorker");
  } else if (model.summaryCode === "uploading") {
    summaryText = t("pipeline.waitingUpload");
  } else if (model.summaryCode === "uploading_stalled") {
    summaryText = t("job.uploadStalled");
  } else if (model.summaryCode === "deleting") {
    summaryText = t("pipeline.deletingJob");
  }

  const selectedNode = model.nodes[selectedId];
  const selectedReason = translateReason(selectedNode, t);

  const renderNode = (id: GraphNodeId) => {
    const node = model.nodes[id];
    const isSelected = selectedId === id;
    const ports = wireGeom.activePorts[id] ?? [];
    const title = nodeTitle(id, t);
    const statusLabel = translateStatusCode(node, t);
    const metaLine = compactMetaText(node, statusLabel, t, fmt);
    const stageDur = node.showStageDuration ? formatSecondsText(node.recordedSeconds, t, fmt) : null;
    const ariaParts = [title, statusLabel];
    if (stageDur) ariaParts.push(stageDur);
    else if (node.id === "splat" && node.splatTrainSeconds != null) {
      ariaParts.push(formatSecondsText(node.splatTrainSeconds, t, fmt));
    }

    return (
      <button
        key={id}
        ref={(el) => {
          nodeRefs.current[id] = el;
        }}
        type="button"
        className="pgraph-node"
        style={{ gridArea: id }}
        data-node-id={id}
        data-group={node.group}
        data-state={node.state}
        aria-pressed={isSelected}
        aria-current={node.state === "active" ? "step" : undefined}
        aria-controls="pgraph-detail-title"
        aria-label={ariaParts.join(", ")}
        onClick={() => setSelectedState({ jobId: job.id, nodeId: id })}
      >
        <span
          ref={(el) => {
            tileRefs.current[id] = el;
          }}
          className="pgraph-tile"
          aria-hidden="true"
        >
          <NodeIconSlot nodeId={id} customIcon={nodeIcons?.[id]} />
          {(["l", "r", "t", "b"] as PortSide[]).map((side) =>
            ports.includes(side) ? (
              <span key={side} className="pgraph-port" data-port={side} />
            ) : null,
          )}
        </span>
        <span className="pgraph-node-copy">
          <span className="pgraph-label">{title}</span>
          <span className="pgraph-meta num" data-state={node.state}>
            {metaLine}
          </span>
        </span>
      </button>
    );
  };

  return (
    <Panel
      className="pgraph"
      data-tone={model.summaryTone}
      data-layout={layoutMode}
      data-motion-paused={motionPaused ? "true" : "false"}
      data-stale={isStale ? "true" : "false"}
      data-version-stale={isVersionStale ? "true" : "false"}
      role="region"
      aria-labelledby="pipeline-title"
    >
      <div ref={panelRef} className="pgraph-inner">
        {/* Header panel */}
        <div className="pgraph-head">
          <div className="pgraph-heading">
            <div className="pgraph-title-row">
              <h2 id="pipeline-title" className="pgraph-title">
                {t("pipeline.reconstructionPipeline")}
              </h2>
              {isStale && (
                <span className="pgraph-stale-pill" data-stale-scope="job" role="status">
                  <span aria-hidden="true">!</span>
                  <span>{t("pgraph.staleBadge")}</span>
                </span>
              )}
              {!isStale && isVersionStale && (
                <span className="pgraph-stale-pill" data-stale-scope="version" role="status">
                  <span aria-hidden="true">!</span>
                  <span>{t("pgraph.versionStaleBadge")}</span>
                </span>
              )}
            </div>
            <p className="pgraph-summary">{summaryText}</p>
          </div>

          <div className="pgraph-head-actions">
            <span className="pgraph-fraction">
              <strong>{model.completedCoreCount}</strong> / {model.totalCoreCount} {t("pipeline.doneFraction")}
            </span>
            <button
              type="button"
              className="pgraph-pause-btn"
              aria-pressed={userPaused}
              disabled={reducedMotion}
              title={reducedMotion ? t("pgraph.reducedMotionActive") : undefined}
              onClick={() => setUserPaused((p) => !p)}
            >
              <span aria-hidden="true">{userPaused || reducedMotion ? "▶" : "❚❚"}</span>
              <span>
                {reducedMotion
                  ? t("pgraph.reducedMotionLabel")
                  : userPaused
                    ? t("pgraph.resumeMotion")
                    : t("pgraph.pauseMotion")}
              </span>
            </button>
          </div>
        </div>

        {isStale && staleError && (
          <p className="pgraph-stale-note" data-stale-scope="job" role="status">
            {t("pgraph.staleDetail", { error: staleError })}
          </p>
        )}
        {!isStale && isVersionStale && (
          <p className="pgraph-stale-note" data-stale-scope="version" role="status">
            {versionError
              ? t("pgraph.versionStaleDetail", { error: versionError })
              : t("pgraph.versionStaleDelayedDetail")}
          </p>
        )}

        {/* Kanvas charcoal dengan grid titik samar, kotak ikon 42x42 px, dan konektor solid tanpa panah */}
        <div ref={canvasRef} className="pgraph-canvas" data-layout={layoutMode}>
          <svg
            className="pgraph-wires"
            width={svgSize.width || undefined}
            height={svgSize.height || undefined}
            viewBox={svgSize.width && svgSize.height ? `0 0 ${svgSize.width} ${svgSize.height}` : undefined}
            aria-hidden="true"
          >
            <g className="pgraph-wire-base-layer">
              {wireGeom.baseSegments.map((seg) => (
                <path
                  key={seg.id}
                  d={seg.d}
                  className="pgraph-wire"
                  data-segment-id={seg.id}
                  data-state={seg.state}
                />
              ))}
            </g>
            <g className="pgraph-wire-flow-layer">
              {wireGeom.flowPulses.map((flow) => (
                <path
                  key={flow.id}
                  d={flow.d}
                  pathLength={100}
                  className="pgraph-wire-flow"
                  data-flow-id={flow.id}
                  data-paused={motionPaused ? "true" : "false"}
                />
              ))}
            </g>
          </svg>

          <div className="pgraph-grid">
            <h3 className="sr-only">{t("pgraph.group.sources")}</h3>
            {renderNode("video")}
            {renderNode("zip")}

            <h3 className="sr-only">{t("pgraph.group.core")}</h3>
            {renderNode("extract")}
            {renderNode("build")}
            {renderNode("inspect")}
            {renderNode("register")}
            {renderNode("align")}
            {renderNode("gate")}

            <h3 className="sr-only">{t("pgraph.group.decision")}</h3>
            {renderNode("reject")}
            {renderNode("hold")}
            {renderNode("pass")}

            <h3 className="sr-only">{t("pgraph.group.outputs")}</h3>
            {renderNode("publish")}
            {renderNode("splat")}
          </div>
        </div>

        {/* Panel detail interaktif (klik atau Enter pada node) */}
        <div className="pgraph-detail" aria-live="polite" data-selected-node={selectedNode.id}>
          <div className="pgraph-detail-head">
            <div className="pgraph-detail-title-group">
              <h3 id="pgraph-detail-title" className="pgraph-detail-title">
                {nodeTitle(selectedNode.id, t)}
              </h3>
              <span className="pgraph-detail-badge" data-state={selectedNode.state}>
                <span aria-hidden="true">{STATE_SYMBOL[selectedNode.state]}</span>
                <span>{translateStatusCode(selectedNode, t)}</span>
              </span>
            </div>
            {selectedNode.showStageDuration && (
              <span className="pgraph-detail-time num">
                {t("pgraph.detail.stageDuration")}: {formatSecondsText(selectedNode.recordedSeconds, t, fmt)}
              </span>
            )}
          </div>

          <p className="pgraph-detail-desc">{nodeDesc(selectedNode.id, t)}</p>

          {selectedReason && (
            <p className="pgraph-detail-reason">
              <strong>{t("pgraph.detail.reason")}:</strong> {selectedReason}
            </p>
          )}

          {selectedNode.group === "source" && (
            <p className="pgraph-detail-meta">
              {selectedNode.inputFiles && selectedNode.inputFiles.length > 0
                ? t("pgraph.detail.sourceFiles", { files: selectedNode.inputFiles.join(", ") })
                : t("pgraph.detail.noSourceFiles")}
            </p>
          )}

          {selectedNode.id === "build" && selectedNode.buildSubsteps && selectedNode.buildSubsteps.length > 0 && (
            <dl className="pgraph-substeps">
              {selectedNode.buildSubsteps.map((sub) => (
                <div key={sub.key}>
                  <dt>
                    {sub.key === "pairs"
                      ? t("pgraph.buildSub.pairs")
                      : sub.key === "match"
                        ? t("pgraph.buildSub.match")
                        : t("pgraph.buildSub.sfm")}
                  </dt>
                  <dd className="num">{formatSecondsText(sub.seconds, t, fmt)}</dd>
                </div>
              ))}
            </dl>
          )}

          {selectedNode.id === "align" && selectedNode.alignSummary?.method && (
            <dl className="pgraph-substeps">
              <div>
                <dt>{t("job.alignMethod")}</dt>
                <dd>{t("job.alignArcore")}</dd>
              </div>
              {selectedNode.alignSummary.matched_frames !== undefined && (
                <div>
                  <dt>{t("job.alignMatched")}</dt>
                  <dd className="num">{fmt(selectedNode.alignSummary.matched_frames, 0)}</dd>
                </div>
              )}
              {selectedNode.alignSummary.residual_median_m !== undefined && (
                <div>
                  <dt>{t("job.alignMedian")}</dt>
                  <dd className="num">{t("job.alignMeters", { value: fmt(selectedNode.alignSummary.residual_median_m, 3) })}</dd>
                </div>
              )}
              {selectedNode.alignSummary.scale !== undefined && (
                <div>
                  <dt>{t("job.alignScale")}</dt>
                  <dd className="num">{fmt(selectedNode.alignSummary.scale, 3)}</dd>
                </div>
              )}
            </dl>
          )}

          {(selectedNode.id === "gate" || selectedNode.group === "decision") && selectedNode.gateSummary && (
            <dl className="pgraph-substeps">
              <div>
                <dt>{t("pgraph.detail.testPhotos")}</dt>
                <dd className="num">
                  {fmt(selectedNode.gateSummary.accepted, 0)} / {fmt(selectedNode.gateSummary.queries, 0)}
                </dd>
              </div>
              {selectedNode.id === "hold" && (
                <div>
                  <dt>{t("pgraph.detail.actualVersionStatus")}</dt>
                  <dd>
                    {selectedNode.matchedVersion
                      ? `v${selectedNode.matchedVersion.version} · ${translateVersionStatus(selectedNode.matchedVersion.status, t)}`
                      : t("pgraph.status.versionUnknown")}
                  </dd>
                </div>
              )}
            </dl>
          )}

          {selectedNode.id === "publish" && selectedNode.matchedVersion && (
            <dl className="pgraph-substeps">
              <div>
                <dt>{t("jobs.mapVersion")}</dt>
                <dd className="num">v{selectedNode.matchedVersion.version}</dd>
              </div>
              <div>
                <dt>{t("pgraph.detail.actualVersionStatus")}</dt>
                <dd>{translateVersionStatus(selectedNode.matchedVersion.status, t)}</dd>
              </div>
              {selectedNode.matchedVersion.published_by && (
                <div>
                  <dt>{t("maps.colPublishedBy")}</dt>
                  <dd>{selectedNode.matchedVersion.published_by}</dd>
                </div>
              )}
            </dl>
          )}

          {selectedNode.id === "splat" && selectedNode.state === "failed" && selectedNode.hasExistingSplatAsset && (
            <p className="pgraph-detail-meta" data-existing-splat-note="true">
              {t("pgraph.detail.existingSplatAssetNote")}
            </p>
          )}

          {selectedNode.id === "splat" && (
            <dl className="pgraph-substeps">
              {selectedNode.state === "failed" && selectedNode.hasExistingSplatAsset && (
                <div>
                  <dt>{t("pgraph.detail.previousSplatAsset")}</dt>
                  <dd>{t("pgraph.detail.previousSplatAssetAvailable")}</dd>
                </div>
              )}
              {selectedNode.splatStage && (
                <div>
                  <dt>{t("pgraph.detail.splatStage")}</dt>
                  <dd className="font-mono">{selectedNode.splatStage}</dd>
                </div>
              )}
              {selectedNode.splatTrainSeconds != null && (
                <div>
                  <dt>{t("pgraph.detail.splatTrainTime")}</dt>
                  <dd className="num">{formatSecondsText(selectedNode.splatTrainSeconds, t, fmt)}</dd>
                </div>
              )}
              {selectedNode.matchedVersion?.splat_summary?.gaussians != null && (
                <div>
                  <dt>{t("maps.splatGaussians")}</dt>
                  <dd className="num">{fmt(selectedNode.matchedVersion.splat_summary.gaussians, 0)}</dd>
                </div>
              )}
              {selectedNode.matchedVersion?.splat_summary?.psnr != null && (
                <div>
                  <dt>PSNR</dt>
                  <dd className="num">{fmt(selectedNode.matchedVersion.splat_summary.psnr, 2)} dB</dd>
                </div>
              )}
            </dl>
          )}
        </div>

        {/* Ringkasan durasi peta di bawah graph (terpisah dari waktu training 3D) */}
        <dl className="pgraph-timings">
          <div>
            <dt>{t("pgraph.timing.queue")}</dt>
            <dd className="num">{formatSecondsText(model.timings.queueSeconds, t, fmt)}</dd>
          </div>
          <div>
            <dt>{t("pgraph.timing.gpuWait")}</dt>
            <dd className="num">{formatSecondsText(model.timings.gpuWaitSeconds, t, fmt)}</dd>
          </div>
          <div>
            <dt>{t("pgraph.timing.reconstruct")}</dt>
            <dd className="num">{formatSecondsText(model.timings.reconstructSeconds, t, fmt)}</dd>
          </div>
          <div>
            <dt>{t("pgraph.timing.totalSinceQueue")}</dt>
            <dd className="num">{formatSecondsText(model.timings.totalSinceQueueSeconds, t, fmt)}</dd>
          </div>
          {model.timings.runningSinceStartSeconds !== null && (
            <div className="pgraph-timing-live">
              <dt>{t("pgraph.timing.sinceWorkerStart")}</dt>
              <dd className="num">{formatSecondsText(model.timings.runningSinceStartSeconds, t, fmt)}</dd>
            </div>
          )}
        </dl>
      </div>
    </Panel>
  );
}
