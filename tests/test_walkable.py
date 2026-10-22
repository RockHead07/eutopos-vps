"""Grid walkable: seed jalur scan, goresan kuas, erosi, jangkar, bits (spek 2026-10-21)."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from server import walkable
from server.walkable import Grid


def at(g: Grid, x: float, y: float) -> bool:
    ox, oy = g.origin
    return bool(g.cells[math.floor((y - oy) / g.cell_m), math.floor((x - ox) / g.cell_m)])


def seeded() -> Grid:
    return walkable.seed(walkable.make_grid((0, 0, 2, 0), margin=1.0), [[(0, 0), (2, 0)]])


def test_make_grid_extent():
    g = walkable.make_grid((0, 0, 2, 0), margin=1.0)
    assert g.origin == (-1.0, -1.0)
    assert (g.width, g.height) == (40, 20)
    assert g.cells.shape == (20, 40)
    assert not g.cells.any()


def test_make_grid_coarsens_then_refuses():
    assert walkable.make_grid((0, 0, 100, 100), margin=0).cell_m == 0.2
    with pytest.raises(ValueError):
        walkable.make_grid((0, 0, 300, 300), margin=0)


def test_seed_stamps_a_band_with_round_caps():
    g = seeded()
    assert at(g, 1.0, 0.0) and at(g, 1.0, 0.4) and at(g, -0.4, 0.0)
    assert not at(g, 1.0, 0.7) and not at(g, -0.7, 0.0)


def test_strokes_apply_in_order():
    g = seeded()
    painted = walkable.apply_strokes(g, [{"mode": "paint", "radius": 0.3, "points": [[1, 0.8]]}])
    assert at(painted, 1.0, 0.8) and not at(g, 1.0, 0.8)
    erased = walkable.apply_strokes(g, [{"mode": "erase", "radius": 0.3, "points": [[1, 0]]}])
    assert not at(erased, 1.0, 0.0) and at(erased, 1.0, 0.4)
    again = walkable.apply_strokes(
        g,
        [
            {"mode": "erase", "radius": 0.3, "points": [[1, 0]]},
            {"mode": "paint", "radius": 0.3, "points": [[1, 0]]},
        ],
    )
    assert at(again, 1.0, 0.0)


def test_erode_drops_spurs_and_shrinks_edges():
    cells = np.zeros((40, 40), dtype=bool)
    cells[10:30, 10:30] = True  # blok 2,0 x 2,0
    cells[19:21, 30:40] = True  # ekor 2 sel
    out = walkable.erode(Grid((0.0, 0.0), 0.1, 40, 40, cells), radius=0.2).cells
    assert out[20, 20] and out[20, 12]
    assert not out[20, 11] and not out[15, 28] and not out[20, 35]


def test_components_separate_blobs_and_diagonals():
    labels = walkable.components(walkable.grid_from_rows(["..#..", "..#.."]))
    assert labels[0, 0] == 1 and labels[0, 3] == 2 and labels[0, 2] == 0
    diag = walkable.components(walkable.grid_from_rows([".#", "#."]))
    assert diag[0, 1] == 1 and diag[1, 0] == 2


def test_anchor():
    assert walkable.anchor(walkable.grid_from_rows(["#.#"]), (1.5, 0.5)) == (1, 0.0)
    assert walkable.anchor(walkable.grid_from_rows(["#.#"]), (0.5, 0.5)) == (1, 1.0)
    assert walkable.anchor(walkable.grid_from_rows([".#."]), (1.5, 0.5)) == (0, 1.0)
    assert walkable.anchor(walkable.grid_from_rows(["..."]), (-10.5, 0.5)) == (0, 11.0)
    assert walkable.anchor(walkable.grid_from_rows(["###"]), (0.5, 0.5)) is None


def test_encode_bit_order_and_roundtrip():
    assert walkable.encode(walkable.grid_from_rows([".#######"]))["bits"] == "AQ=="
    assert walkable.encode(walkable.grid_from_rows(["#######."]))["bits"] == "gA=="
    assert walkable.encode(walkable.grid_from_rows(["#.", ".#"]))["bits"] == "CQ=="
    rng = np.random.default_rng(0)
    g = Grid((1.5, -2.0), 0.1, 37, 23, rng.random((23, 37)) > 0.5)
    back = walkable.decode(walkable.encode(g))
    assert back.cells.tolist() == g.cells.tolist()
    assert (back.origin, back.cell_m, back.width, back.height) == (g.origin, 0.1, 37, 23)


def test_decode_rejects_wrong_length():
    d = walkable.encode(walkable.grid_from_rows(["...."]))
    with pytest.raises(ValueError):
        walkable.decode({**d, "width": 40})


def test_room_warnings():
    g = walkable.grid_from_rows(["...", "###", "###", "###", "..."])
    rooms = [
        {"name": "X", "x": 1.5, "y": 0.5},
        {"name": "Y", "x": 1.5, "y": 4.5},
        {"name": "Z", "x": 1.5, "y": 2.5},
    ]
    assert walkable.room_warnings(g, rooms) == [
        "Room Y is not connected to the main walkable area",
        "Room Z is 2.0 from the walkable area (more than 1.5)",
    ]


def test_planning_grid_composes():
    seq = [[(0.0, 0.0), (2.0, 0.0)]]
    strokes = [{"mode": "erase", "radius": 0.3, "points": [[1.0, 0.0]]}]
    by_hand = walkable.erode(
        walkable.apply_strokes(walkable.seed(walkable.make_grid((0, 0, 2, 0)), seq), strokes)
    )
    out = walkable.planning_grid((0, 0, 2, 0), seq, strokes)
    assert out.cells.tolist() == by_hand.cells.tolist()


CASES = json.loads((Path(__file__).parent / "fixtures" / "walkable_cases.json").read_text())


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["name"])
def test_shared_route_cases(case):
    g = walkable.grid_from_rows(case["rows"], case["cell_m"], tuple(case["origin"]))
    route = walkable.plan_route(g, tuple(case["from"]), tuple(case["to"]))
    if case["expect"].get("unreachable"):
        assert route is None
        return
    assert route is not None
    assert len(route["points"]) == len(case["expect"]["points"])
    assert np.allclose(route["points"], case["expect"]["points"], atol=1e-3)
    assert route["length_m"] == pytest.approx(case["expect"]["length_m"], abs=1e-3)


@pytest.mark.parametrize("case", CASES["bits"], ids=lambda c: c["b64"])
def test_shared_bit_cases(case):
    g = walkable.grid_from_rows(case["rows"], case["cell_m"], tuple(case["origin"]))
    assert walkable.encode(g)["bits"] == case["b64"]


def test_plan_route_empty_grid_is_none():
    g = walkable.grid_from_rows(["###"])
    assert walkable.plan_route(g, (0.5, 0.5), (2.5, 0.5)) is None
