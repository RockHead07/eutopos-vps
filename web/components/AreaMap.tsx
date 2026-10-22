"use client";

import { useMemo, useRef, useState } from "react";
import type { PlanMeta, Room, StrokeMode, WalkableData, XY } from "@/lib/api";
import { overlayImage } from "@/lib/walkable";

export type MapMode = "view" | "walkable" | "rooms" | "test";

type Props = {
  plan: PlanMeta;
  imageUrl: string;
  rooms: Room[];
  walkable: WalkableData | null;
  mode: MapMode;
  editable: boolean;
  brush: { mode: StrokeMode; radius: number };
  onPick: (p: XY) => void;
  onMoveRoom?: (roomId: number, p: XY) => void;
  onStroke?: (mode: StrokeMode, radius: number, points: XY[]) => void;
  route?: XY[];
  start?: XY | null;
  pending?: XY | null;
  marker?: XY | null;
  arrivalTarget?: XY | null;
};

const MIN_STEP_M = 0.05; // jarak minimum antar titik goresan

/** Peta 2D lantai: jalur scan, area walkable (overlay), ruangan, dan rute uji.
 *  Piksel dari meter (sama dengan server/floorplan.py): px = (x - origin_x) / res_m,
 *  py = height - 1 - (y - origin_y) / res_m. */
export function AreaMap(props: Props) {
  const { plan, imageUrl, rooms, walkable, mode, editable, brush } = props;
  const svg = useRef<SVGSVGElement>(null);
  const [dragRoom, setDragRoom] = useState<{ id: number; at: XY } | null>(null);
  const [stroke, setStroke] = useState<XY[] | null>(null); // goresan yang sedang digambar (untuk gambar)
  const strokeRef = useRef<XY[] | null>(null); // sama, untuk logika: event cepat tidak melihat state basi
  const [cursor, setCursor] = useState<XY | null>(null);
  const justDragged = useRef(false); // click menyusul pointerup: jangan dianggap klik di peta
  const overlay = useMemo(() => (walkable ? overlayImage(walkable) : ""), [walkable]);

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
  const line = 0.06 / plan.res_m; // garis setebal 6 cm di peta
  const labelSize = Math.max(plan.width, plan.height) * 0.018; // ukuran huruf mengikuti lebar peta
  const brushing = editable && mode === "walkable";
  const dragging = editable && mode === "rooms";

  let overlayBox: { x: number; y: number; w: number; h: number } | null = null;
  if (walkable) {
    const [left, top] = px([walkable.origin[0], walkable.origin[1] + walkable.height * walkable.cell_m]);
    overlayBox = {
      x: left,
      y: top,
      w: (walkable.width * walkable.cell_m) / plan.res_m,
      h: (walkable.height * walkable.cell_m) / plan.res_m,
    };
  }

  return (
    <svg
      ref={svg}
      viewBox={`0 0 ${plan.width} ${plan.height}`}
      className="w-full h-auto rounded-xl border border-border bg-white touch-none select-none"
      style={brushing ? { cursor: "none" } : undefined}
      onPointerDown={(e) => {
        if (!brushing) return;
        e.currentTarget.setPointerCapture(e.pointerId);
        strokeRef.current = [toMeters(e)];
        setStroke(strokeRef.current);
      }}
      onPointerMove={(e) => {
        const p = toMeters(e);
        if (brushing) {
          setCursor(p);
          const cur = strokeRef.current;
          if (cur) {
            const last = cur[cur.length - 1];
            if (Math.hypot(p[0] - last[0], p[1] - last[1]) >= MIN_STEP_M) {
              strokeRef.current = [...cur, p];
              setStroke(strokeRef.current);
            }
          }
        }
        if (dragRoom) setDragRoom({ ...dragRoom, at: p });
      }}
      onPointerLeave={() => setCursor(null)}
      onPointerUp={(e) => {
        if (strokeRef.current) {
          props.onStroke?.(brush.mode, brush.radius, strokeRef.current);
          strokeRef.current = null;
          setStroke(null);
          justDragged.current = true;
          return;
        }
        if (!dragRoom) return;
        props.onMoveRoom?.(dragRoom.id, toMeters(e));
        justDragged.current = true;
        setDragRoom(null);
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
      {overlay && overlayBox && (
        <image
          href={overlay}
          x={overlayBox.x}
          y={overlayBox.y}
          width={overlayBox.w}
          height={overlayBox.h}
          preserveAspectRatio="none"
          style={{ imageRendering: "pixelated" }}
          pointerEvents="none"
        />
      )}
      <polyline
        points={plan.trajectory.map((p) => px(p).join(",")).join(" ")}
        fill="none"
        stroke="#90AB8B"
        strokeWidth={line * 0.6}
        opacity={0.5}
        pointerEvents="none"
      />
      {props.route && props.route.length > 1 && (
        <polyline
          points={props.route.map((p) => px(p).join(",")).join(" ")}
          fill="none"
          stroke="#E07A2E"
          strokeWidth={line * 1.6}
          strokeLinejoin="round"
          strokeLinecap="round"
          pointerEvents="none"
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
          strokeWidth={line * 0.5}
          pointerEvents="none"
        />
      )}
      {stroke && (
        <polyline
          points={stroke.map((p) => px(p).join(",")).join(" ")}
          fill="none"
          stroke={brush.mode === "paint" ? "#5A7863" : "#B4452E"}
          strokeOpacity={0.4}
          strokeWidth={(2 * brush.radius) / plan.res_m}
          strokeLinecap="round"
          strokeLinejoin="round"
          pointerEvents="none"
        />
      )}
      {rooms.map((r) => {
        const p = dragRoom?.id === r.id ? dragRoom.at : ([r.x, r.y] as XY);
        const [cx, cy] = px(p);
        const left = cx > plan.width * 0.7;
        return (
          <g
            key={r.id}
            className={dragging ? "cursor-move" : undefined}
            onPointerDown={(e) => {
              if (!dragging) return;
              e.stopPropagation();
              setDragRoom({ id: r.id, at: [r.x, r.y] });
            }}
          >
            <circle cx={cx} cy={cy} r={line * 2.4} fill="#FBFCF7" stroke="#1C2421" strokeWidth={line * 0.6} />
            <text
              x={left ? cx - line * 3.5 : cx + line * 3.5}
              y={cy + labelSize * 0.35}
              textAnchor={left ? "end" : "start"}
              fontSize={labelSize}
              fill="#1C2421"
              fontWeight={600}
              stroke="#FFFFFF"
              strokeWidth={labelSize * 0.25}
              paintOrder="stroke"
              pointerEvents="none"
            >
              {r.name}
            </text>
          </g>
        );
      })}
      {[props.start, props.pending].map(
        (p, i) =>
          p && <circle key={i} cx={px(p)[0]} cy={px(p)[1]} r={line * 2} fill={i ? "#2F6FB0" : "#1C2421"} pointerEvents="none" />,
      )}
      {props.marker && (
        <circle cx={px(props.marker)[0]} cy={px(props.marker)[1]} r={line * 2.6} fill="#E07A2E" stroke="#FBFCF7" strokeWidth={line * 0.6} pointerEvents="none" />
      )}
      {brushing && cursor && (
        <circle
          cx={px(cursor)[0]}
          cy={px(cursor)[1]}
          r={brush.radius / plan.res_m}
          fill="none"
          stroke={brush.mode === "paint" ? "#5A7863" : "#B4452E"}
          strokeWidth={line * 0.5}
          pointerEvents="none"
        />
      )}
    </svg>
  );
}
