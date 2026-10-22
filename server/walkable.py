"""Area walkable: grid dari jalur scan dan goresan kuas, plus perencana rute.

Spesifikasi `docs/specs/2026-10-21-area-walkable-panah-poi-design.md`. Modul murni (tanpa
database dan HTTP). Kerangka G 2D; skala belum dikalibrasi, jarak dalam satuan G. Sel `[row, col]`,
indeks `row * width + col`, baris naik searah y. Port C# (`WalkableGrid`) memakai aturan yang
sama dan diuji dengan `tests/fixtures/walkable_cases.json`.
"""

import base64
import heapq
import math
from collections import deque
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

CELL_M = 0.10
COARSE_CELL_M = 0.20
MARGIN_M = 3.0
SEED_RADIUS_M = 0.5
AGENT_RADIUS_M = 0.2
SOFT_CELLS = 400_000
MAX_CELLS = 1_000_000
ROOM_FAR_M = 1.5


@dataclass(frozen=True, eq=False)
class Grid:
    origin: tuple[float, float]
    cell_m: float
    width: int
    height: int
    cells: np.ndarray  # bool, bentuk (height, width)


def _dims(extent_x: float, extent_y: float, cell_m: float) -> tuple[int, int]:
    # round() menahan galat float: 4 / 0.1 harus 40, bukan 41
    w = math.ceil(round(extent_x / cell_m, 6))
    h = math.ceil(round(extent_y / cell_m, 6))
    return max(w, 1), max(h, 1)


def make_grid(
    bounds: tuple[float, float, float, float], cell_m: float = CELL_M, margin: float = MARGIN_M
) -> Grid:
    """Grid kosong yang menutupi bounds = (minx, miny, maxx, maxy) ditambah margin."""
    minx, miny, maxx, maxy = bounds
    ex, ey = maxx - minx + 2 * margin, maxy - miny + 2 * margin
    w, h = _dims(ex, ey, cell_m)
    if w * h > SOFT_CELLS:
        cell_m = COARSE_CELL_M
        w, h = _dims(ex, ey, cell_m)
    if w * h > MAX_CELLS:
        raise ValueError(f"walkable grid too large: {w * h} cells")
    return Grid((minx - margin, miny - margin), cell_m, w, h, np.zeros((h, w), dtype=bool))


def grid_from_rows(rows: list[str], cell_m: float = 1.0, origin=(0.0, 0.0)) -> Grid:
    """Grid dari teks: '#' tembok, '.' walkable. Baris pertama = y tertinggi (seperti peta)."""
    cells = np.array([[c == "." for c in row] for row in reversed(rows)], dtype=bool)
    return Grid((float(origin[0]), float(origin[1])), cell_m, cells.shape[1], cells.shape[0], cells)


def _centers(g: Grid) -> tuple[np.ndarray, np.ndarray]:
    xs = g.origin[0] + (np.arange(g.width) + 0.5) * g.cell_m
    ys = g.origin[1] + (np.arange(g.height) + 0.5) * g.cell_m
    return xs, ys


def _stamp(g: Grid, cells: np.ndarray, pts, radius: float, value: bool) -> None:
    """Set sel yang pusatnya dalam `radius` dari polyline `pts` (satu titik = lingkaran)."""
    xs, ys = _centers(g)
    segs = list(pairwise(pts)) or [(pts[0], pts[0])]
    for (ax, ay), (bx, by) in segs:
        c0 = max(math.floor((min(ax, bx) - radius - g.origin[0]) / g.cell_m), 0)
        c1 = min(math.floor((max(ax, bx) + radius - g.origin[0]) / g.cell_m), g.width - 1)
        r0 = max(math.floor((min(ay, by) - radius - g.origin[1]) / g.cell_m), 0)
        r1 = min(math.floor((max(ay, by) + radius - g.origin[1]) / g.cell_m), g.height - 1)
        if c0 > c1 or r0 > r1:
            continue
        gx, gy = np.meshgrid(xs[c0 : c1 + 1], ys[r0 : r1 + 1])
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        t = np.clip(((gx - ax) * dx + (gy - ay) * dy) / l2, 0.0, 1.0) if l2 > 0 else 0.0
        d2 = (gx - (ax + t * dx)) ** 2 + (gy - (ay + t * dy)) ** 2
        block = cells[r0 : r1 + 1, c0 : c1 + 1]
        block[d2 <= radius * radius + 1e-12] = value


def seed(g: Grid, sequences, radius: float = SEED_RADIUS_M) -> Grid:
    cells = g.cells.copy()
    for seq in sequences:
        if seq:
            _stamp(g, cells, [tuple(p) for p in seq], radius, True)
    return Grid(g.origin, g.cell_m, g.width, g.height, cells)


