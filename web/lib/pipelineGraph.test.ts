import { test } from "node:test";
import assert from "node:assert/strict";
import {
  CORE_STAGE_IDS,
  GRAPH_NODE_ORDER,
  derivePipelineGraph,
  detectMappingInputs,
  matchJobVersion,
  // @ts-expect-error Node's type stripping requires the .ts extension.
} from "./pipelineGraph.ts";
import {
  buildPipelineWires,
  type BoxRect,
  type GraphLayoutMode,
  type Point2D,
  type TileRect,
  // @ts-expect-error Node's type stripping requires the .ts extension.
} from "./pipelineWires.ts";
import type { Job, Version } from "./api";
import type { GraphNodeId } from "./pipelineGraph";

function baseJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 42,
    area_id: "floor-10",
    status: "queued",
    stage: null,
    created_by: "bagus@example.com",
    videos: [{ name: "scan.mp4", role: "peta", kind: "video", size: 120_000_000, uploaded: true }],
    summary: null,
    error: null,
    map_version_id: null,
    created_at: "2026-11-27T01:00:00Z",
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

function baseVersion(overrides: Partial<Version> = {}): Version {
  return {
    id: 10,
    area_id: "floor-10",
    building_id: 1,
    building_name: "HCM",
    navigation_ready: false,
    version: 3,
    status: "ready",
    created_at: "2026-11-27T01:10:00Z",
    published_by: null,
    job_id: 42,
    has_report: true,
    has_splat: false,
    splat_status: null,
    splat_stage: null,
    splat_error: null,
    splat_summary: null,
    ...overrides,
  };
}

function makeTile(cx: number, top: number): TileRect {
  return {
    left: cx - 21,
    right: cx + 21,
    top,
    bottom: top + 42,
    cx,
    cy: top + 21,
  };
}

function syntheticTiles(layout: GraphLayoutMode): { tiles: Record<GraphNodeId, TileRect>; canvasWidth: number } {
  if (layout === "wide") {
    const col = (i: number) => 60 + i * 116;
    const row = (r: number) => 20 + r * 96;
    return {
      canvasWidth: 860,
      tiles: {
        video: makeTile(col(0), row(0)),
        zip: makeTile(col(0), row(2)),
        extract: makeTile(col(1), row(1)),
        build: makeTile(col(2), row(1)),
        inspect: makeTile(col(3), row(1)),
        register: makeTile(col(4), row(1)),
        align: makeTile(col(5), row(1)),
        gate: makeTile(col(6), row(1)),
        reject: makeTile(col(4), row(3)),
        hold: makeTile(col(5), row(3)),
        pass: makeTile(col(6), row(3)),
        splat: makeTile(col(5), row(4)),
        publish: makeTile(col(6), row(4)),
      },
    };
  }
  if (layout === "medium") {
    const col = (i: number) => 110 + i * 180;
    const row = (r: number) => 20 + r * 96;
    return {
      canvasWidth: 600,
      tiles: {
        video: makeTile(col(0), row(0)),
        zip: makeTile(col(1), row(0)),
        extract: makeTile(col(0), row(1)),
        build: makeTile(col(1), row(1)),
        inspect: makeTile(col(2), row(1)),
        gate: makeTile(col(0), row(2)),
        align: makeTile(col(1), row(2)),
        register: makeTile(col(2), row(2)),
        reject: makeTile(col(0), row(3)),
        hold: makeTile(col(1), row(3)),
        pass: makeTile(col(2), row(3)),
        splat: makeTile(col(1), row(4)),
        publish: makeTile(col(2), row(4)),
      },
    };
  }
  const order = GRAPH_NODE_ORDER;
  const tiles = {} as Record<GraphNodeId, TileRect>;
  order.forEach((id, i) => {
    tiles[id] = makeTile(55, 16 + i * 60);
  });
  return { canvasWidth: 320, tiles };
}

