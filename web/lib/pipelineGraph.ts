import type { AlignmentSummary, GateSummary, Job, Version, Video } from "./api";

export const CORE_STAGE_IDS = [
  "extract",
  "build",
  "inspect",
  "register",
  "align",
  "gate",
] as const;

export type CoreStageId = (typeof CORE_STAGE_IDS)[number];

export const GRAPH_NODE_ORDER = [
  "video",
  "zip",
  "extract",
  "build",
  "inspect",
  "register",
  "align",
  "gate",
  "reject",
  "hold",
  "pass",
  "publish",
  "splat",
] as const;

export type GraphNodeId = (typeof GRAPH_NODE_ORDER)[number];

export type NodeVisualState =
  | "done"
  | "active"
  | "wait"
  | "warn"
  | "failed"
  | "skipped"
  | "legacy"
  | "optional"
  | "ready"
  | "unknown"
  | "pending"
  | "off";

export type WireVisualState = "done" | "active" | "warn" | "failed" | "idle" | "off";

export type GraphWireSpec = {
  id: string;
  from: GraphNodeId;
  to: GraphNodeId;
  state: WireVisualState;
  animated: boolean;
};

export type BuildSubstepTiming = {
  key: "pairs" | "match" | "reconstruction";
  seconds: number;
};

export type GraphNodeModel = {
  id: GraphNodeId;
  group: "source" | "core" | "decision" | "output";
  state: NodeVisualState;
  /** Durasi tercatat dari `summary.report.processing.stage_seconds[stage]` (termasuk 0), atau null. */
  recordedSeconds: number | null;
  /** Apakah node menampilkan baris durasi tahap (6 tahap inti). */
  showStageDuration: boolean;
  /** Kode status khusus untuk terjemahan label status node. */
  statusCode: string;
  /** Informasi tambahan terstruktur untuk panel detail. */
  reasonText: string | null;
  reasonCodes: string[];
  /** Daftar berkas input pemetaan untuk node sumber. */
  inputFiles?: string[];
  /** Rincian sub-tahap Build dari `summary.run.t_map_s` bila tersedia. */
  buildSubsteps?: BuildSubstepTiming[];
  /** Ringkasan align untuk panel detail. */
  alignSummary?: AlignmentSummary | null;
  /** Ringkasan gate untuk panel detail. */
  gateSummary?: GateSummary | null;
  /** Versi aktual yang cocok untuk node Publikasi / Ditahan / Build 3D. */
  matchedVersion?: Version | null;
  /** Tahap Splat saat berjalan/gagal (misalnya `gpu_wait`, `train`). */
  splatStage?: string | null;
  /** Durasi training 3D terpisah dari total peta (`splat_summary.train_seconds`). */
  splatTrainSeconds?: number | null;
  /** True bila versi masih memiliki aset Splat 3D dari build sebelumnya (misalnya saat rebuild gagal). */
  hasExistingSplatAsset?: boolean;
};

export type GraphTimings = {
  queueSeconds: number | null;
  gpuWaitSeconds: number | null;
  /** `total_s - gpu_wait_s` hanya bila keduanya tercatat. */
  reconstructSeconds: number | null;
  /** `queue_s + total_s` hanya bila keduanya tercatat. */
  totalSinceQueueSeconds: number | null;
  /** Durasi berjalan sejak `started_at` saat job berstatus `running`. */
  runningSinceStartSeconds: number | null;
  /** Durasi training 3D terpisah dari total peta. */
  splatTrainSeconds: number | null;
};

export type PipelineSummaryTone = "ok" | "live" | "warn" | "bad" | "idle";

export type PipelineGraphModel = {
  nodes: Record<GraphNodeId, GraphNodeModel>;
  wires: GraphWireSpec[];
  /** Node sumber keluaran pasca-rekonstruksi (`pass`, `hold`, atau `gate` untuk job lama). */
  outputOrigin: "pass" | "hold" | "gate";
  /** True bila keluaran pasca-rekonstruksi dihentikan karena penolakan Gate. */
  outputsBlockedByGate: boolean;
  timings: GraphTimings;
  completedCoreCount: number;
  totalCoreCount: number;
  summaryCode:
    | "done_publish"
    | "done_hold"
    | "done_legacy"
    | "failed_gate"
    | "failed_publish"
    | "failed_stage"
    | "failed_before_first"
    | "running_gpu_wait"
    | "running_stage"
    | "running_starting"
    | "queued"
    | "uploading"
    | "uploading_stalled"
    | "deleting"
    | "not_started";
  summaryTone: PipelineSummaryTone;
  activeCoreStage: CoreStageId | null;
  failedCoreStage: CoreStageId | null;
  gateDecision: "publish" | "hold" | "reject" | null;
  hasAnimatedWire: boolean;
  isStale: boolean;
  isVersionStale: boolean;
  defaultSelectedNode: GraphNodeId;
};

