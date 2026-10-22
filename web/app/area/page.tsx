"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AreaMap, type MapMode } from "@/components/AreaMap";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import {
  api,
  areaApi,
  formatDate,
  photoUrl,
  planImageUrl,
  type AreaGraph,
  type PlanMeta,
  type RouteResult,
  type StrokeMode,
  type WalkableData,
  type XY,
} from "@/lib/api";
import { PageHead } from "@/lib/PageHead";
import { usePoll } from "@/lib/usePoll";

const MODES: { id: MapMode; label: string; hint: string }[] = [
  { id: "view", label: "View", hint: "Click anywhere on the scan path to see the real photo taken there." },
  { id: "walkable", label: "Walkable", hint: "Paint where people may walk and erase desks and walls. Routes are drawn straight across the green area." },
  { id: "rooms", label: "Rooms", hint: "Click on the map to add a room. Drag a room to move it." },
  { id: "test", label: "Test route", hint: "Click a start point, pick a room, then test and simulate the route." },
];
const ARRIVE_M = 1.0; // sama dengan aplikasi ponsel (NavGraph.Arrived)
const WALK_MPS = 1.0;

function dist(a: XY, b: XY) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

function AreaPage() {
  const id = useSearchParams().get("id") ?? "";
  const { data: me } = usePoll(api.me, 60000);
  const admin = !!me?.is_admin;
  const [plan, setPlan] = useState<PlanMeta | null>(null);
  const [graph, setGraph] = useState<AreaGraph | null>(null);
  const [walkable, setWalkable] = useState<WalkableData | null>(null);
  const [brush, setBrush] = useState<{ mode: StrokeMode; radius: number }>({ mode: "paint", radius: 0.4 });
  const [published, setPublished] = useState<{ at: string; warnings: string[] } | null>(null);
  const [resetting, setResetting] = useState(false);
  const [mode, setMode] = useState<MapMode>("view");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [photo, setPhoto] = useState<{ url: string; heading: string | null } | null>(null);
  const [start, setStart] = useState<XY | null>(null);
  const [roomId, setRoomId] = useState<number | null>(null);
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [marker, setMarker] = useState<XY | null>(null);
  const [newRoom, setNewRoom] = useState<XY | null>(null); // titik ruangan baru, menunggu nama
  const [renaming, setRenaming] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [confirming, setConfirming] = useState(false);
  const anim = useRef<number | null>(null);

  const reload = useCallback(async () => {
    try {
      const [g, w] = await Promise.all([areaApi.graph(id), areaApi.walkable(id)]);
      setGraph(g);
      setWalkable(w);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    if (!id) return;
    areaApi.plan(id).then(setPlan, (e) => setError((e as Error).message));
    reload();
  }, [id, reload]);

  useEffect(() => () => {
    if (anim.current) cancelAnimationFrame(anim.current);
  }, []);

  async function act(fn: () => Promise<unknown>, done?: string) {
    try {
      await fn();
      if (done) setMessage(done);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function showPhoto(p: XY) {
    const r = await fetch(photoUrl(id, p));
    if (!r.ok) {
      setPhoto(null);
      setError("No scan photo for this map yet. Ask an admin to prepare the scan photos.");
      return;
    }
    if (photo) URL.revokeObjectURL(photo.url);
    setPhoto({ url: URL.createObjectURL(await r.blob()), heading: r.headers.get("x-heading-deg") });
  }

  function onPick(p: XY) {
    setError(null);
    if (mode === "view") return void showPhoto(p);
    if (mode === "test") {
      setStart(p);
      setRoute(null);
      setMarker(null);
      return;
    }
    if (!admin) return;
    if (mode === "rooms") {
      setNewRoom(p);
      setRenaming(null);
      setName("");
    }
  }

  async function testRoute() {
    if (!start || roomId === null) return;
    try {
      setRoute(await areaApi.route(id, start, roomId));
      setMarker(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function simulate() {
    if (!route || route.status !== "ok") return;
    const pts = route.points;
    const target = pts[pts.length - 1];
    const t0 = performance.now();
    const step = () => {
      let left = ((performance.now() - t0) / 1000) * WALK_MPS;
      let p = pts[0];
      for (let i = 1; i < pts.length; i++) {
        const seg = dist(pts[i - 1], pts[i]);
        if (left <= seg) {
          const k = seg ? left / seg : 0;
          p = [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * k, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * k];
          break;
        }
        left -= seg;
        p = pts[i];
      }
      setMarker(p);
      if (dist(p, target) < ARRIVE_M) {
        setMessage("Arrived: the marker is within 1.0 of the room, so the app would show the arrival banner.");
        return;
      }
      anim.current = requestAnimationFrame(step);
    };
    if (anim.current) cancelAnimationFrame(anim.current);
    anim.current = requestAnimationFrame(step);
  }

  async function publish() {
    setConfirming(false);
    try {
      const r = await areaApi.publish(id);
      setPublished({ at: r.published_at, warnings: r.warnings });
      setMessage(null);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function stroke(mode: StrokeMode, radius: number, points: XY[]) {
    setPublished(null);
    act(() => areaApi.addStroke(id, { mode, radius, points }));
  }

  function undoStroke() {
    const last = walkable?.strokes[walkable.strokes.length - 1];
    if (last) act(() => areaApi.deleteStroke(id, last.id), "Last stroke undone");
  }

  function resetStrokes() {
    setResetting(false);
    act(() => areaApi.resetStrokes(id), "Walkable area reset to the scan path");
  }

  if (!id) return <p className="error">No area selected.</p>;
  const room = graph?.rooms.find((r) => r.id === roomId);

  return (
    <>
      <PageHead crumbs={[{ label: "Maps", href: "/maps/" }, { label: id }]} title={`Rooms and routes · ${id}`}>
        <p className="text-xs text-muted-foreground mt-1">
          Routes are planned on the walkable area, which starts from the scan path. Scale not calibrated: distances follow the current alignment.
          {graph?.published_at && <> Last published {formatDate(graph.published_at)}.</>}
        </p>
      </PageHead>
      {error && <p className="error">{error}</p>}
      {message && <p className="text-sm">{message}</p>}
      {published && (
        <Panel className="border border-border">
          <span className="text-sm font-semibold">Published at {formatDate(published.at)}.</span>
          <span className="text-sm">
            The app loads it on the next Localize (builds older than 21 Oct evening need an app restart).
          </span>
          {published.warnings.map((w) => (
            <span key={w} className="text-xs text-[var(--bad-fg)]">{w}</span>
          ))}
          <div>
            <Button size="sm" variant="outline" onClick={() => setPublished(null)}>Dismiss</Button>
          </div>
        </Panel>
      )}
      <div className="flex flex-wrap gap-2">
        {MODES.map((m) => (
          <Button key={m.id} variant={mode === m.id ? "default" : "outline"} onClick={() => setMode(m.id)}>
            {m.label}
          </Button>
        ))}
        {admin && (
          <Button className="ml-auto" onClick={() => setConfirming(true)} disabled={!graph || !walkable}>
            Publish to app
          </Button>
        )}
      </div>
      {confirming && graph && (
        <Panel className="border border-border">
          <span className="text-sm font-semibold">
            Publish {graph.rooms.length} room(s) and the walkable area to the app?
          </span>
          {walkable?.warnings.map((w) => (
            <span key={w} className="text-xs text-[var(--bad-fg)]">{w}</span>
          ))}
          <div className="flex gap-2">
            <Button onClick={publish}>Confirm publish</Button>
            <Button variant="outline" onClick={() => setConfirming(false)}>Cancel</Button>
          </div>
        </Panel>
      )}
      <p className="text-xs text-muted-foreground">
        {MODES.find((m) => m.id === mode)?.hint}
        {!admin && (mode === "rooms" || mode === "walkable") && " Only admins can make changes."}
      </p>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Panel>
          {plan && graph ? (
            <AreaMap
              plan={plan}
              imageUrl={planImageUrl(id)}
              rooms={graph.rooms}
              walkable={walkable}
              mode={mode}
              editable={admin}
              brush={brush}
              onPick={onPick}
              onMoveRoom={(rid, p) => act(() => areaApi.editRoom(id, rid, { x: p[0], y: p[1] }), "Room moved")}
              onStroke={stroke}
              route={mode === "test" && route?.status === "ok" ? route.points : undefined}
              start={mode === "test" ? start : null}
              pending={mode === "rooms" ? newRoom : null}
              marker={mode === "test" ? marker : null}
              arrivalTarget={mode === "test" && room ? [room.x, room.y] : null}
            />
          ) : (
            <p className="muted">Loading the floor plan...</p>
          )}
        </Panel>
        <div className="flex flex-col gap-4">
          {mode === "view" && (
            <Panel>
              <span className="stat-label">Scan photo</span>
              {photo ? (
                <>
                  <img src={photo.url} alt="Scan photo nearest to the clicked point" className="w-full rounded-lg" />
                  {photo.heading && <span className="muted text-xs">Camera facing {photo.heading}° in the map frame</span>}
                </>
              ) : (
                <span className="muted text-sm">Click the map to see the nearest photo.</span>
              )}
            </Panel>
          )}
          {mode === "walkable" && (
            <Panel>
              <span className="stat-label">Walkable area</span>
              {admin ? (
                <>
                  <div className="flex gap-2">
                    <Button size="sm" variant={brush.mode === "paint" ? "default" : "outline"} onClick={() => setBrush({ ...brush, mode: "paint" })}>
                      Paint
                    </Button>
                    <Button size="sm" variant={brush.mode === "erase" ? "default" : "outline"} onClick={() => setBrush({ ...brush, mode: "erase" })}>
                      Erase
                    </Button>
                  </div>
                  <label className="flex items-center gap-2 text-sm">
                    Brush radius {brush.radius.toFixed(2)}
                    <input
                      type="range"
                      min={0.3}
                      max={1.5}
                      step={0.05}
                      value={brush.radius}
                      aria-label="Brush radius"
                      onChange={(e) => setBrush({ ...brush, radius: Number(e.target.value) })}
                    />
                  </label>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={undoStroke} disabled={!walkable?.strokes.length}>Undo</Button>
                    <Button size="sm" variant="outline" onClick={() => setResetting(true)} disabled={!walkable?.strokes.length}>
                      Reset to scan path
                    </Button>
                  </div>
                  {resetting && (
                    <div className="flex flex-col gap-2 text-sm">
                      <span>Remove all {walkable?.strokes.length} stroke(s) and go back to the scan path?</span>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={resetStrokes}>Confirm reset</Button>
                        <Button size="sm" variant="outline" onClick={() => setResetting(false)}>Cancel</Button>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <span className="muted text-sm">Only admins can change the walkable area.</span>
              )}
              <span className="muted text-xs">
                {walkable?.strokes.length ?? 0} stroke(s), {walkable?.walkable_cells ?? 0} walkable cells. Green is what routes can use.
              </span>
              {walkable?.warnings.map((w) => (
                <span key={w} className="text-xs text-[var(--bad-fg)]">{w}</span>
              ))}
            </Panel>
          )}
          {mode === "test" && (
            <Panel>
              <span className="stat-label">Test route</span>
              <span className="text-sm">{start ? `Start ${start[0]}, ${start[1]}` : "Click the map to set a start point."}</span>
              <select className="mock-input rounded-md border border-border p-2 text-sm" value={roomId ?? ""} onChange={(e) => setRoomId(e.target.value ? Number(e.target.value) : null)}>
                <option value="">Pick a room</option>
                {graph?.rooms.map((r) => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
              <div className="flex gap-2">
                <Button onClick={testRoute} disabled={!start || roomId === null}>Test route</Button>
                <Button variant="outline" onClick={simulate} disabled={route?.status !== "ok"}>Simulate</Button>
              </div>
              {route?.status === "unreachable" && <span className="error">This room cannot be reached from the start point.</span>}
              {route?.status === "ok" && (
                <span className="text-sm">
                  Route length {route.length_m.toFixed(1)} (scale not calibrated), {Math.max(route.points.length - 2, 0)} turn(s).
                </span>
              )}
            </Panel>
          )}
          {mode === "rooms" && newRoom && admin && (
            <Panel>
              <span className="stat-label">New room</span>
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const n = name.trim();
                  if (!n) return;
                  act(() => areaApi.addRoom(id, { name: n, x: newRoom[0], y: newRoom[1] }), `Room ${n} added`);
                  setNewRoom(null);
                }}
              >
                <input
                  autoFocus
                  aria-label="Room name"
                  placeholder="Room name"
                  className="min-w-0 flex-1 rounded-md border border-border px-2 py-1 text-sm"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <Button type="submit" size="sm">Add</Button>
                <Button type="button" size="sm" variant="outline" onClick={() => setNewRoom(null)}>Cancel</Button>
              </form>
            </Panel>
          )}
          <Panel>
            <span className="stat-label">Rooms ({graph?.rooms.length ?? 0})</span>
            {graph?.rooms.length === 0 && <span className="muted text-sm">No rooms yet.</span>}
            {graph?.rooms.map((r) => (
              <div key={r.id} className="flex items-center justify-between gap-2 text-sm">
                {renaming === r.id ? (
                  <form
                    className="flex flex-1 gap-1"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const n = name.trim();
                      if (n) act(() => areaApi.editRoom(id, r.id, { name: n }), "Room renamed");
                      setRenaming(null);
                    }}
                  >
                    <input
                      autoFocus
                      aria-label="New room name"
                      className="min-w-0 flex-1 rounded-md border border-border px-2 py-1 text-sm"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                    <Button type="submit" size="sm">Save</Button>
                  </form>
                ) : (
                  <span>{r.name}</span>
                )}
                {admin && renaming !== r.id && (
                  <span className="flex gap-1">
                    <Button size="sm" variant="outline" onClick={() => { setRenaming(r.id); setName(r.name); }}>Rename</Button>
                    <Button size="sm" variant="outline" onClick={() => act(() => areaApi.deleteRoom(id, r.id), "Room deleted")}>Delete</Button>
                  </span>
                )}
              </div>
            ))}
          </Panel>
        </div>
      </div>
    </>
  );
}

export default function AreaRoute() {
  // useSearchParams wajib di dalam Suspense pada static export (tanpa ini next build gagal).
  return (
    <Suspense fallback={<p className="muted">Loading...</p>}>
      <AreaPage />
    </Suspense>
  );
}