function segmentsOverlap(a1: Point2D, a2: Point2D, b1: Point2D, b2: Point2D): boolean {
  const eps = 0.5;
  // Horizontal collinear overlap
  if (Math.abs(a1[1] - a2[1]) < eps && Math.abs(b1[1] - b2[1]) < eps && Math.abs(a1[1] - b1[1]) < eps) {
    const lo = Math.max(Math.min(a1[0], a2[0]), Math.min(b1[0], b2[0]));
    const hi = Math.min(Math.max(a1[0], a2[0]), Math.max(b1[0], b2[0]));
    return hi - lo > 1.5;
  }
  // Vertical collinear overlap
  if (Math.abs(a1[0] - a2[0]) < eps && Math.abs(b1[0] - b2[0]) < eps && Math.abs(a1[0] - b1[0]) < eps) {
    const lo = Math.max(Math.min(a1[1], a2[1]), Math.min(b1[1], b2[1]));
    const hi = Math.min(Math.max(a1[1], a2[1]), Math.max(b1[1], b2[1]));
    return hi - lo > 1.5;
  }
  return false;
}

test("workflow order keeps core stages strictly sequential", () => {
  assert.deepEqual([...CORE_STAGE_IDS], ["extract", "build", "inspect", "register", "align", "gate"]);
  assert.deepEqual(GRAPH_NODE_ORDER.slice(2, 8), ["extract", "build", "inspect", "register", "align", "gate"]);
});

test("detectMappingInputs ignores test (uji) files and supports legacy entries without kind", () => {
  const job = baseJob({
    videos: [
      { name: "legacy-map.mp4", role: "peta", size: null, uploaded: null } as Job["videos"][number],
      { name: "query-photos.zip", role: "uji", kind: "frames", size: 5_000_000, uploaded: true },
    ],
  });
  const inputs = detectMappingInputs(job);
  assert.equal(inputs.hasVideo, true);
  assert.equal(inputs.hasFrames, false);
  assert.deepEqual(inputs.videoFiles, ["legacy-map.mp4"]);
  assert.deepEqual(inputs.frameFiles, []);
});

test("queued and running/gpu_wait keep all wires idle", () => {
  for (const job of [
    baseJob({ status: "uploading", stage: null }),
    baseJob({ status: "queued", stage: null }),
    baseJob({ status: "running", stage: "gpu_wait", started_at: "2026-11-27T01:01:00Z" }),
  ]) {
    const model = derivePipelineGraph({
      job,
      version: null,
      nowMs: Date.parse("2026-11-27T01:02:15Z"),
    });
    assert.equal(model.wires.filter((w) => w.animated).length, 0);
    assert.equal(model.hasAnimatedWire, false);
    if (job.stage === "gpu_wait") {
      assert.equal(model.summaryCode, "running_gpu_wait");
      assert.equal(model.timings.runningSinceStartSeconds, 75);
    }
  }
});

test("running on build animates exactly one incoming wire", () => {
  const job = baseJob({
    status: "running",
    stage: "build",
    started_at: "2026-11-27T01:00:00Z",
  });
  const model = derivePipelineGraph({
    job,
    version: null,
    nowMs: Date.parse("2026-11-27T01:03:20Z"),
  });
  const animated = model.wires.filter((w) => w.animated);
  assert.equal(animated.length, 1);
  assert.equal(animated[0].id, "extract-build");
  assert.equal(model.nodes.extract.state, "done");
  assert.equal(model.nodes.build.state, "active");
  assert.equal(model.nodes.inspect.state, "pending");
  assert.equal(model.timings.runningSinceStartSeconds, 200);
});

test("running on extract animates only active mapping source wire", () => {
  const job = baseJob({
    status: "running",
    stage: "extract",
    videos: [
      { name: "capture.zip", role: "peta", kind: "frames", size: 30_000_000, uploaded: true },
      { name: "test.mp4", role: "uji", kind: "video", size: 10_000_000, uploaded: true },
    ],
  });
  const model = derivePipelineGraph({ job, version: null });
  assert.deepEqual(
    model.wires.filter((w) => w.animated).map((w) => w.id),
    ["zip-extract"],
  );
  assert.equal(model.nodes.video.state, "off");
  assert.equal(model.nodes.zip.state, "done");
});