export type DerivePipelineGraphInput = {
  job: Job;
  /** Versi yang cocok dengan `job.map_version_id`, atau null bila tidak ditemukan / belum dimuat. */
  version: Version | null;
  /** True saat daftar versi masih pertama kali dimuat untuk job yang memiliki `map_version_id`. */
  versionLoading?: boolean;
  /** Pesan galat saat mengambil `/api/versions` (bila ada). */
  versionError?: string | null;
  /** Pesan galat aksi Publish dari halaman job (tidak mengubah riwayat rekonstruksi). */
  publishActionError?: string | null;
  /** True saat polling job gagal atau data terlambat: animasi dijeda sampai data segar tiba. */
  isStale?: boolean;
  /** True saat polling `/api/versions` gagal atau terlambat sementara polling job sehat: jeda kabel Build 3D sampai data versi segar tiba. */
  isVersionStale?: boolean;
  /** Waktu sekarang (epoch ms) untuk menghitung "Sejak worker mulai". */
  nowMs?: number;
};

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Cocokkan versi aktual dari `api.versions()` berdasarkan `job.map_version_id === version.id`. */
export function matchJobVersion(job: Job, versions: Version[] | null | undefined): Version | null {
  if (job.map_version_id == null || !versions?.length) return null;
  return versions.find((v) => v.id === job.map_version_id) ?? null;
}

/**
 * Deteksi sumber pemetaan aktif dari `job.videos` (`role === "peta"` dan `kind`).
 * Foto uji (`role !== "peta"`) tidak pernah menyalakan cabang input pemetaan.
 * Kompatibel dengan job lama tanpa `kind` (bawaan `"video"`) dan fallback `report.recording.source`.
 */
export function detectMappingInputs(job: Job): {
  hasVideo: boolean;
  hasFrames: boolean;
  videoFiles: string[];
  frameFiles: string[];
} {
  const videos: Video[] = Array.isArray(job.videos) ? job.videos : [];
  const mapItems = videos.filter((v) => v.role === "peta");
  const videoFiles: string[] = [];
  const frameFiles: string[] = [];

  for (const item of mapItems) {
    const kind = item.kind ?? "video";
    if (kind === "frames") {
      frameFiles.push(item.name);
    } else {
      videoFiles.push(item.name);
    }
  }

  let hasVideo = videoFiles.length > 0;
  let hasFrames = frameFiles.length > 0;

  // Kompatibilitas job historis yang daftar videonya kosong tetapi menyimpan sumber rekaman di report.
  if (!hasVideo && !hasFrames) {
    const recSource = job.summary?.report?.recording?.source;
    if (recSource === "arcore") hasFrames = true;
    else if (recSource === "video") hasVideo = true;
  }

  return { hasVideo, hasFrames, videoFiles, frameFiles };
}

function extractGateSummary(job: Job): GateSummary | null {
  const direct = job.summary?.gate;
  if (direct && (direct.decision === "publish" || direct.decision === "hold" || direct.decision === "reject")) {
    return direct;
  }
  const fromReport = job.summary?.report?.quality?.gate;
  if (
    fromReport &&
    (fromReport.decision === "publish" ||
      fromReport.decision === "hold" ||
      fromReport.decision === "reject")
  ) {
    return {
      decision: fromReport.decision,
      reasons: Array.isArray(fromReport.reasons) ? fromReport.reasons : [],
      queries: fromReport.queries ?? 0,
      accepted: fromReport.accepted ?? 0,
    };
  }
  return null;
}

