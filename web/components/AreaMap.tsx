"use client";

import { useRef, useState } from "react";
import type { AreaGraph, PlanMeta, XY } from "@/lib/api";

export type MapMode = "view" | "rooms" | "routes" | "test";

type Props = {
  plan: PlanMeta;
  imageUrl: string;
  graph: AreaGraph;
  mode: MapMode;
  editable: boolean;
  onPick: (p: XY) => void;
  onMoveRoom?: (roomId: number, p: XY) => void;
  onMoveNode?: (from: XY, to: XY) => void;
  onEdgeClick?: (a: XY, b: XY) => void;
  route?: XY[];
  start?: XY | null;
  pending?: XY | null;
  marker?: XY | null;
  arrivalTarget?: XY | null;
};

/** Peta 2D lantai dengan lapisan jalur scan, graf rute, ruangan, dan rute uji.
 *  Piksel dari meter (sama dengan server/floorplan.py): px = (x - origin_x) / res_m,
 *  py = height - 1 - (y - origin_y) / res_m. */
export function AreaMap(props: Props) {
  const { plan, imageUrl, graph, mode, editable } = props;
  const svg = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<{ kind: "room" | "node"; id: string; from: XY; at: XY } | null>(null);
  const justDragged = useRef(false); // click menyusul pointerup: jangan dianggap klik di peta

  const px = ([x, y]: XY): XY => [(x - plan.origin_x) / plan.res_m, plan.height - 1 - (y - plan.origin_y) / plan.res_m];
  const toMeters = (e: React.PointerEvent): XY => {
    const s = svg.current!;
    const pt = s.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(s.getScreenCTM()!.inverse());
    const x = plan.origin_x + p.x * plan.res_m;
    const y = plan.origin_y + (plan.height - 1 - p.y) * plan.res_m;
    return [Math.round(x * 100) / 100, Math.round(y * 100) / 100];
  };
  const nodes = new Map(graph.draft.nodes.map((n) => [n.id, [n.x, n.y] as XY]));
  const roomIds = new Set(graph.rooms.map((r) => `R${r.id}`));
  const stroke = 0.06 / plan.res_m; // garis setebal 6 cm di peta
  const canDrag = editable && (mode === "rooms" || mode === "routes");

  return (
    <svg
      ref={svg}
      viewBox={`0 0 ${plan.width} ${plan.height}`}
      className="w-full h-auto rounded-xl border border-border bg-white touch-none select-none"
      onPointerMove={(e) => drag && setDrag({ ...drag, at: toMeters(e) })}
      onPointerUp={(e) => {
        if (!drag) return;
        const to = toMeters(e);
        if (drag.kind === "room") props.onMoveRoom?.(Number(drag.id), to);
        else props.onMoveNode?.(drag.from, to);
        justDragged.current = true;
        setDrag(null);
      }}
      onClick={(e) => {
        if (justDragged.current) {
          justDragged.current = false;
          return;
        }
        props.onPick(toMeters(e as unknown as React.PointerEvent));
      }}
    >
      <image href={imageUrl} width={plan.width} height={plan.height} />
      <polyline
        points={plan.trajectory.map((p) => px(p).join(",")).join(" ")}
        fill="none"
        stroke="#90AB8B"
        strokeWidth={stroke * 0.6}
        opacity={0.7}
      />
      {graph.draft.edges.map(([a, b]) => {
        const pa = nodes.get(a)!;
        const pb = nodes.get(b)!;
        const room = roomIds.has(a) || roomIds.has(b);
        return (
          <line
            key={`${a}-${b}`}
            x1={px(pa)[0]}
            y1={px(pa)[1]}
            x2={px(pb)[0]}
            y2={px(pb)[1]}
            stroke={room ? "#90AB8B" : "#5A7863"}
            strokeWidth={stroke}
            strokeDasharray={room ? `${stroke * 2} ${stroke}` : undefined}
            className={editable && mode === "routes" && !room ? "cursor-pointer" : undefined}
            onClick={(e) => {
              if (!(editable && mode === "routes") || room) return;
              e.stopPropagation();
              props.onEdgeClick?.(pa, pb);
            }}
          />
        );
      })}
      {graph.draft.nodes
        .filter((n) => !roomIds.has(n.id))
        .map((n) => {
          const p = drag?.kind === "node" && drag.id === n.id ? drag.at : ([n.x, n.y] as XY);
          return (
            <circle
              key={n.id}
              cx={px(p)[0]}
              cy={px(p)[1]}
              r={stroke * 1.4}
              fill="#5A7863"
              className={canDrag && mode === "routes" ? "cursor-move" : undefined}
              onPointerDown={(e) => {
                if (!(canDrag && mode === "routes")) return;
                e.stopPropagation();
                setDrag({ kind: "node", id: n.id, from: [n.x, n.y], at: [n.x, n.y] });
              }}
            />
          );
        })}
      {props.route && props.route.length > 1 && (
        <polyline
          points={props.route.map((p) => px(p).join(",")).join(" ")}
          fill="none"
          stroke="#E07A2E"
          strokeWidth={stroke * 1.6}
          strokeLinejoin="round"
        />
      )}
      {props.arrivalTarget && (
        <circle
          cx={px(props.arrivalTarget)[0]}
          cy={px(props.arrivalTarget)[1]}
          r={1.0 / plan.res_m}
          fill="#E07A2E"
          opacity={0.12}
          stroke="#E07A2E"
          strokeWidth={stroke * 0.5}
        />
      )}
      {graph.rooms.map((r) => {
        const p = drag?.kind === "room" && drag.id === String(r.id) ? drag.at : ([r.x, r.y] as XY);
        const [cx, cy] = px(p);
        return (
          <g
            key={r.id}
            className={canDrag && mode === "rooms" ? "cursor-move" : undefined}
            onPointerDown={(e) => {
              if (!(canDrag && mode === "rooms")) return;
              e.stopPropagation();
              setDrag({ kind: "room", id: String(r.id), from: [r.x, r.y], at: [r.x, r.y] });
            }}
          >
            <circle cx={cx} cy={cy} r={stroke * 2.4} fill="#FBFCF7" stroke="#1C2421" strokeWidth={stroke * 0.6} />
            <text
              x={cx > plan.width * 0.7 ? cx - stroke * 3 : cx + stroke * 3}
              y={cy + stroke}
              textAnchor={cx > plan.width * 0.7 ? "end" : "start"}
              fontSize={stroke * 5}
              fill="#1C2421"
              fontWeight={600}
            >
              {r.name}
            </text>
          </g>
        );
      })}
      {[props.start, props.pending].map(
        (p, i) =>
          p && (
            <circle key={i} cx={px(p)[0]} cy={px(p)[1]} r={stroke * 2} fill={i ? "#2F6FB0" : "#1C2421"} />
          ),
      )}
      {props.marker && (
        <circle cx={px(props.marker)[0]} cy={px(props.marker)[1]} r={stroke * 2.6} fill="#E07A2E" stroke="#FBFCF7" strokeWidth={stroke * 0.6} />
      )}
    </svg>
  );
}
