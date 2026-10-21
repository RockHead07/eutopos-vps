"""Graf rute dari jalur kamera scan (spesifikasi 2026-10-21 dashboard rute otomatis, bagian 5a)."""

import json
import math
from pathlib import Path

import numpy as np

from server import navgraph
from server.routegraph import (
    MERGE_M,
    apply_edits,
    arrived,
    build_base_graph,
    compose_navgraph,
    plan_route,
    split_sequences,
)

CASES = Path(__file__).parent / "fixtures" / "route_cases.json"


def noisy(points, seed=0, sigma=0.05):
    rng = np.random.default_rng(seed)
    return [(x + rng.normal(0, sigma), y + rng.normal(0, sigma)) for x, y in points]


def straight(x0, y0, x1, y1, step=0.1):
    n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
    return [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n + 1)]


def l_path():
    return noisy(straight(0, 0, 6, 0) + straight(6, 0, 6, 4)[1:])


def edges(g):
    return [tuple(sorted(e)) for e in g["edges"]]


def degree(g, n):
    return sum(1 for e in g["edges"] if n in e)


def is_connected(g):
    ids = list(g["nodes"])
    seen, todo = {ids[0]}, [ids[0]]
    while todo:
        cur = todo.pop()
        for e in g["edges"]:
            if cur in e:
                (other,) = set(e) - {cur}
                if other not in seen:
                    seen.add(other)
                    todo.append(other)
    return len(seen) == len(ids)


def midpoint(g, a, b):
    (ax, ay), (bx, by) = g["nodes"][a], g["nodes"][b]
    return (ax + bx) / 2, (ay + by) / 2


def min_dist(p, path):
    return min(math.hypot(p[0] - x, p[1] - y) for x, y in path)


def test_noisy_l_path_becomes_a_smooth_l():
    g = build_base_graph([l_path()])
    assert 3 <= len(g["nodes"]) <= 8
    assert is_connected(g)


def test_walking_the_same_corridor_twice_gives_one_corridor():
    there = noisy(straight(0, 0, 8, 0), seed=1)
    back = [(x, y + 0.2) for x, y in reversed(noisy(straight(0, 0, 8, 0), seed=2))]
    g = build_base_graph([there + back])
    assert max(abs(y) for _, y in g["nodes"].values()) < 0.4
    assert all(degree(g, n) <= 2 for n in g["nodes"])


def test_a_loop_closes_into_a_junction():
    square = straight(0, 0, 4, 0) + straight(4, 0, 4, 4)[1:] + straight(4, 4, 0, 4)[1:]
    square += straight(0, 4, 0, 0)[1:]
    g = build_base_graph([noisy(square, seed=3)])
    assert is_connected(g)
    assert all(degree(g, n) == 2 for n in g["nodes"])
    assert len(g["edges"]) == len(g["nodes"])  # siklus tertutup


def test_no_edge_crosses_area_the_camera_never_walked():
    path = l_path()
    g = build_base_graph([path])
    for a, b in edges(g):
        assert min_dist(midpoint(g, a, b), path) < MERGE_M


def test_sequences_are_split_at_jumps():
    assert len(split_sequences([(0, 0), (0.1, 0), (5, 0), (5.1, 0)])) == 2
    assert len(split_sequences([(0, 0), (0.1, 0), (0.2, 0)])) == 1


def test_empty_input_gives_an_empty_graph():
    g = build_base_graph([])
    assert g["nodes"] == {} and g["edges"] == set()


def shift(path, dx):
    return [(x + dx, y) for x, y in path]


def near(g, x, y):
    return min(g["nodes"], key=lambda n: math.dist(g["nodes"][n], (x, y)))


def reachable(g, a, b):
    seen, todo = {a}, [a]
    while todo:
        cur = todo.pop()
        for e in g["edges"]:
            if cur in e:
                (other,) = set(e) - {cur}
                if other not in seen:
                    seen.add(other)
                    todo.append(other)
    return b in seen


def test_remove_edit_matches_by_coordinates_after_regeneration():
    base = build_base_graph([l_path()])
    a, b = base["nodes"][near(base, 6, 0)], base["nodes"][near(base, 6, 4)]
    assert frozenset((near(base, 6, 0), near(base, 6, 4))) in base["edges"]
    shifted = build_base_graph([shift(l_path(), 0.1)])
    edit = {"id": 1, "kind": "remove_edge", "a": list(a), "b": list(b)}
    g, unmatched = apply_edits(shifted, [edit])
    assert unmatched == []
    assert not reachable(g, near(g, 0, 0), near(g, 6, 4))


def test_edit_that_no_longer_matches_is_reported():
    edit = {"id": 1, "kind": "remove_edge", "a": [20, 20], "b": [21, 20]}
    _, unmatched = apply_edits(build_base_graph([l_path()]), [edit])
    assert unmatched == [1]


def test_add_and_move_edits():
    base = build_base_graph([l_path()])
    g, unmatched = apply_edits(
        base,
        [
            {"id": 1, "kind": "add_edge", "a": [0, 0], "b": [0, 3]},
            {"id": 2, "kind": "move_node", "a": [6, 4], "b": [6.2, 4.1]},
        ],
    )
    assert unmatched == []
    assert reachable(g, near(g, 0, 3), near(g, 6, 4))
    assert math.dist(g["nodes"][near(g, 6.2, 4.1)], (6.2, 4.1)) < 1e-9
    assert base["nodes"] != g["nodes"]  # graf dasar tidak diubah di tempat


def test_room_is_attached_to_the_nearest_edge():
    nav, warn = compose_navgraph(
        build_base_graph([l_path()]), [{"id": 7, "name": "Lab", "x": 3, "y": 0.4}]
    )
    assert {"node": "R7", "name": "Lab"} in nav["targets"]
    assert navgraph.validate(nav)
    assert warn == []


def test_far_room_is_connected_but_warned():
    nav, warn = compose_navgraph(
        build_base_graph([l_path()]), [{"id": 7, "name": "Lab", "x": 3, "y": 3}]
    )
    assert any("Lab" in w and "1.5" in w for w in warn)
    assert plan_route(nav, (0, 0), "R7") is not None


def test_route_cases_match_the_shared_file():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    for c in cases["routes"]:
        r = plan_route(c["graph"], tuple(c["from"]), c["target"])
        if c["expect"].get("unreachable"):
            assert r is None, c["name"]
        else:
            assert r["nodes"] == c["expect"]["nodes"], c["name"]
            assert abs(r["length_m"] - c["expect"]["length_m"]) < 1e-3, c["name"]
            assert r["points"][0] == list(c["from"]), c["name"]
    for a in cases["arrivals"]:
        assert arrived(tuple(a["user"]), tuple(a["target"])) == a["expect"]
