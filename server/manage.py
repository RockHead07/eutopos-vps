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
    python -m server.manage building list
    python -m server.manage building add pens "Politeknik Elektronika"
Setelah menerbitkan versi baru, muat ulang layanan: docker compose restart api
"""

import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlmodel import Session, select

from server import alignment, jobs, navgraph, quick_align
from server.db import (
    DEFAULT_ORG_SLUG,
    Alignment,
    Area,
    Building,
    MapJob,
    MapVersion,
    Organization,
    engine_from_env,
    publish,
    register,
)
from server.map_layout import missing_files
from server.pipeline import missing_inputs, run_dir
from server.worker import DATA, MAPS, backfill_previews, backfill_thumbs


def _warn_dashboard_alignment(version_id: int, dashboard_id: int) -> None:
    print(
        f"PERINGATAN: penyelarasan dari dashboard (id {dashboard_id}) sedang berlaku "
        f"untuk versi id {version_id} dan didahulukan; align.json ini hanya dipakai untuk "
        "versi tanpa penyelarasan dari dashboard. Ubah lewat halaman Kalibrasi."
    )


def _protect_survey(destination: Path, dashboard: Alignment | None) -> None:
    replace_hint = "gunakan --replace-survey untuk melanjutkan"
    if dashboard is not None and dashboard.params.get("method", "survey") == "survey":
        raise ValueError(f"penyelarasan survey dari dashboard sedang berlaku, {replace_hint}")
    if destination.exists():
        try:
            prior = json.loads(destination.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"metode align.json lama tidak dapat dibaca, {replace_hint}") from exc
        if not isinstance(prior, dict):
            raise ValueError(f"metode align.json lama tidak dapat dibaca, {replace_hint}")
        if prior.get("method", "survey") == "survey":
            raise ValueError(f"align.json versi ini berisi penyelarasan survey, {replace_hint}")


def _quick_align(args: argparse.Namespace, session: Session) -> None:
    version = session.get(MapVersion, args.version)
    if version is None:
        raise SystemExit(f"versi peta id {args.version} tidak ada")
    map_dir = Path(version.path)
    run = run_dir(map_dir)
    destination = run / "align.json"
    try:
        if args.out is not None and (
            args.out.resolve() == destination.resolve()
            or (args.out.exists() and destination.exists() and args.out.samefile(destination))
        ):
            raise ValueError("jangan arahkan --out ke align.json versi ini, gunakan --install")

        centers, ups = quick_align.load_model(run / "sfm")
        if args.method == "arcore":
            result = quick_align.from_arcore(centers, quick_align.read_frames(args.frames))
            quality = (
                f"{result['matched_frames']} frame cocok, median residu "
                f"{result['residual_median_m']:.3f} m, maksimum {result['residual_max_m']:.3f} m"
            )
        else:
            pairs = [(a, b, float(distance)) for a, b, distance in args.pair]
            result = quick_align.from_known_distance(centers, ups, pairs)
            spread = result["gravity_spread_deg"]
            quality = f"{len(pairs)} pasangan, sebaran gravitasi {spread:.3f} derajat"
            if len(pairs) == 2:
                quality += f", selisih skala {result['scale_spread_percent']:.3f}%"

        dashboard = None
        if args.install:
            dashboard = session.exec(
                select(Alignment).where(
                    Alignment.map_version_id == version.id, Alignment.status == "applied"
                )
            ).first()
            if not args.replace_survey:
                _protect_survey(destination, dashboard)

        print(f"{result['method']}, skala {result['meter_from_model']['scale']:.6g}: {quality}")
        for warning in quick_align.warnings(result):
            print(f"PERINGATAN: {warning}")
        output = json.dumps(result, indent=2, allow_nan=False) + "\n"
        if args.out is not None:
            args.out.write_text(output, encoding="utf-8")
        if args.install:
            with TemporaryDirectory() as directory:
                source = Path(directory) / "align.json"
                source.write_text(output, encoding="utf-8")
                written, _ = alignment.install(
                    map_dir, run.name, navgraph.maps_root() / version.area_id, source, None
                )
            for path in written:
                print(f"dipasang: {path}")
            if dashboard is not None:
                _warn_dashboard_alignment(version.id, dashboard.id)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register", help="tambah versi kandidat untuk sebuah area")
    r.add_argument("area_id")
    r.add_argument("name")
    r.add_argument("path", help="folder peta di dalam container, misalnya /maps/demo")
    r.add_argument("--publish", action="store_true", help="langsung jadikan versi aktif")
    r.add_argument("--building", default="hcm", help="slug gedung untuk area baru (bawaan hcm)")
    p = sub.add_parser("publish", help="jadikan sebuah versi aktif")
    p.add_argument("version_id", type=int)
    sub.add_parser("list", help="tampilkan semua versi peta")
    j = sub.add_parser("job", help="antrekan pembangunan peta dari video atau folder frame")
    j.add_argument("area_id")
    j.add_argument("name")
    j.add_argument("--map", nargs="+", required=True, help="video atau folder frame untuk peta")
    j.add_argument("--query", nargs="*", default=[], help="video atau folder frame untuk uji")
    j.add_argument("--by", default="cli", help="dicatat sebagai pembuat pekerjaan")
    j.add_argument("--building", default="hcm", help="slug gedung untuk area baru (bawaan hcm)")
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
    qa = sub.add_parser("quick-align", help="hitung penyelarasan dari pose atau jarak antar-frame")
    qa.add_argument("--version", type=int, required=True, help="id versi peta (lihat 'list')")
    qa.add_argument("--method", required=True, choices=("arcore", "distance"))
    qa.add_argument("--frames", type=Path, help="frames.jsonl untuk metode arcore")
    qa.add_argument("--pair", nargs=3, action="append", metavar=("FRAME_A", "FRAME_B", "METER"))
    qa.add_argument("--out", type=Path, help="ekspor hasil JSON")
    qa.add_argument("--install", action="store_true", help="pasang align.json untuk versi ini")
    qa.add_argument("--replace-survey", action="store_true", help="izinkan install saat ada survey")
    b = sub.add_parser("building", help="kelola gedung")
    b_sub = b.add_subparsers(dest="building_cmd", required=True)
    b_sub.add_parser("list", help="tampilkan daftar gedung")
    b_add = b_sub.add_parser("add", help="tambah gedung baru (organisasi bawaan)")
    b_add.add_argument("slug", help="slug unik gedung")
    b_add.add_argument("name", help="nama gedung")
    a = ap.parse_args()
    if a.cmd == "quick-align":
        if a.method == "arcore" and (a.frames is None or a.pair):
            qa.error("metode arcore membutuhkan --frames saja")
        if a.method == "distance" and (a.frames is not None or not 1 <= len(a.pair or []) <= 2):
            qa.error("metode distance membutuhkan satu atau dua --pair FRAME_A FRAME_B METER")

    with Session(engine_from_env()) as s:
        if a.cmd == "building":
            if a.building_cmd == "list":
                buildings = list(s.exec(select(Building).order_by(Building.name)))
                stmt_areas = select(Area.id, Area.building_id)
                counts: dict[int, int] = {}
                for _, bld_id in s.exec(stmt_areas):
                    counts[bld_id] = counts.get(bld_id, 0) + 1
                for bld in buildings:
                    print(f"{bld.slug}  {bld.name}  {counts.get(bld.id, 0)}")
            elif a.building_cmd == "add":
                default_org = s.exec(
                    select(Organization).where(Organization.slug == DEFAULT_ORG_SLUG)
                ).first()
                if default_org is None:
                    raise SystemExit("default organization not found")
                existing = s.exec(
                    select(Building).where(
                        Building.org_id == default_org.id, Building.slug == a.slug
                    )
                ).first()
                if existing is not None:
                    raise SystemExit(f"building {a.slug} already exists")
                bld = Building(org_id=default_org.id, slug=a.slug, name=a.name)
                s.add(bld)
                s.commit()
                print(f"gedung {bld.slug} ({bld.name}) ditambahkan")
        elif a.cmd == "register":
            bld = s.exec(select(Building).where(Building.slug == a.building)).first()
            if bld is None:
                raise SystemExit(f"building {a.building} not found")
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
            try:
                v = register(s, a.area_id, a.name, a.path, building_id=bld.id)
            except ValueError as e:
                raise SystemExit(str(e)) from e
            if a.publish:
                v = publish(s, v.id)
            print(f"{v.area_id} v{v.version} (id {v.id}): {v.status}, {v.path}")
        elif a.cmd == "publish":
            v = publish(s, a.version_id)
            print(f"{v.area_id} v{v.version} (id {v.id}) sekarang aktif")
        elif a.cmd == "job":
            bld = s.exec(select(Building).where(Building.slug == a.building)).first()
            if bld is None:
                raise SystemExit(f"building {a.building} not found")
            # Disimpan absolut: pekerja berjalan dari folder kerja lain.
            videos = [{"path": str(Path(p).resolve()), "role": "peta"} for p in a.map]
            videos += [{"path": str(Path(p).resolve()), "role": "uji"} for p in a.query]
            if missing := missing_inputs(videos):
                raise SystemExit(f"berkas tidak ditemukan: {', '.join(missing)}")
            try:
                job = jobs.create_job(
                    s, a.area_id, a.name, a.by, videos, status="queued", building_id=bld.id
                )
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
        elif a.cmd == "quick-align":
            _quick_align(a, s)
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
                _warn_dashboard_alignment(v.id, dashboard)
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