test("failed before gate stops animation, marks failed stage, leaves subsequent stages pending", () => {
  const job = baseJob({
    status: "failed",
    stage: "build",
    error: "command failed (exit 1): run.py\ntraceback...",
  });
  const model = derivePipelineGraph({ job, version: null });
  assert.equal(model.wires.filter((w) => w.animated).length, 0);
  assert.equal(model.nodes.extract.state, "done");
  assert.equal(model.nodes.build.state, "failed");
  assert.equal(model.nodes.build.reasonText, "command failed (exit 1): run.py");
  assert.equal(model.nodes.inspect.state, "pending");
  assert.equal(model.nodes.publish.state, "off");
  assert.equal(model.nodes.splat.state, "off");
});

test("align skipped and align failed continue to gate and remain distinct from legacy missing align", () => {
  const skippedJob = baseJob({
    status: "done",
    stage: "gate",
    map_version_id: 10,
    summary: {
      align: { status: "skipped", reason: "no_frames" },
      gate: { decision: "publish", reasons: [], queries: 10, accepted: 9 },
    },
  });
  const skippedModel = derivePipelineGraph({ job: skippedJob, version: baseVersion() });
  assert.equal(skippedModel.nodes.align.state, "skipped");
  assert.equal(skippedModel.nodes.align.statusCode, "align_skipped");
  assert.equal(skippedModel.nodes.gate.state, "done");

  const alignFailedJob = baseJob({
    status: "done",
    stage: "gate",
    map_version_id: 10,
    summary: {
      align: { status: "failed", reason: "sim3 solver diverged" },
      gate: { decision: "publish", reasons: [], queries: 10, accepted: 9 },
    },
  });
  const failedModel = derivePipelineGraph({ job: alignFailedJob, version: baseVersion() });
  assert.equal(failedModel.nodes.align.state, "warn");
  assert.equal(failedModel.nodes.align.statusCode, "align_failed_continued");
  assert.equal(failedModel.nodes.pass.state, "done");

  const legacyJob = baseJob({
    status: "done",
    stage: "register",
    map_version_id: 10,
    summary: { run: { map_images: 120, map_registered: 118 } },
  });
  const legacyModel = derivePipelineGraph({ job: legacyJob, version: baseVersion({ status: "published" }) });
  assert.equal(legacyModel.nodes.align.state, "legacy");
  assert.equal(legacyModel.nodes.gate.state, "legacy");
  assert.equal(legacyModel.outputOrigin, "gate");
  assert.equal(legacyModel.nodes.publish.statusCode, "version_published");
});

test("gate reject stops post-reconstruction outputs and highlights only reject branch", () => {
  const job = baseJob({
    status: "failed",
    stage: "gate",
    error: "Rejected by the test-photo gate: The map has 2 disconnected parts",
    summary: {
      align: { status: "applied" },
      gate: {
        decision: "reject",
        reasons: [{ code: "map_fragmented", message: "The map has 2 disconnected parts" }],
        queries: 10,
        accepted: 4,
      },
    },
  });
  const model = derivePipelineGraph({ job, version: null });
  assert.equal(model.outputsBlockedByGate, true);
  assert.equal(model.nodes.reject.state, "failed");
  assert.equal(model.nodes.hold.state, "off");
  assert.equal(model.nodes.pass.state, "off");
  assert.equal(model.nodes.publish.state, "off");
  assert.equal(model.nodes.splat.state, "off");
});

test("gate hold highlights hold branch while preserving actual version and splat status", () => {
  const job = baseJob({
    status: "done",
    stage: "gate",
    map_version_id: 10,
    summary: {
      align: { status: "skipped", reason: "no_frames" },
      gate: {
        decision: "hold",
        reasons: [{ code: "no_test_photos", message: "No test photos were provided" }],
        queries: 0,
        accepted: 0,
      },
    },
  });
  const model = derivePipelineGraph({ job, version: baseVersion({ status: "candidate" }) });
  assert.equal(model.outputOrigin, "hold");
  assert.equal(model.nodes.hold.state, "warn");
  assert.equal(model.nodes.publish.statusCode, "version_candidate");
  assert.equal(model.nodes.splat.statusCode, "splat_not_scheduled");
});

