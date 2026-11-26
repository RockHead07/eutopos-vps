"""Uji paritas 4-DoF Python vs C# (eutopos-mobile) lewat tests/fixtures/align4dof_cases.json."""

import json
from pathlib import Path

import numpy as np

from server.align4dof import solve_from_poses, yaw_diff_deg

FIXTURE = Path(__file__).parent / "fixtures" / "align4dof_cases.json"


def test_align4dof_fixture_is_self_describing_and_has_at_least_8_cases():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(data.get("about"), str) and len(data["about"]) >= 40
    for keyword in ("metre", "Unity", "xyzw", "Z-up", "Y-up"):
        assert keyword.lower() in data["about"].lower(), keyword
    cases = data["cases"]
    assert isinstance(cases, list) and len(cases) >= 8


def test_align4dof_fixture_cases_match_python_port():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for case in data["cases"]:
        solved = solve_from_poses(
            case["ar_position"],
            case["ar_rotation_xyzw"],
            case["building_position_g"],
            case["building_rotation_xyzw"],
        )
        expected = case["expected"]
        if expected is None:
            assert solved is None, case["name"]
        else:
            assert solved is not None, case["name"]
            assert yaw_diff_deg(solved.yaw_deg, expected["yaw_deg"]) < 1e-4, case["name"]
            assert np.allclose(solved.translation, expected["translation"], atol=1e-5), case["name"]
            # Verifikasi balik: BToU(GToB(building_position_g)) == ar_position
            from server.align4dof import g_to_b

            assert np.allclose(
                solved.b_to_u(g_to_b(case["building_position_g"])),
                case["ar_position"],
                atol=1e-5,
            ), case["name"]
