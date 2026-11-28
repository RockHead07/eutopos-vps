import type { GraphNodeId, GraphWireSpec, WireVisualState } from "./pipelineGraph";

export type GraphLayoutMode = "wide" | "medium" | "narrow";
export type PortSide = "l" | "r" | "t" | "b";

export type BoxRect = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export type TileRect = BoxRect & {
  cx: number;
  cy: number;
};

export type Point2D = [number, number];

export type WireSegmentPath = {
  id: string;
  d: string;
  state: WireVisualState;
  /** Segmen poligon mentah untuk pemeriksaan geometri / non-tumpang-tindih di tes. */
  points: Point2D[];
};

export type FlowPulsePath = {
  id: string;
  d: string;
  points: Point2D[];
};

export type BuiltWireGeometry = {
  baseSegments: WireSegmentPath[];
  flowPulses: FlowPulsePath[];
  activePorts: Partial<Record<GraphNodeId, PortSide[]>>;
};

const WIRE_PRIORITY: Record<WireVisualState, number> = {
  off: 0,
  idle: 1,
  done: 2,
  warn: 3,
  failed: 3,
  active: 4,
};

function higherState(...states: WireVisualState[]): WireVisualState {
  let best: WireVisualState = "off";
  for (const st of states) {
    if (WIRE_PRIORITY[st] > WIRE_PRIORITY[best]) {
      best = st;
    }
  }
  return best;
}

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