def apply_strokes(g: Grid, strokes: list[dict]) -> Grid:
    cells = g.cells.copy()
    for s in strokes:
        pts = [tuple(p) for p in s["points"]]
        _stamp(g, cells, pts, float(s["radius"]), s["mode"] == "paint")
    return Grid(g.origin, g.cell_m, g.width, g.height, cells)


def _shift(a: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """s[r, c] = a[r + dy, c + dx]; di luar grid False."""
    h, w = a.shape
    s = np.zeros_like(a)
    s[max(0, -dy) : h - max(0, dy), max(0, -dx) : w - max(0, dx)] = a[
        max(0, dy) : h - max(0, -dy), max(0, dx) : w - max(0, -dx)
    ]
    return s


def erode(g: Grid, radius: float = AGENT_RADIUS_M) -> Grid:
    """Sel bertahan hanya bila semua sel berpusat dalam `radius` darinya walkable (radius agen)."""
    k = math.ceil(radius / g.cell_m) + 1
    out = g.cells.copy()
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            if math.hypot(dx, dy) * g.cell_m <= radius + 1e-9:
                out &= _shift(g.cells, dx, dy)
    return Grid(g.origin, g.cell_m, g.width, g.height, out)


def planning_grid(bounds, sequences, strokes) -> Grid:
    return erode(apply_strokes(seed(make_grid(bounds), sequences), strokes))


_NEIGHBORS = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))  # (dx, dy)


def _passable(cells: list, col: int, row: int, dx: int, dy: int) -> bool:
    """Sel tetangga walkable, dan diagonal tidak memotong sudut tembok. `cells` = list of list."""
    h, w = len(cells), len(cells[0])
    nc, nr = col + dx, row + dy
    if not (0 <= nc < w and 0 <= nr < h) or not cells[nr][nc]:
        return False
    return dx == 0 or dy == 0 or bool(cells[row][nc] and cells[nr][col])


def components(g: Grid) -> np.ndarray:
    """Label komponen terhubung (delapan arah, tanpa memotong sudut); 0 = bukan walkable."""
    labels = np.zeros((g.height, g.width), dtype=np.int32)
    cells = g.cells.tolist()
    nxt = 0
    for idx in np.flatnonzero(g.cells.ravel()):
        row, col = divmod(int(idx), g.width)
        if labels[row, col]:
            continue
        nxt += 1
        labels[row, col] = nxt
        queue = deque([(col, row)])
        while queue:
            c, r = queue.popleft()
            for dx, dy in _NEIGHBORS:
                if _passable(cells, c, r, dx, dy) and not labels[r + dy, c + dx]:
                    labels[r + dy, c + dx] = nxt
                    queue.append((c + dx, r + dy))
    return labels


