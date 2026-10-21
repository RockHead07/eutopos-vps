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
  type XY,
} from "@/lib/api";
import { PageHead } from "@/lib/PageHead";
import { usePoll } from "@/lib/usePoll";

const MODES: { id: MapMode; label: string; hint: string }[] = [
  { id: "view", label: "View", hint: "Click anywhere on the scan path to see the real photo taken there." },
  { id: "rooms", label: "Rooms", hint: "Click on the map to add a room. Drag a room to move it." },
  { id: "routes", label: "Routes", hint: "Click a route segment to remove it. Click two points to add one. Drag a junction to move it." },
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
  const [mode, setMode] = useState<MapMode>("view");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [photo, setPhoto] = useState<{ url: string; heading: string | null } | null>(null);
  const [pending, setPending] = useState<XY | null>(null);
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
      setGraph(await areaApi.graph(id));
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
    if (mode === "routes") {
      if (!pending) return setPending(p);
      act(() => areaApi.addEdit(id, { kind: "add_edge", a: pending, b: p }), "Route segment added");
      setPending(null);
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

  function publish() {
    setConfirming(false);
    act(() => areaApi.publish(id), "Published. The app uses the new routes on its next start or Localize.");
  }

  if (!id) return <p className="error">No area selected.</p>;
  const room = graph?.rooms.find((r) => r.id === roomId);

  return (
    <>
      <PageHead crumbs={[{ label: "Maps", href: "/maps/" }, { label: id }]} title={`Rooms and routes · ${id}`}>
        <p className="text-xs text-muted-foreground mt-1">
          Routes come from the scan path. Scale not calibrated: distances follow the current alignment.
          {graph?.published_at && <> Last published {formatDate(graph.published_at)}.</>}
        </p>
      </PageHead>
      {error && <p className="error">{error}</p>}
      {message && <p className="text-sm">{message}</p>}
      <div className="flex flex-wrap gap-2">
        {MODES.map((m) => (
          <Button key={m.id} variant={mode === m.id ? "default" : "outline"} onClick={() => { setMode(m.id); setPending(null); }}>
            {m.label}
          </Button>
        ))}
        {admin && (
          <Button className="ml-auto" onClick={() => setConfirming(true)} disabled={!graph}>
            Publish to app
          </Button>
        )}
      </div>
      {confirming && graph && (
        <Panel className="border border-border">
          <span className="text-sm font-semibold">
            Publish {graph.rooms.length} room(s) and the route graph to the app?
          </span>
          {graph.warnings.map((w) => (
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
        {!admin && (mode === "rooms" || mode === "routes") && " Only admins can make changes."}
        {pending && " First point set, click the second point."}
      </p>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Panel>
          {plan && graph ? (
            <AreaMap
              plan={plan}
              imageUrl={planImageUrl(id)}
              graph={graph}
              mode={mode}
              editable={admin}
              onPick={onPick}
              onMoveRoom={(rid, p) => act(() => areaApi.editRoom(id, rid, { x: p[0], y: p[1] }), "Room moved")}
              onMoveNode={(from, to) => act(() => areaApi.addEdit(id, { kind: "move_node", a: from, b: to }), "Junction moved")}
              onEdgeClick={(a, b) => act(() => areaApi.addEdit(id, { kind: "remove_edge", a, b }), "Route segment removed")}
              route={mode === "test" && route?.status === "ok" ? route.points : undefined}
              start={mode === "test" ? start : null}
              pending={mode === "rooms" ? newRoom : pending}
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
                <span className="text-sm">Route length {route.length_m.toFixed(1)} (scale not calibrated), {route.nodes.length} stops.</span>
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
          <Panel>
            <span className="stat-label">Route edits ({graph?.edits.length ?? 0})</span>
            {graph?.edits.map((e) => (
              <div key={e.id} className="flex items-center justify-between gap-2 text-sm">
                <span className={graph.unmatched_edits.includes(e.id) ? "text-[var(--bad-fg)]" : undefined}>
                  {e.kind.replace("_", " ")}
                  {graph.unmatched_edits.includes(e.id) && " (no longer matches)"}
                </span>
                {admin && <Button size="sm" variant="outline" onClick={() => act(() => areaApi.deleteEdit(id, e.id), "Edit removed")}>Undo</Button>}
              </div>
            ))}
            {graph?.warnings.map((w) => (
              <span key={w} className="text-xs text-[var(--bad-fg)]">{w}</span>
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
