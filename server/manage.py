"""Kelola versi peta dan antrean bangun peta dari baris perintah (butuh DATABASE_URL).

Contoh (di dalam container):
    python -m server.manage register demo "Data contoh" /maps/demo --publish
    python -m server.manage list
    python -m server.manage publish 3
    python -m server.manage job floor10 "Lantai 10" --map /data/inbox/video1.mp4 \
        --query /data/inbox/video2.mp4
    python -m server.manage jobs
    python -m server.manage previews    # pratinjau untuk job lama, dari frame yang tersimpan
    python -m server.manage thumbs      # foto kecil frame scan untuk halaman area (job lama)
    python -m server.manage align --version 7 --align /data/eval/align.json \
        --navgraph /data/eval/navgraph.json   # di container worker (/maps bisa ditulis)
Setelah menerbitkan versi baru, muat ulang layanan: docker compose restart api
"""

import argparse
import os
from pathlib import Path

from sqlmodel import Session, select

from server import alignment, jobs, navgraph
from server.db import Alignment, MapJob, MapVersion, engine_from_env, publish, register
from server.map_layout import missing_files
from server.pipeline import missing_inputs
from server.worker import DATA, MAPS, backfill_previews, backfill_thumbs


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
    sub.add_parser(
        "previews", help="buat pratinjau job selesai yang belum punya, dari frame tersimpan"
    )
    sub.add_parser("thumbs", help="buat foto kecil frame scan untuk job selesai yang belum punya")
    al = sub.add_parser(
        "align", help="pasang align.json (versi peta) dan/atau navgraph.json (area) terukur"
    )
    al.add_argument("--version", type=int, required=True, help="id versi peta (lihat 'list')")
    al.add_argument("--align", type=Path, help="align.json dari spike/eval_meter.py")
    al.add_argument("--navgraph", type=Path, help="navgraph.json untuk area versi itu")
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
            # Disimpan absolut: pekerja berjalan dari folder kerja lain.
            videos = [{"path": str(Path(p).resolve()), "role": "peta"} for p in a.map]
            videos += [{"path": str(Path(p).resolve()), "role": "uji"} for p in a.query]
            if missing := missing_inputs(videos):
                raise SystemExit(f"berkas tidak ditemukan: {', '.join(missing)}")
            try:
                job = jobs.create_job(s, a.area_id, a.name, a.by, videos, status="queued")
            except ValueError as e:
                raise SystemExit(str(e)) from e
            print(f"pekerjaan {job.id} diantrekan untuk {job.area_id}")
        elif a.cmd == "jobs":
            for job in s.exec(select(MapJob).order_by(MapJob.id.desc())):
                when = f"{job.created_at:%Y-%m-%d %H:%M}"
                version = f"  versi id {job.map_version_id}" if job.map_version_id else ""
                stage = job.stage or "-"
                print(f"{job.id:4d}  {job.area_id}  {job.status:9}  {stage:8}  {when}{version}")
        elif a.cmd == "previews":
            made, skipped = backfill_previews(s, DATA, MAPS)
            print(f"{made} pratinjau dibuat, {skipped} dilewati (frame tidak ditemukan)")
        elif a.cmd == "thumbs":
            made, skipped = backfill_thumbs(s, DATA, MAPS)
            print(f"foto kecil dibuat untuk {made} job, {skipped} dilewati (frame tidak ditemukan)")
        elif a.cmd == "align":
            v = s.get(MapVersion, a.version)
            if v is None:
                raise SystemExit(f"versi peta id {a.version} tidak ada")
            run_name = (
                f"kp{int(os.environ.get('EUTOPOS_MAX_KP', 1024))}"
                f"-r{int(os.environ.get('EUTOPOS_RESIZE', 1024))}"
            )
            try:
                written, warnings = alignment.install(
                    Path(v.path), run_name, navgraph.maps_root() / v.area_id, a.align, a.navgraph
                )
            except ValueError as e:
                raise SystemExit(f"tidak ada yang dipasang: {e}") from e
            for w in warnings:
                print(f"PERINGATAN: {w}")
            for p in written:
                print(f"dipasang: {p}")
            dashboard = (
                a.align
                and s.exec(
                    select(Alignment.id).where(
                        Alignment.map_version_id == v.id, Alignment.status == "applied"
                    )
                ).first()
            )
            if dashboard:
                print(
                    f"PERINGATAN: penyelarasan dari dashboard (id {dashboard}) sedang berlaku "
                    f"untuk versi id {v.id} dan didahulukan; align.json ini hanya dipakai untuk "
                    "versi tanpa penyelarasan dari dashboard. Ubah lewat halaman Kalibrasi."
                )
            elif a.align and v.status == "published":
                print(
                    f"Versi id {v.id} sedang aktif: layanan memakai align.json baru pada "
                    "permintaan berikutnya, tanpa restart (cek /health aligned)."
                )
            elif a.align:
                print(
                    f"align.json ikut dimuat saat versi id {v.id} diterbitkan (dashboard atau "
                    "'manage publish')."
                )
        else:
            for v in s.exec(select(MapVersion).order_by(MapVersion.area_id, MapVersion.version)):
                print(f"id {v.id}  {v.area_id} v{v.version}  {v.status:9}  {v.path}")


if __name__ == "__main__":
    main()