function extractBuildSubsteps(job: Job): BuildSubstepTiming[] {
  const raw = job.summary?.run?.t_map_s ?? job.summary?.report?.processing?.map_stage_seconds;
  if (!raw || typeof raw !== "object") return [];
  const out: BuildSubstepTiming[] = [];
  const pairs = raw.pairs;
  const match = raw.match ?? raw.matching;
  const reconstruction = raw.reconstruction;
  if (isFiniteNumber(pairs)) out.push({ key: "pairs", seconds: pairs });
  if (isFiniteNumber(match)) out.push({ key: "match", seconds: match });
  if (isFiniteNumber(reconstruction)) out.push({ key: "reconstruction", seconds: reconstruction });
  return out;
}

function recordedStageSeconds(job: Job, stage: CoreStageId): number | null {
  const map = job.summary?.report?.processing?.stage_seconds;
  if (!map || typeof map !== "object") return null;
  const val = map[stage];
  return isFiniteNumber(val) ? val : null;
}

function isCoreStage(stage: string | null | undefined): stage is CoreStageId {
  return (CORE_STAGE_IDS as readonly string[]).includes(stage ?? "");
}

function firstErrorLine(error: string | null | undefined): string | null {
  if (!error) return null;
  const trimmed = error.trim();
  if (!trimmed) return null;
  const line = trimmed.split(/\r?\n/)[0]?.trim();
  return line || trimmed;
}

export function derivePipelineTimings(
  job: Job,
  version: Version | null,
  nowMs?: number,
): GraphTimings {
  const proc = job.summary?.report?.processing;
  const queueSeconds = isFiniteNumber(proc?.queue_s) ? proc.queue_s : null;
  const gpuWaitSeconds = isFiniteNumber(proc?.gpu_wait_s) ? proc.gpu_wait_s : null;
  const totalSeconds = isFiniteNumber(proc?.total_s) ? proc.total_s : null;

  // total_s sudah mencakup gpu_wait_s dari saat worker mulai.
  const reconstructSeconds =
    totalSeconds !== null && gpuWaitSeconds !== null
      ? Math.max(0, totalSeconds - gpuWaitSeconds)
      : null;

  const totalSinceQueueSeconds =
    queueSeconds !== null && totalSeconds !== null ? queueSeconds + totalSeconds : null;

  let runningSinceStartSeconds: number | null = null;
  if (job.status === "running" && job.started_at) {
    const startMs = Date.parse(job.started_at);
    const currentMs = nowMs ?? Date.now();
    if (Number.isFinite(startMs) && Number.isFinite(currentMs) && currentMs >= startMs) {
      runningSinceStartSeconds = Math.floor((currentMs - startMs) / 1000);
    }
  }

  const splatTrainSeconds = isFiniteNumber(version?.splat_summary?.train_seconds)
    ? version.splat_summary.train_seconds
    : null;

  return {
    queueSeconds,
    gpuWaitSeconds,
    reconstructSeconds,
    totalSinceQueueSeconds,
    runningSinceStartSeconds,
    splatTrainSeconds,
  };
}