test("publish node shows published ONLY when matched version is published, and unknown when unavailable", () => {
  const job = baseJob({
    status: "done",
    stage: "gate",
    map_version_id: 10,
    summary: {
      align: { status: "applied" },
      gate: { decision: "publish", reasons: [], queries: 10, accepted: 10 },
    },
  });
  assert.equal(derivePipelineGraph({ job, version: baseVersion({ status: "ready" }) }).nodes.publish.statusCode, "version_ready");
  assert.equal(derivePipelineGraph({ job, version: baseVersion({ status: "published" }) }).nodes.publish.statusCode, "version_published");
  assert.equal(derivePipelineGraph({ job, version: null }).nodes.publish.statusCode, "version_unknown");
  assert.equal(matchJobVersion(job, [baseVersion({ id: 9 }), baseVersion({ id: 10 })])?.id, 10);
});

test("publish failure preserves completed reconstruction stage history", () => {
  const job = baseJob({
    status: "failed",
    stage: "publish",
    error: "reload timed out",
    summary: {
      align: { status: "applied" },
      gate: { decision: "publish", reasons: [], queries: 8, accepted: 8 },
    },
  });
  const model = derivePipelineGraph({ job, version: baseVersion({ status: "ready" }) });
  for (const id of CORE_STAGE_IDS) assert.equal(model.nodes[id].state, "done");
  assert.equal(model.nodes.publish.state, "failed");
});

test("splat animates wire ONLY when running outside gpu_wait", () => {
  const job = baseJob({
    status: "done",
    stage: "gate",
    map_version_id: 10,
    summary: {
      align: { status: "applied" },
      gate: { decision: "publish", reasons: [], queries: 10, accepted: 9 },
    },
  });

  const gpuWait = derivePipelineGraph({
    job,
    version: baseVersion({ splat_status: "running", splat_stage: "gpu_wait" }),
  });
  assert.equal(gpuWait.wires.filter((w) => w.animated).length, 0);

  const train = derivePipelineGraph({
    job,
    version: baseVersion({ splat_status: "running", splat_stage: "train" }),
  });
  assert.deepEqual(
    train.wires.filter((w) => w.animated).map((w) => w.id),
    ["pass-splat"],
  );
});

test("stage_seconds preserves zero values and map totals stay separate from 3D training time", () => {
  const job = baseJob({
    status: "done",
    stage: "gate",
    map_version_id: 10,
    summary: {
      run: { t_map_s: { pairs: 3.1, match: 41.5, reconstruction: 92.4 } },
      align: { status: "applied" },
      gate: { decision: "publish", reasons: [], queries: 10, accepted: 10 },
      report: {
        version: 1,
        processing: {
          queue_s: 12,
          gpu_wait_s: 30,
          total_s: 210,
          stage_seconds: { extract: 14.5, build: 145.2, inspect: 18.1, register: 0, align: 2.0, gate: 0.2 },
        },
      },
    },
  });
  const version = baseVersion({
    status: "published",
    splat_status: "done",
    has_splat: true,
    splat_summary: { gaussians: 250_000, psnr: 25.1, ssim: 0.85, lpips: 0.21, train_seconds: 960, built_at: "2026-11-27T01:40:00Z" },
  });
  const model = derivePipelineGraph({ job, version });
  assert.equal(model.nodes.register.recordedSeconds, 0);
  assert.equal(model.timings.reconstructSeconds, 180);
  assert.equal(model.timings.totalSinceQueueSeconds, 222);
  assert.equal(model.timings.splatTrainSeconds, 960);
});

test("stale polling pauses wire animation while preserving last known state", () => {
  const job = baseJob({ status: "running", stage: "build" });
  const staleModel = derivePipelineGraph({ job, version: null, isStale: true });
  assert.equal(staleModel.nodes.build.state, "active");
  assert.equal(staleModel.hasAnimatedWire, false);
});

