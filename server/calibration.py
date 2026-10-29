"""Kalibrasi peta ke meter: urai results.csv, agregasi per titik, taksir align.json (roadmap M1-3a).

Murni: tanpa FastAPI dan tanpa database, jadi dipanggil sama oleh API dan tes. Penaksirannya
sama dengan spike/eval_meter.py (satu Sim3 penuh dari semua titik acuan lewat server.sim3.fit,
galat 2D); bedanya, di sini pengamatan per titik dirangkum dulu dengan median.
"""

import csv
import io
import json
import math
import re
import statistics
from dataclasses import dataclass
from typing import Literal

import numpy as np

from server import alignment, sim3

MIN_INLIERS = 50  # sama dengan MIN_INLIERS layanan /localize
MIN_REFERENCE = 4
MIN_SPREAD = 0.05  # sama dengan eval_meter: di bawah ini titik acuan dianggap segaris
ROLES = ("reference", "test")
Xyz = tuple[float, float, float]


class CalibrationError(ValueError):
    """code: too_few_reference, collinear, no_observation, fit_failed, bad_scale, bad_input."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Observation:
    point_id: str
    model_xyz: Xyz
    inliers: int


@dataclass(frozen=True)
class CalPoint:
    point_id: str
    x_m: float
    y_m: float
    role: Literal["reference", "test"]


@dataclass
class FitResult:
    align: dict
    stats: dict
    rows: list[dict]


def _finite(*values) -> bool:
    return all(isinstance(v, int | float) and math.isfinite(v) for v in values)


def _point_id(query: str) -> str:
    name = re.split(r"[\\/]", query)[-1]
    return name.rsplit(".", 1)[0].split("_")[0]  # aturan eval_meter.point_id


def parse_results_csv(text: str) -> list[Observation]:
    """Baca results.csv spike/run.py. Hanya baris ok dengan pusat kamera yang terbaca."""
    reader = csv.DictReader(io.StringIO(text))
    need = {"query", "ok", "inliers", "center_xyz_model"}
    if not need <= set(reader.fieldnames or []):
        raise CalibrationError("bad_input", f"kolom results.csv wajib: {', '.join(sorted(need))}")
    out = []
    for r in reader:
        try:
            if r["ok"] != "True":
                continue
            c = json.loads(r["center_xyz_model"])
            if not (isinstance(c, list) and len(c) == 3 and _finite(*c)):
                continue
            pid = _point_id(r["query"])
            if pid:
                out.append(
                    Observation(pid, (float(c[0]), float(c[1]), float(c[2])), int(r["inliers"]))
                )
        except (ValueError, TypeError, KeyError):
            continue  # baris yang tak terbaca dilewati, bukan menggagalkan seluruh impor
    return out


def aggregate(obs: list[Observation], min_inliers: int = MIN_INLIERS) -> dict[str, Xyz]:
    """Median per sumbu per titik dari pengamatan yang inliernya cukup."""
    by_point: dict[str, list[Xyz]] = {}
    for o in obs:
        if o.inliers >= min_inliers:
            by_point.setdefault(o.point_id, []).append(o.model_xyz)
    return {
        p: tuple(statistics.median(v[i] for v in xs) for i in range(3))  # type: ignore[misc]
        for p, xs in by_point.items()
    }


def _check_points(points: list[CalPoint], observed: dict[str, Xyz]) -> None:
    seen = set()
    for p in points:
        if not p.point_id or p.point_id in seen:
            raise CalibrationError("bad_input", f"ID titik kosong atau ganda: {p.point_id!r}")
        seen.add(p.point_id)
        if p.role not in ROLES:
            raise CalibrationError("bad_input", f"peran {p.role!r} bukan reference atau test")
        if not _finite(p.x_m, p.y_m):
            raise CalibrationError("bad_input", f"koordinat {p.point_id} bukan angka berhingga")
    for pid, xyz in observed.items():
        if len(xyz) != 3 or not _finite(*xyz):
            raise CalibrationError("bad_input", f"pengamatan {pid} bukan angka berhingga")


def fit_alignment(
    points: list[CalPoint],
    observed: dict[str, Xyz],
    height_m: float = 1.3,
    ransac_m: float = 1.0,
) -> FitResult:
    _check_points(points, observed)
    refs = [p for p in points if p.role == "reference"]
    if len(refs) < MIN_REFERENCE:
        raise CalibrationError("too_few_reference", f"butuh >= {MIN_REFERENCE} titik acuan")
    used = [p for p in refs if p.point_id in observed]
    if len(used) < MIN_REFERENCE:
        lost = ", ".join(p.point_id for p in refs if p.point_id not in observed)
        raise CalibrationError("no_observation", f"titik acuan tanpa pengamatan: {lost}")

    xy = np.array([[p.x_m, p.y_m] for p in used], float)
    sv = np.linalg.svd(xy - xy.mean(0), compute_uv=False)
    spread = float(sv[1] / sv[0]) if sv[0] > 0 else 0.0
    if spread < MIN_SPREAD:
        raise CalibrationError("collinear", "titik acuan nyaris segaris; sebar dua dimensi")

    src = np.array([observed[p.point_id] for p in used], float)
    tgt = np.array([[p.x_m, p.y_m, height_m] for p in used], float)
    sim = sim3.fit(src, tgt, ransac_m)
    if sim is None:
        raise CalibrationError("fit_failed", "penaksiran Sim3 gagal; periksa titik dan pengamatan")
    scale = float(sim.scale)
    quat, trans = sim.rotation.quat.tolist(), sim.translation.tolist()
    if not _finite(scale, *quat, *trans) or scale <= 0:
        raise CalibrationError("bad_scale", f"skala hasil taksiran tidak sah: {scale}")

    def at_g(p: CalPoint):
        if p.point_id not in observed:
            return None, None, None
        g = (sim * np.array([observed[p.point_id]], float))[0]
        return float(g[0]), float(g[1]), float(math.hypot(g[0] - p.x_m, g[1] - p.y_m))

    rows = []
    for p in points:
        ox, oy, err = at_g(p)
        rows.append(
            {
                "point_id": p.point_id,
                "role": p.role,
                "x_m": p.x_m,
                "y_m": p.y_m,
                "observed_x": ox,
                "observed_y": oy,
                "error_m": err,
            }
        )
    ref_err = [r["error_m"] for r in rows if r["role"] == "reference" and r["error_m"] is not None]
    test_err = [r["error_m"] for r in rows if r["role"] == "test" and r["error_m"] is not None]
    holdout = sorted(p.point_id for p in points if p.role == "test")

    def r3(v):
        return None if v is None else round(float(v), 3)

    stats = {
        "reference_points": len(used),
        "test_points": len(test_err),
        "point_spread": r3(spread),
        "scale": scale,
        "residual_median_m": r3(np.median(ref_err)),
        "residual_max_m": r3(max(ref_err)),
        "test_median_m": r3(np.median(test_err)) if test_err else None,
        "test_p90_m": r3(np.percentile(test_err, 90)) if test_err else None,
        "test_max_m": r3(max(test_err)) if test_err else None,
    }
    align = {
        "meter_from_model": {"scale": scale, "rotation_xyzw": quat, "translation": trans},
        "phone_height_m": height_m,
        "reference_points": len(used),
        "holdout_points": holdout,
        "residual_median_m": stats["residual_median_m"],
    }
    alignment.validate_align(align)
    return FitResult(align=align, stats=stats, rows=rows)