export function derivePipelineGraph(input: DerivePipelineGraphInput): PipelineGraphModel {
  const {
    job,
    version,
    versionLoading = false,
    versionError = null,
    publishActionError = null,
    isStale = false,
    isVersionStale = false,
    nowMs,
  } = input;

  const status = job.status;
  const stage = job.stage;
  const inputs = detectMappingInputs(job);
  const align = job.summary?.align ?? null;
  const gate = extractGateSummary(job);
  const buildSubsteps = extractBuildSubsteps(job);
  const timings = derivePipelineTimings(job, version, nowMs);

  const publishFailedAtJobStage = status === "failed" && stage === "publish";
  const gateDecision = gate?.decision ?? null;
  const isGateRejected = gateDecision === "reject";
  const rejectedAtGate = status === "failed" && isGateRejected;
  const jobFinishedWithoutReject = status === "done" && !isGateRejected;
  const coreStageIdx = isCoreStage(stage) ? CORE_STAGE_IDS.indexOf(stage) : -1;

  // 1. Status 6 tahap inti (extract -> build -> inspect -> register -> align -> gate)
  const coreStates = {} as Record<CoreStageId, NodeVisualState>;
  const coreStatusCodes = {} as Record<CoreStageId, string>;
  const coreReasons = {} as Record<CoreStageId, string | null>;

  const reachedPastAlign =
    status === "done" ||
    publishFailedAtJobStage ||
    rejectedAtGate ||
    ((status === "running" || status === "failed") && stage === "gate");

  const reachedPastGate = status === "done" || publishFailedAtJobStage;

  for (let i = 0; i < CORE_STAGE_IDS.length; i++) {
    const id = CORE_STAGE_IDS[i];
    coreReasons[id] = null;

    if (status === "uploading" || status === "queued" || status === "deleting") {
      coreStates[id] = "pending";
      coreStatusCodes[id] = "pending";
      continue;
    }

    if (status === "running") {
      if (stage === "gpu_wait" || coreStageIdx < 0) {
        coreStates[id] = "pending";
        coreStatusCodes[id] = "pending";
      } else if (i < coreStageIdx) {
        coreStates[id] = "done";
        coreStatusCodes[id] = "done";
      } else if (i === coreStageIdx) {
        coreStates[id] = "active";
        coreStatusCodes[id] = "running";
      } else {
        coreStates[id] = "pending";
        coreStatusCodes[id] = "pending";
      }
      continue;
    }

    if (status === "failed") {
      if (publishFailedAtJobStage) {
        coreStates[id] = "done";
        coreStatusCodes[id] = "done";
      } else if (rejectedAtGate) {
        if (id === "gate") {
          coreStates[id] = "failed";
          coreStatusCodes[id] = "rejected";
          coreReasons[id] =
            gate?.reasons.map((r) => r.message).join("; ") || firstErrorLine(job.error);
        } else {
          coreStates[id] = "done";
          coreStatusCodes[id] = "done";
        }
      } else if (coreStageIdx >= 0) {
        if (i < coreStageIdx) {
          coreStates[id] = "done";
          coreStatusCodes[id] = "done";
        } else if (i === coreStageIdx) {
          coreStates[id] = "failed";
          coreStatusCodes[id] = "failed";
          coreReasons[id] = firstErrorLine(job.error);
        } else {
          coreStates[id] = "pending";
          coreStatusCodes[id] = "pending";
        }
      } else {
        coreStates[id] = "pending";
        coreStatusCodes[id] = "pending";
      }
      continue;
    }

    if (status === "done") {
      coreStates[id] = "done";
      coreStatusCodes[id] = "done";
      continue;
    }

    coreStates[id] = "pending";
    coreStatusCodes[id] = "pending";
  }

  // Sesuaikan Align (bedakan job historis tanpa Align dari hasil skipped eksplisit)
  if (reachedPastAlign || align !== null) {
    if (align) {
      if (align.status === "applied") {
        coreStates.align = "done";
        coreStatusCodes.align = "align_applied";
      } else if (align.status === "skipped") {
        coreStates.align = "skipped";
        coreStatusCodes.align = "align_skipped";
        coreReasons.align = align.reason ?? null;
      } else if (align.status === "failed") {
        coreStates.align = "warn";
        coreStatusCodes.align = "align_failed_continued";
        coreReasons.align = align.reason ?? null;
      }
    } else if (reachedPastAlign && status !== "running") {
      coreStates.align = "legacy";
      coreStatusCodes.align = "legacy_not_recorded";
    }
  }

  // Sesuaikan Gate (publish=lolos, hold=ditahan, reject=ditolak, atau job lama)
  if (reachedPastGate) {
    if (gate) {
      if (gate.decision === "publish") {
        coreStates.gate = "done";
        coreStatusCodes.gate = "gate_passed";
      } else if (gate.decision === "hold") {
        coreStates.gate = "warn";
        coreStatusCodes.gate = "gate_held";
        coreReasons.gate = gate.reasons.map((r) => r.message).join("; ") || null;
      } else if (gate.decision === "reject") {
        coreStates.gate = "failed";
        coreStatusCodes.gate = "rejected";
        coreReasons.gate =
          gate.reasons.map((r) => r.message).join("; ") || firstErrorLine(job.error);
      }
    } else {
      coreStates.gate = "legacy";
      coreStatusCodes.gate = "legacy_not_recorded";
    }
  }

  // 2. Sumber pemetaan (Video dan Paket foto berpose)
  const pastExtract =
    status === "done" ||
    publishFailedAtJobStage ||
    rejectedAtGate ||
    (status === "running" && coreStageIdx >= 0) ||
    (status === "failed" && coreStageIdx >= 0);

  function sourceNodeState(selected: boolean): { state: NodeVisualState; statusCode: string } {
    if (!selected) return { state: "off", statusCode: "source_unused" };
    if (status === "uploading") {
      return {
        state: job.stalled ? "warn" : "wait",
        statusCode: job.stalled ? "uploading_stalled" : "uploading",
      };
    }
    if (status === "queued" || (status === "running" && stage === "gpu_wait")) {
      return { state: "wait", statusCode: "source_ready" };
    }
    if (pastExtract) {
      return { state: "done", statusCode: "source_used" };
    }
    return { state: "wait", statusCode: "source_ready" };
  }

  const videoSrc = sourceNodeState(inputs.hasVideo);
  const zipSrc = sourceNodeState(inputs.hasFrames);

  // 3. Tiga cabang keputusan Gate
  const gateReasonText =
    gate?.reasons.map((r) => r.message).join("; ") ||
    (rejectedAtGate ? firstErrorLine(job.error) : null);
  const gateReasonCodes = gate?.reasons.map((r) => r.code) ?? [];
  const gateBranchesInactive =
    gateDecision !== null || reachedPastGate || (status === "failed" && stage === "gate");

  const rejectState: NodeVisualState =
    gateDecision === "reject" ? "failed" : gateBranchesInactive ? "off" : "pending";
  const holdState: NodeVisualState =
    gateDecision === "hold" ? "warn" : gateBranchesInactive ? "off" : "pending";
  const passState: NodeVisualState =
    gateDecision === "publish" ? "done" : gateBranchesInactive ? "off" : "pending";

  // 4. Keluaran Publikasi peta (dari status aktual Version yang cocok)
  let publishState: NodeVisualState = "pending";
  let publishStatusCode = "waiting_map";
  let publishReason: string | null = publishActionError ?? null;

  if (isGateRejected) {
    publishState = "off";
    publishStatusCode = "blocked_by_gate";
    publishReason = gateReasonText;
  } else if (publishFailedAtJobStage) {
    publishState = "failed";
    publishStatusCode = "publish_failed";
    publishReason = firstErrorLine(job.error) ?? publishActionError ?? null;
  } else if (status === "failed") {
    publishState = "off";
    publishStatusCode = "not_reached";
  } else if (!jobFinishedWithoutReject) {
    publishState = "pending";
    publishStatusCode = "waiting_map";
  } else if (job.map_version_id == null) {
    publishState = "unknown";
    publishStatusCode = "version_unknown";
  } else if (version === null) {
    if (versionLoading && !versionError) {
      publishState = "wait";
      publishStatusCode = "version_loading";
    } else {
      publishState = "unknown";
      publishStatusCode = "version_unknown";
      publishReason = versionError ?? publishActionError ?? null;
    }
  } else {
    if (version.status === "published") {
      publishState = "done";
      publishStatusCode = "version_published";
    } else if (version.status === "ready") {
      publishState = "ready";
      publishStatusCode = "version_ready";
    } else if (version.status === "candidate") {
      publishState = gateDecision === "hold" ? "warn" : "ready";
      publishStatusCode = "version_candidate";
    } else if (version.status === "retired") {
      publishState = "off";
      publishStatusCode = "version_retired";
    } else if (version.status === "rejected") {
      publishState = "failed";
      publishStatusCode = "version_rejected";
    } else {
      publishState = "unknown";
      publishStatusCode = "version_unknown";
    }
    if (publishActionError) {
      publishReason = publishActionError;
    }
  }

  // 5. Keluaran Build 3D (status job Splat independen)
  let splatState: NodeVisualState = "pending";
  let splatStatusCode = "waiting_map";
  let splatReason: string | null = null;
  let splatStage: string | null = null;

  if (isGateRejected) {
    splatState = "off";
    splatStatusCode = "blocked_by_gate";
  } else if (status === "failed" && !publishFailedAtJobStage) {
    splatState = "off";
    splatStatusCode = "not_reached";
  } else if (!jobFinishedWithoutReject && !publishFailedAtJobStage) {
    splatState = "pending";
    splatStatusCode = "waiting_map";
  } else if (job.map_version_id == null) {
    splatState = "optional";
    splatStatusCode = "splat_optional";
  } else if (version === null) {
    if (versionLoading && !versionError) {
      splatState = "wait";
      splatStatusCode = "version_loading";
    } else {
      splatState = "unknown";
      splatStatusCode = "version_unknown";
      splatReason = versionError ?? null;
    }
  } else {
    splatStage = version.splat_stage ?? null;
    if (version.splat_status === "queued") {
      splatState = "wait";
      splatStatusCode = "splat_queued";
    } else if (version.splat_status === "running") {
      if (version.splat_stage === "gpu_wait") {
        splatState = "wait";
        splatStatusCode = "splat_gpu_wait";
      } else if (version.splat_stage) {
        splatState = "active";
        splatStatusCode = "splat_running";
      } else {
        splatState = "wait";
        splatStatusCode = "splat_starting";
      }
    } else if (version.splat_status === "failed") {
      splatState = "failed";
      splatStatusCode = "splat_failed";
      splatReason = firstErrorLine(version.splat_error);
    } else if (version.splat_status === "done" || version.has_splat) {
      splatState = "done";
      splatStatusCode = "splat_done";
    } else {
      splatState = "optional";
      splatStatusCode = "splat_not_scheduled";
    }
  }

  // 6. Susun model 13 node
  const nodes: Record<GraphNodeId, GraphNodeModel> = {
    video: {
      id: "video",
      group: "source",
      state: videoSrc.state,
      recordedSeconds: null,
      showStageDuration: false,
      statusCode: videoSrc.statusCode,
      reasonText: null,
      reasonCodes: [],
      inputFiles: inputs.videoFiles,
    },
    zip: {
      id: "zip",
      group: "source",
      state: zipSrc.state,
      recordedSeconds: null,
      showStageDuration: false,
      statusCode: zipSrc.statusCode,
      reasonText: null,
      reasonCodes: [],
      inputFiles: inputs.frameFiles,
    },
    extract: {
      id: "extract",
      group: "core",
      state: coreStates.extract,
      recordedSeconds: recordedStageSeconds(job, "extract"),
      showStageDuration: true,
      statusCode: coreStatusCodes.extract,
      reasonText: coreReasons.extract,
      reasonCodes: [],
    },
    build: {
      id: "build",
      group: "core",
      state: coreStates.build,
      recordedSeconds: recordedStageSeconds(job, "build"),
      showStageDuration: true,
      statusCode: coreStatusCodes.build,
      reasonText: coreReasons.build,
      reasonCodes: [],
      buildSubsteps,
    },
    inspect: {
      id: "inspect",
      group: "core",
      state: coreStates.inspect,
      recordedSeconds: recordedStageSeconds(job, "inspect"),
      showStageDuration: true,
      statusCode: coreStatusCodes.inspect,
      reasonText: coreReasons.inspect,
      reasonCodes: [],
    },
    register: {
      id: "register",
      group: "core",
      state: coreStates.register,
      recordedSeconds: recordedStageSeconds(job, "register"),
      showStageDuration: true,
      statusCode: coreStatusCodes.register,
      reasonText: coreReasons.register,
      reasonCodes: [],
    },
    align: {
      id: "align",
      group: "core",
      state: coreStates.align,
      recordedSeconds: recordedStageSeconds(job, "align"),
      showStageDuration: true,
      statusCode: coreStatusCodes.align,
      reasonText: coreReasons.align,
      reasonCodes: align?.reason ? [align.reason] : [],
      alignSummary: align,
    },
    gate: {
      id: "gate",
      group: "core",
      state: coreStates.gate,
      recordedSeconds: recordedStageSeconds(job, "gate"),
      showStageDuration: true,
      statusCode: coreStatusCodes.gate,
      reasonText: coreReasons.gate,
      reasonCodes: gateReasonCodes,
      gateSummary: gate,
    },
    reject: {
      id: "reject",
      group: "decision",
      state: rejectState,
      recordedSeconds: null,
      showStageDuration: false,
      statusCode: gateDecision === "reject" ? "gate_branch_rejected" : "gate_branch_inactive",
      reasonText: gateDecision === "reject" ? gateReasonText : null,
      reasonCodes: gateDecision === "reject" ? gateReasonCodes : [],
      gateSummary: gate,
    },
    hold: {
      id: "hold",
      group: "decision",
      state: holdState,
      recordedSeconds: null,
      showStageDuration: false,
      statusCode: gateDecision === "hold" ? "gate_branch_held" : "gate_branch_inactive",
      reasonText: gateDecision === "hold" ? gateReasonText : null,
      reasonCodes: gateDecision === "hold" ? gateReasonCodes : [],
      gateSummary: gate,
      matchedVersion: version,
    },
    pass: {
      id: "pass",
      group: "decision",
      state: passState,
      recordedSeconds: null,
      showStageDuration: false,
      statusCode: gateDecision === "publish" ? "gate_branch_passed" : "gate_branch_inactive",
      reasonText: null,
      reasonCodes: [],
      gateSummary: gate,
    },
    publish: {
      id: "publish",
      group: "output",
      state: publishState,
      recordedSeconds: null,
      showStageDuration: false,
      statusCode: publishStatusCode,
      reasonText: publishReason,
      reasonCodes: [],
      matchedVersion: version,
    },
    splat: {
      id: "splat",
      group: "output",
      state: splatState,
      recordedSeconds: null,
      showStageDuration: false,
      statusCode: splatStatusCode,
      reasonText: splatReason,
      reasonCodes: [],
      matchedVersion: version,
      splatStage,
      splatTrainSeconds: timings.splatTrainSeconds,
      hasExistingSplatAsset: Boolean(version?.has_splat),
    },
  };

  // 7. Daftar kabel logis dan status animasi (tepat satu kabel aktif masuk ke tahap aktif)
  const wires: GraphWireSpec[] = [];

  function sourceWireState(selected: boolean): { state: WireVisualState; animated: boolean } {
    if (!selected) return { state: "off", animated: false };
    if (status === "running" && stage === "extract") {
      return { state: "active", animated: !isStale };
    }
    if (status === "failed" && stage === "extract") {
      return { state: "failed", animated: false };
    }
    if (
      status === "done" ||
      publishFailedAtJobStage ||
      rejectedAtGate ||
      ((status === "running" || status === "failed") && coreStageIdx > 0)
    ) {
      return { state: "done", animated: false };
    }
    return { state: "idle", animated: false };
  }

  const vWire = sourceWireState(inputs.hasVideo);
  const zWire = sourceWireState(inputs.hasFrames);
  wires.push(
    { id: "video-extract", from: "video", to: "extract", state: vWire.state, animated: vWire.animated },
    { id: "zip-extract", from: "zip", to: "extract", state: zWire.state, animated: zWire.animated },
  );

  for (let i = 0; i < CORE_STAGE_IDS.length - 1; i++) {
    const from = CORE_STAGE_IDS[i];
    const to = CORE_STAGE_IDS[i + 1];
    const toIdx = i + 1;
    let wState: WireVisualState = "idle";
    let animated = false;

    if (status === "running" && coreStageIdx === toIdx) {
      wState = "active";
      animated = !isStale;
    } else if (status === "failed" && !publishFailedAtJobStage && !rejectedAtGate && coreStageIdx === toIdx) {
      wState = "failed";
    } else if (
      status === "done" ||
      publishFailedAtJobStage ||
      rejectedAtGate ||
      ((status === "running" || status === "failed") && coreStageIdx > toIdx)
    ) {
      wState = from === "align" && coreStates.align === "warn" ? "warn" : "done";
    }

    wires.push({ id: `${from}-${to}`, from, to, state: wState, animated });
  }

  wires.push(
    {
      id: "gate-reject",
      from: "gate",
      to: "reject",
      state: gateDecision === "reject" ? "failed" : gateBranchesInactive ? "off" : "idle",
      animated: false,
    },
    {
      id: "gate-hold",
      from: "gate",
      to: "hold",
      state: gateDecision === "hold" ? "warn" : gateBranchesInactive ? "off" : "idle",
      animated: false,
    },
    {
      id: "gate-pass",
      from: "gate",
      to: "pass",
      state: gateDecision === "publish" ? "done" : gateBranchesInactive ? "off" : "idle",
      animated: false,
    },
  );

  const outputOrigin: "pass" | "hold" | "gate" =
    gateDecision === "hold" ? "hold" : reachedPastGate && gateDecision === null ? "gate" : "pass";

  let publishWireState: WireVisualState = "idle";
  if (isGateRejected || (status === "failed" && !publishFailedAtJobStage)) {
    publishWireState = "off";
  } else if (publishState === "failed") {
    publishWireState = "failed";
  } else if (publishState === "done") {
    publishWireState = "done";
  } else if (publishState === "warn") {
    publishWireState = "warn";
  } else if (jobFinishedWithoutReject) {
    publishWireState = gateDecision === "hold" ? "warn" : "done";
  }

  let splatWireState: WireVisualState = "idle";
  let splatWireAnimated = false;
  if (isGateRejected || (status === "failed" && !publishFailedAtJobStage)) {
    splatWireState = "off";
  } else if (splatState === "active") {
    splatWireState = "active";
    splatWireAnimated = !isStale && !isVersionStale;
  } else if (splatState === "done") {
    splatWireState = "done";
  } else if (splatState === "failed") {
    splatWireState = "failed";
  } else if (splatState === "wait") {
    splatWireState = "idle";
  } else if (splatState === "optional") {
    splatWireState = "off";
  }

  wires.push(
    {
      id: `${outputOrigin}-publish`,
      from: outputOrigin,
      to: "publish",
      state: publishWireState,
      animated: false,
    },
    {
      id: `${outputOrigin}-splat`,
      from: outputOrigin,
      to: "splat",
      state: splatWireState,
      animated: splatWireAnimated,
    },
  );

  // 8. Ringkasan header dan node default terpilih
  const completedCoreCount = CORE_STAGE_IDS.filter((id) => {
    const st = coreStates[id];
    return st === "done" || st === "skipped" || st === "warn";
  }).length;

  let summaryCode: PipelineGraphModel["summaryCode"] = "not_started";
  let summaryTone: PipelineSummaryTone = "idle";

  if (status === "done") {
    if (gateDecision === "hold") {
      summaryCode = "done_hold";
      summaryTone = "warn";
    } else if (gateDecision === "publish") {
      summaryCode = "done_publish";
      summaryTone = "ok";
    } else {
      summaryCode = "done_legacy";
      summaryTone = "ok";
    }
  } else if (status === "failed") {
    summaryTone = "bad";
    if (rejectedAtGate) summaryCode = "failed_gate";
    else if (publishFailedAtJobStage) summaryCode = "failed_publish";
    else if (coreStageIdx >= 0) summaryCode = "failed_stage";
    else summaryCode = "failed_before_first";
  } else if (status === "running") {
    if (stage === "gpu_wait") {
      summaryCode = "running_gpu_wait";
      summaryTone = "warn";
    } else if (coreStageIdx >= 0) {
      summaryCode = "running_stage";
      summaryTone = "live";
    } else {
      summaryCode = "running_starting";
      summaryTone = "live";
    }
  } else if (status === "queued") {
    summaryCode = "queued";
    summaryTone = "idle";
  } else if (status === "uploading") {
    summaryCode = job.stalled ? "uploading_stalled" : "uploading";
    summaryTone = job.stalled ? "bad" : "idle";
  } else if (status === "deleting") {
    summaryCode = "deleting";
    summaryTone = "idle";
  }

  let defaultSelectedNode: GraphNodeId = "extract";
  if (status === "running" && isCoreStage(stage)) {
    defaultSelectedNode = stage;
  } else if (rejectedAtGate) {
    defaultSelectedNode = "reject";
  } else if (publishFailedAtJobStage) {
    defaultSelectedNode = "publish";
  } else if (status === "failed" && isCoreStage(stage)) {
    defaultSelectedNode = stage;
  } else if (splatState === "active" || splatState === "failed") {
    defaultSelectedNode = "splat";
  } else if (gateDecision === "hold") {
    defaultSelectedNode = "hold";
  } else if (status === "done") {
    defaultSelectedNode = "publish";
  } else if (inputs.hasFrames && !inputs.hasVideo) {
    defaultSelectedNode = "zip";
  } else if (inputs.hasVideo) {
    defaultSelectedNode = "video";
  }

  return {
    nodes,
    wires,
    outputOrigin,
    outputsBlockedByGate: isGateRejected,
    timings,
    completedCoreCount,
    totalCoreCount: CORE_STAGE_IDS.length,
    summaryCode,
    summaryTone,
    activeCoreStage: status === "running" && isCoreStage(stage) ? stage : null,
    failedCoreStage: status === "failed" && !rejectedAtGate && isCoreStage(stage) ? stage : null,
    gateDecision,
    hasAnimatedWire: wires.some((w) => w.animated),
    isStale,
    isVersionStale,
    defaultSelectedNode,
  };
}