/** Konversi polyline ortogonal menjadi path SVG dengan sudut membulat halus. */
export function roundedPolylinePath(rawPoints: Point2D[], cornerRadius = 6): string {
  const points: Point2D[] = [];
  for (const pt of rawPoints) {
    const prev = points[points.length - 1];
    if (!prev || Math.hypot(pt[0] - prev[0], pt[1] - prev[1]) > 0.25) {
      points.push(pt);
    }
  }
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${fmt(points[0][0])} ${fmt(points[0][1])}`;

  const toward = (a: Point2D, b: Point2D, len: number): Point2D => {
    const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (d < 1e-6) return a;
    const r = len / d;
    return [a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r];
  };

  const parts: string[] = [`M ${fmt(points[0][0])} ${fmt(points[0][1])}`];
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const next = points[i + 1];
    const d1 = Math.hypot(curr[0] - prev[0], curr[1] - prev[1]);
    const d2 = Math.hypot(next[0] - curr[0], next[1] - curr[1]);
    const cross = (curr[0] - prev[0]) * (next[1] - curr[1]) - (curr[1] - prev[1]) * (next[0] - curr[0]);
    if (Math.abs(cross) < 0.05) continue;
    const radius = Math.min(cornerRadius, d1 / 2, d2 / 2);
    if (radius < 0.5) {
      parts.push(`L ${fmt(curr[0])} ${fmt(curr[1])}`);
      continue;
    }
    const pIn = toward(curr, prev, radius);
    const pOut = toward(curr, next, radius);
    parts.push(`L ${fmt(pIn[0])} ${fmt(pIn[1])}`);
    parts.push(`Q ${fmt(curr[0])} ${fmt(curr[1])} ${fmt(pOut[0])} ${fmt(pOut[1])}`);
  }
  const last = points[points.length - 1];
  parts.push(`L ${fmt(last[0])} ${fmt(last[1])}`);
  return parts.join(" ");
}

function portPoint(tile: TileRect, side: PortSide): Point2D {
  switch (side) {
    case "l":
      return [tile.left, tile.cy];
    case "r":
      return [tile.right, tile.cy];
    case "t":
      return [tile.cx, tile.top];
    case "b":
      return [tile.cx, tile.bottom];
  }
}

export function buildPipelineWires(params: {
  wires: GraphWireSpec[];
  outputOrigin: "pass" | "hold" | "gate";
  outputsBlockedByGate: boolean;
  layout: GraphLayoutMode;
  tiles: Partial<Record<GraphNodeId, TileRect>>;
  /** Bounding box teks label/durasi tiap node agar rel kabel tidak pernah memotong teks. */
  copies?: Partial<Record<GraphNodeId, BoxRect>>;
  canvasWidth: number;
}): BuiltWireGeometry {
  const { wires, outputOrigin, outputsBlockedByGate, layout, tiles, copies = {}, canvasWidth } = params;
  const wireById = new Map<string, GraphWireSpec>(wires.map((w) => [w.id, w]));

  const baseSegments: WireSegmentPath[] = [];
  const flowPulses: FlowPulsePath[] = [];
  const portSets = new Map<GraphNodeId, Set<PortSide>>();

  const markPort = (id: GraphNodeId, side: PortSide) => {
    if (!portSets.has(id)) portSets.set(id, new Set());
    portSets.get(id)!.add(side);
  };

  const addSeg = (id: string, points: Point2D[], state: WireVisualState, radius = 6) => {
    baseSegments.push({ id, d: roundedPolylinePath(points, radius), state, points });
  };

  const addFlow = (id: string, points: Point2D[], radius = 6) => {
    flowPulses.push({ id, d: roundedPolylinePath(points, radius), points });
  };

  const getPort = (id: GraphNodeId, side: PortSide): Point2D | null => {
    const t = tiles[id];
    if (!t) return null;
    markPort(id, side);
    return portPoint(t, side);
  };

  /** Gabungan batas kiri/kanan/bawah kotak ikon dan label teksnya. */
  const outerOf = (id: GraphNodeId): BoxRect | null => {
    const t = tiles[id];
    if (!t) return null;
    const c = copies[id];
    if (!c) return t;
    return {
      left: Math.min(t.left, c.left),
      right: Math.max(t.right, c.right),
      top: Math.min(t.top, c.top),
      bottom: Math.max(t.bottom, c.bottom),
    };
  };

  /** Hitung posisi Y horizontal bus di ruang kosong antara baris atas dan baris target. */
  const gapBusY = (aboveIds: GraphNodeId[], targetIds: GraphNodeId[]): number => {
    const targetTop = Math.min(...targetIds.map((id) => tiles[id]?.top ?? Infinity));
    const aboveBottom = Math.max(...aboveIds.map((id) => outerOf(id)?.bottom ?? -Infinity));
    if (Number.isFinite(aboveBottom) && targetTop - aboveBottom >= 10) {
      return (aboveBottom + targetTop) / 2;
    }
    return targetTop - 11;
  };

  const vSpec = wireById.get("video-extract");
  const zSpec = wireById.get("zip-extract");

  // 1. Input fan-in (Video + Paket foto -> Extract) tanpa stroke bertumpuk di batang bersama
  if (vSpec && zSpec && tiles.video && tiles.zip && tiles.extract) {
    const tv = tiles.video;
    const tz = tiles.zip;
    const te = tiles.extract;
    const ov = outerOf("video")!;
    const oz = outerOf("zip")!;
    const oe = outerOf("extract")!;

    if (layout === "wide") {
      const pv = getPort("video", "r")!;
      const pz = getPort("zip", "r")!;
      const pe = getPort("extract", "l")!;
      const col1Right = Math.max(ov.right, oz.right);
      const mergeX =
        oe.left - col1Right >= 8 ? (col1Right + oe.left) / 2 : (Math.max(tv.right, tz.right) + te.left) / 2;
      const trunkStart: Point2D = [mergeX, te.cy];

      addSeg("video-branch", [pv, [mergeX, tv.cy], trunkStart], vSpec.state);
      addSeg("zip-branch", [pz, [mergeX, tz.cy], trunkStart], zSpec.state);
      addSeg("inputs-trunk", [trunkStart, pe], higherState(vSpec.state, zSpec.state));

      if (vSpec.animated) addFlow("video-extract", [pv, [mergeX, tv.cy], trunkStart, pe]);
      if (zSpec.animated) addFlow("zip-extract", [pz, [mergeX, tz.cy], trunkStart, pe]);
    } else if (layout === "medium") {
      const pv = getPort("video", "l")!;
      const pz = getPort("zip", "l")!;
      const pe = getPort("extract", "t")!;
      const busY = gapBusY(["video", "zip"], ["extract"]);
      const leftRail = Math.max(10, Math.min(ov.left, oe.left) - 10);
      const midX = oz.left - ov.right >= 6 ? (ov.right + oz.left) / 2 : (tv.right + tz.left) / 2;
      const mergePt: Point2D = [te.cx, busY];

      addSeg("video-branch", [pv, [leftRail, tv.cy], [leftRail, busY], mergePt], vSpec.state);
      addSeg("zip-branch", [pz, [midX, tz.cy], [midX, busY], mergePt], zSpec.state);
      addSeg("inputs-trunk", [mergePt, pe], higherState(vSpec.state, zSpec.state));

      if (vSpec.animated) addFlow("video-extract", [pv, [leftRail, tv.cy], [leftRail, busY], mergePt, pe]);
      if (zSpec.animated) addFlow("zip-extract", [pz, [midX, tz.cy], [midX, busY], mergePt, pe]);
    } else {
      // Narrow / mobile: zip -> extract vertikal langsung; video -> extract lewat rel kiri
      const pv = getPort("video", "l")!;
      const pz = getPort("zip", "b")!;
      const peTop = getPort("extract", "t")!;
      const peLeft = getPort("extract", "l")!;
      const leftRail = Math.max(10, Math.min(tv.left, te.left) - 12);

      addSeg("video-extract", [pv, [leftRail, tv.cy], [leftRail, te.cy], peLeft], vSpec.state);
      addSeg("zip-extract", [pz, peTop], zSpec.state);

      if (vSpec.animated) addFlow("video-extract", [pv, [leftRail, tv.cy], [leftRail, te.cy], peLeft]);
      if (zSpec.animated) addFlow("zip-extract", [pz, peTop]);
    }
  }

  // 2. Rangkaian 6 tahap inti (Extract -> Build -> Inspect -> Register -> Align -> Gate)
  const corePairs: Array<[GraphNodeId, GraphNodeId]> = [
    ["extract", "build"],
    ["build", "inspect"],
    ["inspect", "register"],
    ["register", "align"],
    ["align", "gate"],
  ];

  for (let i = 0; i < corePairs.length; i++) {
    const [from, to] = corePairs[i];
    const spec = wireById.get(`${from}-${to}`);
    const tf = tiles[from];
    const tt = tiles[to];
    if (!spec || !tf || !tt) continue;

    if (layout === "narrow") {
      const p1 = getPort(from, "b")!;
      const p2 = getPort(to, "t")!;
      addSeg(spec.id, [p1, p2], spec.state);
      if (spec.animated) addFlow(spec.id, [p1, p2]);
    } else if (layout === "wide" || i < 2) {
      const p1 = getPort(from, "r")!;
      const p2 = getPort(to, "l")!;
      addSeg(spec.id, [p1, p2], spec.state);
      if (spec.animated) addFlow(spec.id, [p1, p2]);
    } else if (i === 2) {
      // Medium folded turn: Inspect -> Register lewat rel kanan di luar label Inspect & Register
      const p1 = getPort(from, "r")!;
      const p2 = getPort(to, "r")!;
      const of = outerOf(from)!;
      const ot = outerOf(to)!;
      const railX = Math.min(canvasWidth - 10, Math.max(of.right, ot.right) + 10);
      const pts: Point2D[] = [p1, [railX, tf.cy], [railX, tt.cy], p2];
      addSeg(spec.id, pts, spec.state);
      if (spec.animated) addFlow(spec.id, pts);
    } else {
      // Medium baris kedua kanan -> kiri (Register -> Align -> Gate)
      const p1 = getPort(from, "l")!;
      const p2 = getPort(to, "r")!;
      addSeg(spec.id, [p1, p2], spec.state);
      if (spec.animated) addFlow(spec.id, [p1, p2]);
    }
  }

  // 3. Cabang keputusan Gate (Gate -> Ditolak, Ditahan, Lolos) dengan batang bersama tunggal
  const gReject = wireById.get("gate-reject");
  const gHold = wireById.get("gate-hold");
  const gPass = wireById.get("gate-pass");
  const pubSpec = wireById.get(`${outputOrigin}-publish`);
  const splatSpec = wireById.get(`${outputOrigin}-splat`);
  const legacyBypassActive =
    !outputsBlockedByGate && outputOrigin === "gate" && Boolean(pubSpec && splatSpec && tiles.publish && tiles.splat);
  let legacyWideGateRailX: number | null = null;
  let legacyMedGateRailX: number | null = null;

  if (gReject && gHold && gPass && tiles.gate && tiles.reject && tiles.hold && tiles.pass) {
    const tg = tiles.gate;
    const tr = tiles.reject;
    const th = tiles.hold;
    const tp = tiles.pass;
    const og = outerOf("gate")!;
    const gateBranchState = higherState(gPass.state, gHold.state, gReject.state);
    const outBranchState =
      legacyBypassActive && pubSpec && splatSpec ? higherState(pubSpec.state, splatSpec.state) : "off";

    if (layout === "wide") {
      const pg = getPort("gate", "r")!;
      const pr = getPort("reject", "t")!;
      const ph = getPort("hold", "t")!;
      const pp = getPort("pass", "t")!;
      const railX = Math.min(canvasWidth - 18, og.right + 12);
      const busY = gapBusY(["register", "align", "gate"], ["reject", "hold", "pass"]);

      if (legacyBypassActive) {
        legacyWideGateRailX = railX;
        addSeg("gate-out-stub", [pg, [railX, tg.cy]], higherState(gateBranchState, outBranchState));
        addSeg("gate-trunk", [[railX, tg.cy], [railX, busY], [tp.cx, busY]], gateBranchState);
      } else {
        addSeg("gate-trunk", [pg, [railX, tg.cy], [railX, busY], [tp.cx, busY]], gateBranchState);
      }
      addSeg("gate-pass", [[tp.cx, busY], pp], gPass.state);
      addSeg("gate-spine-ph", [[tp.cx, busY], [th.cx, busY]], higherState(gHold.state, gReject.state));
      addSeg("gate-hold", [[th.cx, busY], ph], gHold.state);
      addSeg("gate-reject", [[th.cx, busY], [tr.cx, busY], pr], gReject.state);
    } else if (layout === "medium") {
      const pg = getPort("gate", "l")!;
      const pr = getPort("reject", "t")!;
      const ph = getPort("hold", "t")!;
      const pp = getPort("pass", "t")!;
      const or = outerOf("reject")!;
      const railX = Math.max(16, Math.min(og.left, or.left) - 10);
      const busY = gapBusY(["gate", "align", "register"], ["reject", "hold", "pass"]);

      if (legacyBypassActive) {
        legacyMedGateRailX = railX;
        addSeg("gate-out-stub", [pg, [railX, tg.cy]], higherState(gateBranchState, outBranchState));
        addSeg("gate-trunk", [[railX, tg.cy], [railX, busY], [tr.cx, busY]], gateBranchState);
      } else {
        addSeg("gate-trunk", [pg, [railX, tg.cy], [railX, busY], [tr.cx, busY]], gateBranchState);
      }
      addSeg("gate-reject", [[tr.cx, busY], pr], gReject.state);
      addSeg("gate-spine-rh", [[tr.cx, busY], [th.cx, busY]], higherState(gHold.state, gPass.state));
      addSeg("gate-hold", [[th.cx, busY], ph], gHold.state);
      addSeg("gate-pass", [[th.cx, busY], [tp.cx, busY], pp], gPass.state);
    } else {
      // Narrow / mobile: rel kiri dalam (-12 px) untuk ketiga cabang Gate
      const pg = getPort("gate", "l")!;
      const pr = getPort("reject", "l")!;
      const ph = getPort("hold", "l")!;
      const pp = getPort("pass", "l")!;
      const railX = Math.max(14, tg.left - 12);

      addSeg("gate-trunk", [pg, [railX, tg.cy], [railX, tr.cy]], gateBranchState);
      addSeg("gate-reject", [[railX, tr.cy], pr], gReject.state);
      addSeg("gate-spine-rh", [[railX, tr.cy], [railX, th.cy]], higherState(gHold.state, gPass.state));
      addSeg("gate-hold", [[railX, th.cy], ph], gHold.state);
      addSeg("gate-pass", [[railX, th.cy], [railX, tp.cy], pp], gPass.state);
    }
  }

  // 4. Cabang keluaran pasca-rekonstruksi (Publikasi peta & Build 3D), berhenti saat ditolak di Gate
  const toTile = tiles[outputOrigin];
  const tPub = tiles.publish;
  const tSplat = tiles.splat;

  if (!outputsBlockedByGate && pubSpec && splatSpec && toTile && tPub && tSplat) {
    if (layout === "wide" || layout === "medium") {
      const pPub = getPort("publish", "t")!;
      const pSplat = getPort("splat", "t")!;
      const busY = gapBusY(["reject", "hold", "pass"], ["splat", "publish"]);
      const oOrig = outerOf(outputOrigin)!;

      if (outputOrigin === "pass") {
        const pOrig = getPort("pass", "r")!;
        const oPub = outerOf("publish")!;
        const railX = Math.min(canvasWidth - 10, Math.max(oOrig.right, oPub.right) + 12);
        addSeg(
          "output-trunk",
          [pOrig, [railX, toTile.cy], [railX, busY], [tPub.cx, busY]],
          higherState(pubSpec.state, splatSpec.state),
        );
        addSeg("output-publish", [[tPub.cx, busY], pPub], pubSpec.state);
        addSeg("output-splat", [[tPub.cx, busY], [tSplat.cx, busY], pSplat], splatSpec.state);
        if (splatSpec.animated) {
          addFlow(splatSpec.id, [pOrig, [railX, toTile.cy], [railX, busY], [tSplat.cx, busY], pSplat]);
        }
      } else if (outputOrigin === "hold") {
        const pOrig = getPort("hold", "r")!;
        const oPass = outerOf("pass");
        const midX =
          oPass && oPass.left - oOrig.right >= 6
            ? (oOrig.right + oPass.left) / 2
            : oOrig.right + 12;
        addSeg("output-trunk", [pOrig, [midX, toTile.cy], [midX, busY]], higherState(pubSpec.state, splatSpec.state));
        addSeg("output-splat", [[midX, busY], [tSplat.cx, busY], pSplat], splatSpec.state);
        addSeg("output-publish", [[midX, busY], [tPub.cx, busY], pPub], pubSpec.state);
        if (splatSpec.animated) {
          addFlow(splatSpec.id, [pOrig, [midX, toTile.cy], [midX, busY], [tSplat.cx, busY], pSplat]);
        }
      } else {
        // Job lama tanpa Gate: lanjut dari ujung stub Gate lewat rel luar tanpa tumpang tindih stroke
        if (layout === "wide") {
          const pOrig = getPort("gate", "r")!;
          const oPass = outerOf("pass");
          const startPt: Point2D = legacyWideGateRailX != null ? [legacyWideGateRailX, toTile.cy] : pOrig;
          const railX = Math.min(
            canvasWidth - 6,
            Math.max(oOrig.right, oPass?.right ?? oOrig.right, legacyWideGateRailX ?? oOrig.right) + 10,
          );
          addSeg(
            "output-trunk",
            [startPt, [railX, toTile.cy], [railX, busY], [tPub.cx, busY]],
            higherState(pubSpec.state, splatSpec.state),
          );
          addSeg("output-publish", [[tPub.cx, busY], pPub], pubSpec.state);
          addSeg("output-splat", [[tPub.cx, busY], [tSplat.cx, busY], pSplat], splatSpec.state);
          if (splatSpec.animated) {
            addFlow(splatSpec.id, [pOrig, [railX, toTile.cy], [railX, busY], [tSplat.cx, busY], pSplat]);
          }
        } else {
          const pOrig = getPort("gate", "l")!;
          const oReject = outerOf("reject");
          const startPt: Point2D = legacyMedGateRailX != null ? [legacyMedGateRailX, toTile.cy] : pOrig;
          const railX = Math.max(
            6,
            Math.min(oOrig.left, oReject?.left ?? oOrig.left, legacyMedGateRailX ?? oOrig.left) - 10,
          );
          addSeg(
            "output-trunk",
            [startPt, [railX, toTile.cy], [railX, busY], [tSplat.cx, busY]],
            higherState(pubSpec.state, splatSpec.state),
          );
          addSeg("output-splat", [[tSplat.cx, busY], pSplat], splatSpec.state);
          addSeg("output-publish", [[tSplat.cx, busY], [tPub.cx, busY], pPub], pubSpec.state);
          if (splatSpec.animated) {
            addFlow(splatSpec.id, [pOrig, [railX, toTile.cy], [railX, busY], [tSplat.cx, busY], pSplat]);
          }
        }
      }
    } else {
      // Narrow / mobile: keluar dari port bawah origin -> rel kiri luar (-22 px) -> cabang ke Publikasi dan Build 3D
      const pOrig = getPort(outputOrigin, "b")!;
      const pPub = getPort("publish", "l")!;
      const pSplat = getPort("splat", "l")!;
      const dropY = toTile.bottom + 6;
      const railX = Math.max(6, Math.min(toTile.left, tPub.left, tSplat.left) - 22);

      addSeg(
        "output-trunk",
        [pOrig, [toTile.cx, dropY], [railX, dropY], [railX, tPub.cy]],
        higherState(pubSpec.state, splatSpec.state),
      );
      addSeg("output-publish", [[railX, tPub.cy], pPub], pubSpec.state);
      addSeg("output-splat", [[railX, tPub.cy], [railX, tSplat.cy], pSplat], splatSpec.state);
      if (splatSpec.animated) {
        addFlow(splatSpec.id, [pOrig, [toTile.cx, dropY], [railX, dropY], [railX, tSplat.cy], pSplat]);
      }
    }
  }

  baseSegments.sort((a, b) => WIRE_PRIORITY[a.state] - WIRE_PRIORITY[b.state]);

  const activePorts: Partial<Record<GraphNodeId, PortSide[]>> = {};
  for (const [nodeId, sides] of portSets.entries()) {
    activePorts[nodeId] = Array.from(sides);
  }

  return { baseSegments, flowPulses, activePorts };
}
