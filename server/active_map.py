"""Peta aktif yang dimuat /localize, dan penukarannya setelah Terbitkan (spesifikasi bagian 7).

Peta baru dimuat di thread latar. Selama memuat, /localize tetap memakai peta lama. Kalau gagal,
peta lama tetap dipakai, versi aktif di database dikembalikan, dan galatnya ditampilkan dashboard.
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


def reload_in_background(state, engine, version_id: int, previous_id: int | None):
    """ponytail: memuat ulang seluruh model untuk peta baru (beberapa detik, memori sementara dua
    kali lipat). Pakai ulang model yang sudah dimuat kalau penukaran jadi sering."""
    state.reloading = True

    def run():
        with Session(engine) as s:
            v = s.get(MapVersion, version_id)
            try:
                localizer = load_localizer(Path(v.path))
            except Exception as e:
                log.exception("gagal memuat versi peta %s", version_id)
                if previous_id is not None:
                    publish(s, previous_id)  # versi lama aktif lagi
                v = s.get(MapVersion, version_id)
                v.status = "rejected"
                s.add(v)
                s.commit()
                state.reload_error = (
                    f"versi {v.version} gagal dimuat ({e}), peta lama tetap dipakai"
                )
                state.reloading = False
                return
            with state.lock:
                state.localizer, state.area_id, state.map_version = localizer, v.area_id, v.version
            state.reload_error, state.reloading = None, False

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t
