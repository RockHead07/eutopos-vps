"""Graf rute dari jalur kamera scan, ruangan, editan, dan aturan rute aplikasi.

Spesifikasi `docs/specs/2026-10-21-dashboard-rute-otomatis-design.md` bagian 5a, 5b, 5e. Semua
koordinat di kerangka gedung G (x, y meter menurut align.json, bidang lantai). Jalur kamera adalah
jalur yang benar-benar dilalui saat scan, jadi graf dasar hanya berisi tempat yang bisa dijalani.
"""

import math
from itertools import pairwise

Point = tuple[float, float]
Graph = dict  # {"nodes": {id: (x, y)}, "edges": set[frozenset[str]]}

SMOOTH_WINDOW = 5
RESAMPLE_M = 0.5
MERGE_M = 0.6
SIMPLIFY_M = 0.15


def split_sequences(centers: list[Point], split_m: float = 1.5) -> list[list[Point]]:
    """Potong jalur bila dua frame berurutan melompat > split_m (video lain, frame hilang)."""
    seqs: list[list[Point]] = []
    for p in centers:
        if seqs and math.dist(seqs[-1][-1], p) <= split_m:
            seqs[-1].append(p)
        else:
            seqs.append([p])
    return seqs


def _smooth(seq: list[Point]) -> list[Point]:
    h = SMOOTH_WINDOW // 2
    out = []
    for i in range(len(seq)):
        win = seq[max(0, i - h) : i + h + 1]
        out.append((sum(p[0] for p in win) / len(win), sum(p[1] for p in win) / len(win)))
    return out


def _resample(seq: list[Point]) -> list[Point]:
    if len(seq) < 2:
        return list(seq)
    out, carry = [seq[0]], 0.0
    for a, b in pairwise(seq):
        seg = math.dist(a, b)
        t = RESAMPLE_M - carry
        while seg > 0 and t <= seg:
            out.append((a[0] + (b[0] - a[0]) * t / seg, a[1] + (b[1] - a[1]) * t / seg))
            t += RESAMPLE_M
        carry = seg - (t - RESAMPLE_M) if seg > 0 else carry
    if math.dist(out[-1], seq[-1]) > 1e-9:
        out.append(seq[-1])
    return out


def _seg_dist(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    l2 = dx * dx + dy * dy
    s = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    return math.dist(p, (ax + s * dx, ay + s * dy))


def _simplify(g: Graph) -> None:
    changed = True
    while changed:
        changed = False
        for n in list(g["nodes"]):
            nb = [next(iter(e - {n})) for e in g["edges"] if n in e]
            if len(nb) != 2 or frozenset(nb) in g["edges"]:
                continue
            a, b = (g["nodes"][x] for x in nb)
            if _seg_dist(g["nodes"][n], a, b) < SIMPLIFY_M:
                g["edges"] -= {frozenset((n, nb[0])), frozenset((n, nb[1]))}
                g["edges"].add(frozenset(nb))
                del g["nodes"][n]
                changed = True


def build_base_graph(sequences: list[list[Point]]) -> Graph:
    """Graf tak berarah dari jalur kamera: dihaluskan, disampel ulang, digabung, disederhanakan."""
    # Titik bergabung ke simpul terdekat dalam MERGE_M; titik yang masih dekat simpul sebelumnya
    # tetap di simpul itu. Simpul lintasan baru berjarak sekitar 2 x RESAMPLE_M, dan lintasan yang
    # lewat lagi (bolak-balik, putaran) mengunjungi simpul yang sama, bukan membuat jalur sejajar.
    nodes: dict[str, Point] = {}
    edges: set[frozenset[str]] = set()
    count = 0
    for seq in sequences:
        prev = None
        for p in _resample(_smooth(seq)):
            near = [(math.dist(p, q), n) for n, q in nodes.items() if math.dist(p, q) < MERGE_M]
            if near:
                cur = min(near)[1]
            else:
                cur = f"N{count}"
                count += 1
                nodes[cur] = p
            if prev is not None and prev != cur:
                edges.add(frozenset((prev, cur)))
            prev = cur
    g = {"nodes": nodes, "edges": edges}
    _simplify(g)
    return g


MATCH_M = 0.5
ROOM_FAR_M = 1.5
Edit = dict  # {"id", "kind": "add_edge" | "remove_edge" | "move_node", "a": [x, y], "b": [x, y]}
Room = dict  # {"id", "name", "x", "y"}


def _nearest(g: Graph, p, within: float) -> str | None:
    best = min(g["nodes"], key=lambda n: math.dist(g["nodes"][n], p), default=None)
    if best is None or math.dist(g["nodes"][best], p) > within:
        return None
    return best


def apply_edits(
    base: Graph, edits: list[Edit], match_m: float = MATCH_M
) -> tuple[Graph, list[int]]:
    """Editan disimpan dengan koordinat supaya tetap berlaku pada graf dasar yang dibuat ulang."""
    g = {"nodes": dict(base["nodes"]), "edges": set(base["edges"])}
    unmatched = []
    for e in edits:
        a, b = tuple(e["a"]), tuple(e["b"])
        if e["kind"] == "move_node":
            n = _nearest(g, a, match_m)
            if n is None:
                unmatched.append(e["id"])
            else:
                g["nodes"][n] = b
        elif e["kind"] == "remove_edge":
            na, nb = _nearest(g, a, match_m), _nearest(g, b, match_m)
            edge = frozenset((na, nb))
            if na is None or nb is None or edge not in g["edges"]:
                unmatched.append(e["id"])
            else:
                g["edges"].discard(edge)
        elif e["kind"] == "add_edge":
            ends = []
            for p, tag in ((a, "a"), (b, "b")):
                n = _nearest(g, p, match_m)
                if n is None:
                    n = f"E{e['id']}{tag}"
                    g["nodes"][n] = p
                ends.append(n)
            if ends[0] != ends[1]:
                g["edges"].add(frozenset(ends))
        else:
            raise ValueError(f"unknown edit kind: {e['kind']}")
    return g, unmatched


def _project(nodes: dict, edges: list, p):
    """Titik terdekat pada sisi mana pun, sama dengan NavGraph.TryProject (seri: sisi pertama)."""
    best, out = math.inf, None
    for ea, eb in edges:
        (ax, ay), (bx, by) = nodes[ea], nodes[eb]
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        s = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2)) if l2 > 0 else 0.0
        q = (ax + s * dx, ay + s * dy)
        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
        if d < best:
            best, out = d, (q, ea, eb, s)
    return out


