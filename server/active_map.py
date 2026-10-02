"""Peta aktif yang dimuat /localize, dan penukarannya setelah Terbitkan (spesifikasi bagian 7).

Peta baru dimuat di thread latar. Selama memuat, /localize tetap memakai peta lama. Versi baru
diterbitkan di database SETELAH terbukti bisa dimuat: kalau gagal (berkas rusak, GPU penuh, proses
mati di tengah), database tidak berubah, peta lama tetap dipakai, galatnya ditampilkan dashboard.
"""

import logging
import os
import threading
from pathlib import Path

from sqlmodel import Session

from server.db import MapVersion, publish
from server.localizer import MIN_INLIERS, Localizer

log = logging.getLogger("eutopos")


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def serving_area() -> str:
    return os.environ.get("EUTOPOS_AREA", "demo")


def load_localizer(map_dir: Path) -> Localizer:
    return Localizer(
        map_dir,
        max_kp=_env_int("EUTOPOS_MAX_KP", 1024),
        resize=_env_int("EUTOPOS_RESIZE", 1024),
        global_resize=_env_int("EUTOPOS_GLOBAL_RESIZE", 512),
        k=_env_int("EUTOPOS_K", 5),
        device=os.environ.get("EUTOPOS_DEVICE", "cpu"),
        min_inliers=_env_int("EUTOPOS_MIN_INLIERS", MIN_INLIERS),
    )


def reload_in_background(state, engine, version_id: int, by: str | None):
    """Muat versi peta, terbitkan atas nama `by`, lalu tukar peta yang dilayani.

    ponytail: memuat ulang seluruh model untuk peta baru (beberapa detik, memori sementara dua
    kali lipat). Pakai ulang model yang sudah dimuat kalau penukaran jadi sering."""
    state.reloading, state.reload_error = True, None

    def run():
        label = f"versi id {version_id}"
        try:
            with Session(engine) as s:
                v = s.get(MapVersion, version_id)
                label, path = f"versi {v.version}", Path(v.path)
            localizer = load_localizer(path)  # tanpa sesi database terbuka selama memuat
            with Session(engine) as s:
                v = publish(s, version_id, by=by)
            with state.lock:
                state.localizer, state.area_id, state.map_version = localizer, v.area_id, v.version
        except Exception as e:
            log.exception("gagal menerbitkan %s", label)
            state.reload_error = f"{label} gagal diterbitkan ({e}), peta lama tetap dipakai"
        finally:
            state.reloading = False

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t
