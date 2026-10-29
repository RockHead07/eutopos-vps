"""server/sim3.fit: satu-satunya penaksir Sim3 titik-ke-titik (roadmap M1-1)."""

import sys
from pathlib import Path

import numpy as np
import pycolmap
import pytest

from server import sim3


def known_sim():
    q = np.array([0.1, 0.7, 0.2, 0.68])
    return pycolmap.Sim3d(4.0, pycolmap.Rotation3d(q / np.linalg.norm(q)), np.array([3.0, -1, 2]))


def points(n=12):
    return np.array([[i * 1.5, 0.3 if i % 2 else 1.7, 1.3] for i in range(n)], float)


def test_fit_recovers_a_known_sim3():
    truth = known_sim()
    src = points()
    got = sim3.fit(src, truth * src, 0.1)
    assert abs(got.scale - 4.0) < 1e-6
    np.testing.assert_allclose(got.translation, truth.translation, atol=1e-6)
    np.testing.assert_allclose(got.rotation.matrix(), truth.rotation.matrix(), atol=1e-6)


def test_fit_ignores_a_gross_outlier():
    truth = known_sim()
    src = points()
    tgt = truth * src
    tgt[5] += [50.0, -40.0, 20.0]
    got = sim3.fit(src, tgt, 0.1)
    assert abs(got.scale - 4.0) < 1e-3
    np.testing.assert_allclose(got.translation, truth.translation, atol=1e-3)


def test_fit_returns_none_when_it_cannot_solve():
    assert sim3.fit(points(2), points(2), 1.0) is None


def test_the_spike_tool_uses_this_fit():
    # satu sumber kebenaran: spike/eval_meter.py tidak boleh punya salinan sendiri
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spike"))
    import eval_meter

    assert eval_meter.fit is sim3.fit


def test_fit_signature_is_stable():
    with pytest.raises(TypeError):
        sim3.fit(points())  # ransac_m wajib: tanpa ambang bawaan yang tersembunyi
