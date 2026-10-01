"""Kelola versi peta dan antrean bangun peta dari baris perintah (butuh DATABASE_URL).

Contoh (di dalam container):
    python -m server.manage register demo "Data contoh" /maps/demo --publish
    python -m server.manage list
    python -m server.manage publish 3
    python -m server.manage job floor10 "Lantai 10" --map /data/inbox/video1.mp4 \
        --query /data/inbox/video2.mp4
    python -m server.manage jobs
Setelah menerbitkan versi baru, muat ulang layanan: docker compose restart api
"""

import argparse
import os
from pathlib import Path

from sqlmodel import Session, select

from server import jobs
from server.db import MapJob, MapVersion, engine_from_env, publish, register
from server.map_layout import missing_files
from server.pipeline import missing_inputs


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
    j = sub.add_parser("job", help="antrekan pembangunan peta dari video atau folder frame")
    j.add_argument("area_id")
    j.add_argument("name")
    j.add_argument("--map", nargs="+", required=True, help="video atau folder frame untuk peta")
    j.add_argument("--query", nargs="*", default=[], help="video atau folder frame untuk uji")
    j.add_argument("--by", default="cli", help="dicatat sebagai pembuat pekerjaan")
    sub.add_parser("jobs", help="tampilkan antrean pekerjaan")
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
        elif a.cmd == "job":
            videos = [{"path": p, "role": "peta"} for p in a.map]
            videos += [{"path": p, "role": "uji"} for p in a.query]
            if missing := missing_inputs(videos):
                raise SystemExit(f"berkas tidak ditemukan: {', '.join(missing)}")
            job = jobs.create_job(s, a.area_id, a.name, a.by, videos, status="queued")
            print(f"pekerjaan {job.id} diantrekan untuk {job.area_id}")
        elif a.cmd == "jobs":
            for job in s.exec(select(MapJob).order_by(MapJob.id.desc())):
                when = f"{job.created_at:%Y-%m-%d %H:%M}"
                version = f"  versi id {job.map_version_id}" if job.map_version_id else ""
                stage = job.stage or "-"
                print(f"{job.id:4d}  {job.area_id}  {job.status:9}  {stage:8}  {when}{version}")
        else:
            for v in s.exec(select(MapVersion).order_by(MapVersion.area_id, MapVersion.version)):
                print(f"id {v.id}  {v.area_id} v{v.version}  {v.status:9}  {v.path}")


if __name__ == "__main__":
    main()