def compose_navgraph(graph: Graph, rooms: list[Room]) -> tuple[dict, list[str]]:
    """navgraph.json dari graf (sesudah editan) dan ruangan; ruangan disambung ke sisi terdekat."""
    nodes = dict(graph["nodes"])
    edges = sorted(tuple(sorted(e)) for e in graph["edges"])
    warnings = []
    for r in rooms:
        rid, p = f"R{r['id']}", (r["x"], r["y"])
        hit = _project(nodes, edges, p)
        if hit is None:
            anchor = _nearest({"nodes": nodes}, p, math.inf)
            q = nodes[anchor] if anchor else None
        else:
            q, ea, eb, s = hit
            if s <= 1e-9:
                anchor = ea
            elif s >= 1 - 1e-9:
                anchor = eb
            else:
                anchor = f"J{r['id']}"
                nodes[anchor] = q
                edges.remove((ea, eb))
                edges += [tuple(sorted((ea, anchor))), tuple(sorted((anchor, eb)))]
        nodes[rid] = p
        if anchor is None:
            warnings.append(f"Room {r['name']} has no route to connect to")
            continue
        edges.append(tuple(sorted((anchor, rid))))
        if (d := math.dist(p, q)) > ROOM_FAR_M:
            warnings.append(
                f"Room {r['name']} is {d:.1f} m from the nearest route (more than {ROOM_FAR_M} m)"
            )
    nav = {
        "frame": "building",
        "units": "m",
        "nodes": [{"id": n, "x": float(x), "y": float(y)} for n, (x, y) in nodes.items()],
        "edges": [list(e) for e in edges],
        "targets": [{"node": f"R{r['id']}", "name": r["name"]} for r in rooms],
    }
    if len(rooms) > 1:
        first = f"R{rooms[0]['id']}"
        for r in rooms[1:]:
            if plan_route(nav, nav_point(nav, first), f"R{r['id']}") is None:
                warnings.append(f"Room {r['name']} cannot be reached from {rooms[0]['name']}")
    return nav, warnings


def nav_point(nav: dict, node: str) -> Point:
    n = next(x for x in nav["nodes"] if x["id"] == node)
    return (n["x"], n["y"])


def plan_route(nav: dict, start: Point, target: str) -> dict | None:
    """Port NavGraph.Plan (eutopos-mobile): proyeksi ke sisi terdekat lalu A* ke simpul target."""
    nodes = {n["id"]: (n["x"], n["y"]) for n in nav["nodes"]}
    if target not in nodes:
        raise ValueError(f"target does not exist: {target}")
    edges = [tuple(e) for e in nav["edges"]]
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    hit = _project(nodes, edges, start)
    if hit is None:
        return None
    proj, ea, eb, _ = hit
    s0 = "\0start"

    def pos(n):
        return proj if n == s0 else nodes[n]

    def neighbors(n):
        return [ea, eb] if n == s0 else adj[n]

    goal = nodes[target]
    cost, parent, open_, closed = {s0: 0.0}, {}, [s0], set()
    reached = False
    while open_:
        cur, best_f = open_[0], math.inf
        for o in open_:
            f = cost[o] + math.dist(pos(o), goal)
            if f < best_f:
                best_f, cur = f, o
        if cur == target:
            reached = True
            break
        open_.remove(cur)
        closed.add(cur)
        for nb in neighbors(cur):
            if nb in closed:
                continue
            c = cost[cur] + math.dist(pos(cur), nodes[nb])
            if nb not in cost or c < cost[nb]:
                cost[nb], parent[nb] = c, cur
                if nb not in open_:
                    open_.append(nb)
    if not reached:
        return None
    ids, c = [], target
    while c != s0:
        ids.append(c)
        c = parent[c]
    ids.reverse()
    points = [list(start), list(proj)] + [list(nodes[i]) for i in ids]
    length = sum(math.dist(p, q) for p, q in pairwise(points))
    return {"points": points, "nodes": ids, "length_m": length}


def arrived(user: Point, target: Point, radius_m: float = 1.0) -> bool:
    return math.dist(user, target) < radius_m
