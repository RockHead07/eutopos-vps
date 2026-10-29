"""Penaksir Sim3 titik-ke-titik, satu-satunya di repo (roadmap M1-1).

Dipakai alat ukur (spike/eval_meter.py) dan, nanti, kalibrasi lewat dashboard, supaya angka yang
diukur dan angka yang diterapkan dihitung oleh kode yang sama.
"""

import pycolmap


def fit(src, tgt, ransac_m):
    """Sim3 tgt_from_src dengan LO-RANSAC; None kalau gagal (kurang dari 3 titik, tak ada model)."""
    opts = pycolmap.RANSACOptions()
    opts.max_error = ransac_m
    ret = pycolmap.estimate_sim3d_robust(src, tgt, opts)
    return ret["tgt_from_src"] if ret else None