test("version poll failure pauses Build 3D wire while job polling remains healthy", () => {
  const job = baseJob({
    status: "done",
    stage: "gate",
    map_version_id: 10,
    summary: {
      align: { status: "applied" },
      gate: { decision: "publish", reasons: [], queries: 10, accepted: 10 },
    },
  });
  const version = baseVersion({ status: "published", splat_status: "running", splat_stage: "train" });

  const healthy = derivePipelineGraph({ job, version, isStale: false, isVersionStale: false });
  assert.equal(healthy.nodes.splat.state, "active");
  assert.deepEqual(
    healthy.wires.filter((w) => w.animated).map((w) => w.id),
    ["pass-splat"],
  );

  const versionStale = derivePipelineGraph({
    job,
    version,
    isStale: false,
    isVersionStale: true,
    versionError: "503 version endpoint delayed",
  });
  assert.equal(versionStale.isStale, false);
  assert.equal(versionStale.isVersionStale, true);
  assert.equal(versionStale.nodes.publish.statusCode, "version_published");
  assert.equal(versionStale.nodes.splat.state, "active");
  assert.equal(versionStale.wires.find((w) => w.id === "pass-splat")?.state, "active");
  assert.equal(versionStale.wires.find((w) => w.id === "pass-splat")?.animated, false);
  assert.equal(versionStale.hasAnimatedWire, false);
});

test("splat_status failed with has_splat true shows failed state and reason while noting existing asset separately", () => {
  const job = baseJob({
    status: "done",
    stage: "gate",
    map_version_id: 10,
    summary: {
      align: { status: "applied" },
      gate: { decision: "publish", reasons: [], queries: 10, accepted: 10 },
    },
  });
  const version = baseVersion({
    status: "published",
    has_splat: true,
    splat_status: "failed",
    splat_stage: "train",
    splat_error: "CUDA out of memory during rebuild\ntraceback...",
    splat_summary: null,
  });

  const model = derivePipelineGraph({ job, version });
  assert.equal(model.nodes.splat.state, "failed");
  assert.equal(model.nodes.splat.statusCode, "splat_failed");
  assert.equal(model.nodes.splat.splatStage, "train");
  assert.equal(model.nodes.splat.splatTrainSeconds, null);
  assert.equal(model.nodes.splat.reasonText, "CUDA out of memory during rebuild");
  assert.equal(model.nodes.splat.hasExistingSplatAsset, true);
  assert.equal(model.wires.find((w) => w.id === "pass-splat")?.state, "failed");
  assert.equal(model.wires.find((w) => w.id === "pass-splat")?.animated, false);
  assert.equal(model.defaultSelectedNode, "splat");
});

