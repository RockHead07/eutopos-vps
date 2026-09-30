"""Kelola versi peta dari baris perintah (butuh DATABASE_URL).

Contoh (di dalam container):
    python -m server.manage register demo "Data contoh" /maps/demo --publish
    python -m server.manage list
    python -m server.manage publish 3
Setelah menerbitkan versi baru, muat ulang layanan: docker compose restart api
"""

import argparse
import os
from pathlib import Path

from sqlmodel import Session, select

from server.db import MapVersion, engine_from_env, publish, register
from server.map_layout import missing_files


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register", help="tambah versi kandidat untuk sebuah area")
    r.add_argument("area_id")
    r.add_argument("name")
    r.add_argument("path", help="folder peta di dalam container, misalnya /maps/demo")
    r.add_argument("--publish", action="store_true", help="langsung jadikan versi aktif")
    p = sub.add_parser("publish", help="jadikan sebuah versi aktif")
    p.add_argument("version_id", type=int)
    sub.add_parser("list", help="tampilkan semua versi peta")
    a = ap.parse_args()

    with Session(engine_from_env()) as s:
        if a.cmd == "register":
            # Setelan sama dengan layanan (server/app.py): diperiksa persis berkas yang dimuat.
            missing = missing_files(
                Path(a.path),
                int(os.environ.get("EUTOPOS_MAX_KP", 1024)),
                int(os.environ.get("EUTOPOS_RESIZE", 1024)),
                int(os.environ.get("EUTOPOS_GLOBAL_RESIZE", 512)),
            )
            if missing:
                raise SystemExit(
                    "peta tidak lengkap, tidak didaftarkan. Berkas yang tidak ada:\n  "
                    + "\n  ".join(map(str, missing))
                )
            v = register(s, a.area_id, a.name, a.path)
            if a.publish:
                v = publish(s, v.id)
            print(f"{v.area_id} v{v.version} (id {v.id}): {v.status}, {v.path}")
        elif a.cmd == "publish":
            v = publish(s, a.version_id)
            print(f"{v.area_id} v{v.version} (id {v.id}) sekarang aktif")
        else:
            for v in s.exec(select(MapVersion).order_by(MapVersion.area_id, MapVersion.version)):
                print(f"id {v.id}  {v.area_id} v{v.version}  {v.status:9}  {v.path}")


if __name__ == "__main__":
    main()