def anchor(g: Grid, point: tuple[float, float]) -> tuple[int, float] | None:
    """(indeks sel, jarak ke pusatnya): sel sendiri bila walkable, selain itu sel walkable terdekat
    (seri: indeks terkecil). None bila tidak ada sel walkable."""
    px, py = point
    col = math.floor((px - g.origin[0]) / g.cell_m)
    row = math.floor((py - g.origin[1]) / g.cell_m)
    if 0 <= col < g.width and 0 <= row < g.height and g.cells[row, col]:
        cx = g.origin[0] + (col + 0.5) * g.cell_m
        cy = g.origin[1] + (row + 0.5) * g.cell_m
        return row * g.width + col, math.hypot(px - cx, py - cy)
    walk = np.flatnonzero(g.cells.ravel())
    if not walk.size:
        return None
    cx = g.origin[0] + (walk % g.width + 0.5) * g.cell_m
    cy = g.origin[1] + (walk // g.width + 0.5) * g.cell_m
    d2 = (cx - px) ** 2 + (cy - py) ** 2
    k = int(np.argmin(d2))  # argmin mengambil kemunculan pertama = indeks terkecil
    return int(walk[k]), float(math.sqrt(d2[k]))


def encode(g: Grid) -> dict:
    bits = np.packbits(g.cells.ravel().astype(np.uint8), bitorder="little")
    return {
        "frame": "building",  # aplikasi (WalkableGrid.Parse) mewajibkan frame dan units
        "units": "m",
        "cell_m": g.cell_m,
        "origin": [g.origin[0], g.origin[1]],
        "width": g.width,
        "height": g.height,
        "bits": base64.b64encode(bits.tobytes()).decode("ascii"),
    }


def decode(d: dict) -> Grid:
    w, h = int(d["width"]), int(d["height"])
    raw = np.frombuffer(base64.b64decode(d["bits"]), dtype=np.uint8)
    if raw.size != math.ceil(w * h / 8):
        raise ValueError("walkable bits do not match width * height")
    cells = np.unpackbits(raw, bitorder="little")[: w * h].reshape(h, w).astype(bool)
    return Grid((float(d["origin"][0]), float(d["origin"][1])), float(d["cell_m"]), w, h, cells)


def room_warnings(g: Grid, rooms: list[dict]) -> list[str]:
    """Peringatan Publish: ruangan jauh dari area atau di luar komponen terbesar."""
    labels = components(g)
    counts = np.bincount(labels.ravel())[1:]
    main = int(np.argmax(counts)) + 1 if counts.size else 0
    out = []
    for r in rooms:
        a = anchor(g, (r["x"], r["y"]))
        if a is None:
            continue
        idx, dist = a
        if dist > ROOM_FAR_M:
            out.append(
                f"Room {r['name']} is {dist:.1f} from the walkable area (more than {ROOM_FAR_M})"
            )
        if labels.ravel()[idx] != main:
            out.append(f"Room {r['name']} is not connected to the main walkable area")
    return out


def _heuristic(idx: int, goal: int, w: int) -> int:
    dx, dy = abs(idx % w - goal % w), abs(idx // w - goal // w)
    return 10 * max(dx, dy) + 4 * min(dx, dy)


def _astar(cells: list, w: int, start: int, goal: int) -> list[int] | None:
    """A* delapan arah, biaya bilangan bulat 10 dan 14, prioritas (f, h, indeks). Parent hanya
    diganti bila biaya LEBIH KECIL; goal diperiksa saat di-pop. C# harus meniru ini persis."""
    best = {start: 0}
    parent: dict[int, int] = {}
    closed: set[int] = set()
    h0 = _heuristic(start, goal, w)
    heap = [(h0, h0, start)]
    while heap:
        _, _, idx = heapq.heappop(heap)
        if idx in closed:
            continue
        if idx == goal:
            path = [idx]
            while path[-1] != start:
                path.append(parent[path[-1]])
            return path[::-1]
        closed.add(idx)
        row, col = divmod(idx, w)
        for dx, dy in _NEIGHBORS:
            if not _passable(cells, col, row, dx, dy):
                continue
            n = (row + dy) * w + col + dx
            if n in closed:
                continue
            cost = best[idx] + (10 if dx == 0 or dy == 0 else 14)
            if cost < best.get(n, math.inf):
                best[n], parent[n] = cost, idx
                hn = _heuristic(n, goal, w)
                heapq.heappush(heap, (cost + hn, hn, n))
    return None


def _los(cells: list, w: int, a: int, b: int) -> bool:
    """Garis pandang Bresenham bilangan bulat (semua oktan): semua sel yang dilalui walkable."""
    x0, y0, x1, y1 = a % w, a // w, b % w, b // w
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        if not cells[y0][x0]:
            return False
        if (x0, y0) == (x1, y1):
            return True
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _own_walkable(g: Grid, p: tuple[float, float]) -> bool:
    col = math.floor((p[0] - g.origin[0]) / g.cell_m)
    row = math.floor((p[1] - g.origin[1]) / g.cell_m)
    return 0 <= col < g.width and 0 <= row < g.height and bool(g.cells[row, col])


def plan_route(g: Grid, start: tuple[float, float], goal: tuple[float, float]) -> dict | None:
    """Rute start ke goal di atas grid: A* lalu diluruskan. None bila tidak ada sel walkable atau
    goal tidak terjangkau. `points` = [start persis, pusat sel belokan, goal persis]."""
    a, b = anchor(g, start), anchor(g, goal)
    if a is None or b is None:
        return None
    cells, w = g.cells.tolist(), g.width
    path = _astar(cells, w, a[0], b[0])
    if path is None:
        return None
    kept = [path[0]]
    i = 0
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1 and not _los(cells, w, path[i], path[j]):
            j -= 1
        kept.append(path[j])
        i = j
    start_ok, goal_ok = _own_walkable(g, start), _own_walkable(g, goal)
    if len(kept) == 1:
        mid = [] if start_ok and goal_ok else kept
    else:
        mid = kept[:]
        if goal_ok:
            mid.pop()
        if start_ok:
            mid.pop(0)
    centers = [
        (g.origin[0] + (n % w + 0.5) * g.cell_m, g.origin[1] + (n // w + 0.5) * g.cell_m)
        for n in mid
    ]
    points = [tuple(start), *centers, tuple(goal)]
    length = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in pairwise(points))
    return {"points": [list(p) for p in points], "length_m": length}
