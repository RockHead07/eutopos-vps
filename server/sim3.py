"""Penaksir Sim3 titik-ke-titik, satu-satunya di repo (roadmap M1-1).

Dipakai alat ukur (spike/eval_meter.py) dan, nanti, kalibrasi lewat dashboard, supaya angka yang
diukur dan angka yang diterapkan dihitung oleh kode yang sama.
"""

import numpy as np
import pycolmap


def fit(src, tgt, ransac_m):
    """Sim3 tgt_from_src dengan LO-RANSAC; None kalau gagal (kurang dari 3 titik, tak ada model)."""
    opts = pycolmap.RANSACOptions()
    opts.max_error = ransac_m
    ret = pycolmap.estimate_sim3d_robust(src, tgt, opts)
    return ret["tgt_from_src"] if ret else None


def from_align(meter_from_model: dict):
    """Sim3 model ke meter dari bagian meter_from_model sebuah align.json."""
    q = np.asarray(meter_from_model["rotation_xyzw"], float)
    t = np.asarray(meter_from_model["translation"], float)
    return pycolmap.Sim3d(float(meter_from_model["scale"]), pycolmap.Rotation3d(q), t)