test("buildPipelineWires emits zero overlapping shared segments across wide, medium, and narrow layouts", () => {
  const scenarios = [
    // Build running
    derivePipelineGraph({ job: baseJob({ status: "running", stage: "build" }), version: null }),
    // Published + 3D running
    derivePipelineGraph({
      job: baseJob({
        status: "done",
        stage: "gate",
        map_version_id: 10,
        summary: {
          align: { status: "applied" },
          gate: { decision: "publish", reasons: [], queries: 10, accepted: 10 },
        },
      }),
      version: baseVersion({ status: "published", splat_status: "running", splat_stage: "train" }),
    }),
    // Gate hold
    derivePipelineGraph({
      job: baseJob({
        status: "done",
        stage: "gate",
        map_version_id: 10,
        summary: {
          align: { status: "skipped", reason: "no_frames" },
          gate: { decision: "hold", reasons: [{ code: "no_test_photos", message: "none" }], queries: 0, accepted: 0 },
        },
      }),
      version: baseVersion({ status: "candidate" }),
    }),
    // Legacy job without Gate/Align (gate bypass to outputs)
    derivePipelineGraph({
      job: baseJob({
        status: "done",
        stage: "register",
        map_version_id: 10,
        summary: { run: { map_images: 120, map_registered: 118 } },
      }),
      version: baseVersion({ status: "published", splat_status: "running", splat_stage: "train" }),
    }),
  ];

  for (const layout of ["wide", "medium", "narrow"] as GraphLayoutMode[]) {
    const { tiles, canvasWidth } = syntheticTiles(layout);
    for (const model of scenarios) {
      const geom = buildPipelineWires({
        wires: model.wires,
        outputOrigin: model.outputOrigin,
        outputsBlockedByGate: model.outputsBlockedByGate,
        layout,
        tiles,
        canvasWidth,
      });

      // Extract atomic straight segments from all baseSegments and verify zero collinear overlap (no stroke stacking!)
      const atomic: Array<{ id: string; a: Point2D; b: Point2D }> = [];
      for (const seg of geom.baseSegments) {
        for (let i = 0; i < seg.points.length - 1; i++) {
          atomic.push({ id: seg.id, a: seg.points[i], b: seg.points[i + 1] });
        }
      }
      for (let i = 0; i < atomic.length; i++) {
        for (let j = i + 1; j < atomic.length; j++) {
          assert.equal(
            segmentsOverlap(atomic[i].a, atomic[i].b, atomic[j].a, atomic[j].b),
            false,
            `Overlapping stroke detected in ${layout}: ${atomic[i].id} vs ${atomic[j].id}`,
          );
        }
      }
    }
  }
});

test("buildPipelineWires routes side rails strictly outside wide text labels", () => {
  const holdModel = derivePipelineGraph({
    job: baseJob({
      status: "done",
      stage: "gate",
      map_version_id: 10,
      summary: {
        align: { status: "skipped", reason: "no_frames" },
        gate: { decision: "hold", reasons: [{ code: "no_test_photos", message: "none" }], queries: 0, accepted: 0 },
      },
    }),
    version: baseVersion({ status: "candidate" }),
  });

  // Wide layout: wide Gate label below tile must not be crossed by gate-trunk vertical rail
  const wide = syntheticTiles("wide");
  const wideCopies: Partial<Record<GraphNodeId, BoxRect>> = {
    gate: { left: wide.tiles.gate.cx - 46, right: wide.tiles.gate.cx + 46, top: wide.tiles.gate.bottom + 6, bottom: wide.tiles.gate.bottom + 36 },
  };
  const wideGeom = buildPipelineWires({
    wires: holdModel.wires,
    outputOrigin: holdModel.outputOrigin,
    outputsBlockedByGate: holdModel.outputsBlockedByGate,
    layout: "wide",
    tiles: wide.tiles,
    copies: wideCopies,
    canvasWidth: wide.canvasWidth,
  });
  const gateTrunk = wideGeom.baseSegments.find((s) => s.id === "gate-trunk")!;
  assert.ok(gateTrunk.points[1][0] > wideCopies.gate!.right, `Expected gate-trunk railX (${gateTrunk.points[1][0]}) > copy.right (${wideCopies.gate!.right})`);

  // Medium layout: wide Video label below tile must not be crossed by video-branch vertical rail
  const med = syntheticTiles("medium");
  const medCopies: Partial<Record<GraphNodeId, BoxRect>> = {
    video: { left: med.tiles.video.cx - 56, right: med.tiles.video.cx + 56, top: med.tiles.video.bottom + 6, bottom: med.tiles.video.bottom + 34 },
  };
  const medGeom = buildPipelineWires({
    wires: holdModel.wires,
    outputOrigin: holdModel.outputOrigin,
    outputsBlockedByGate: holdModel.outputsBlockedByGate,
    layout: "medium",
    tiles: med.tiles,
    copies: medCopies,
    canvasWidth: med.canvasWidth,
  });
  const videoBranch = medGeom.baseSegments.find((s) => s.id === "video-branch")!;
  assert.ok(videoBranch.points[1][0] < medCopies.video!.left, `Expected video-branch leftRail (${videoBranch.points[1][0]}) < copy.left (${medCopies.video!.left})`);
});
