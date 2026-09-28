"""Uji coba awal eutopos: bangun peta dari foto, lokalisasi foto uji, catat waktu per tahap.

Struktur data yang diharapkan:
    <dataset>/mapping/*.jpg   foto untuk membangun peta
    <dataset>/query/*.jpg     foto uji yang dilokalisasi

Contoh:
    python spike/run.py data/lantai10 --out outputs/lantai10

Mengikuti alur notebook resmi hloc (demo.ipynb, commit c13273b):
extract_features -> pairs -> match_features -> reconstruction -> QueryLocalizer + pose_from_cluster.
"""

import argparse
import csv
import json
import time
from pathlib import Path

import pycolmap
from hloc import (
    extract_features,
    match_features,
    pairs_from_exhaustive,
    pairs_from_retrieval,
    reconstruction,
)
from hloc.localize_sfm import QueryLocalizer, do_covisibility_clustering, pose_from_cluster
from hloc.utils.parsers import parse_retrieval
from tegakkan import orientation

LOCAL = extract_features.confs["aliked-n16"]  # bukan SuperPoint: lisensinya non-komersial
MATCHER = match_features.confs["aliked+lightglue"]
GLOBAL = extract_features.confs["megaloc"]
EXHAUSTIVE_MAX = 30  # bawaan --exhaustive-max: di bawahnya semua pasangan, di atasnya retrieval


def images_in(root: Path, sub: str) -> list[str]:
    exts = {".jpg", ".jpeg", ".png"}
    files = [p for p in (root / sub).iterdir() if p.is_file()]
    skipped = sorted({p.suffix.lower() or "(tanpa ekstensi)" for p in files} - exts)
    if skipped:
        # contoh: ponsel yang menyimpan HEIC. Set kamera ke JPEG, jangan diam-diam kehilangan foto.
        n = sum(p.suffix.lower() not in exts for p in files)
        print(f"PERINGATAN: {n} file di {sub}/ dilewati, ekstensi {', '.join(skipped)}")
    return sorted(p.relative_to(root).as_posix() for p in files if p.suffix.lower() in exts)


def timed(times: dict, key: str, fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    times[key] = round(time.perf_counter() - t0, 3)
    return out


def make_pairs(times, key, out, feats_global, root, queries, refs, k, exhaustive_max):
    # ponytail: exhaustive untuk data kecil (demo), retrieval MegaLoc untuk data lapangan
    if len(refs) <= exhaustive_max:
        if queries is refs:
            timed(times, key, pairs_from_exhaustive.main, out, image_list=refs)
        else:
            timed(times, key, pairs_from_exhaustive.main, out, image_list=queries, ref_list=refs)
        return
    if not feats_global.exists():
        timed(
            times,
            "global_extract_mapping",
            extract_features.main,
            GLOBAL,
            root,
            image_list=refs,
            feature_path=feats_global,
        )
    timed(
        times,
        key,
        pairs_from_retrieval.main,
        feats_global,
        out,
        # torch.topk di hloc gagal kalau k melebihi jumlah kandidat. Saat memetakan, foto itu
        # sendiri tidak dihitung sebagai kandidat.
        num_matched=min(k, len(refs) - (1 if queries is refs else 0)),
        query_list=queries,
        db_list=refs,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--k-map", type=int, default=20, help="tetangga retrieval saat membangun peta")
    ap.add_argument("--k-loc", type=int, default=10, help="kandidat retrieval per foto uji")
    # Bawaan hloc: keypoint tanpa batas (rata2 ~2.800/foto di data demo) -> ~12 s/pasangan di CPU.
    # Lihat spike/bench_matching.py untuk ukuran waktu per batas keypoint.
    ap.add_argument(
        "--max-kp", type=int, default=1024, help="batas keypoint ALIKED, -1 = tanpa batas"
    )
    ap.add_argument("--resize", type=int, default=1024, help="sisi terpanjang foto saat ekstraksi")
    # MegaLoc berbasis ViT (patch 14): biaya naik kuadratik terhadap jumlah token. Di data contoh,
    # 512 hampir 6x lebih cepat dari 1024 dengan kandidat teratas yang sama (docs/spike-plan.md).
    ap.add_argument("--global-resize", type=int, default=1024, help="sisi terpanjang untuk MegaLoc")
    ap.add_argument(
        "--exhaustive-max",
        type=int,
        default=EXHAUSTIVE_MAX,
        help="jumlah foto peta maksimum untuk pencocokan semua pasangan; 0 = selalu retrieval",
    )
    # Pipeline resmi hloc mematikannya. Varian uji untuk area yang tampak mirip (pintu seragam):
    # kandidat dikelompokkan per area yang saling terlihat, PnP per kelompok, inlier terbanyak.
    ap.add_argument("--covis", action="store_true", help="covisibility clustering saat lokalisasi")
    a = ap.parse_args()

    global LOCAL, GLOBAL
    GLOBAL = {**GLOBAL, "preprocessing": {**GLOBAL["preprocessing"], "resize_max": a.global_resize}}
    LOCAL = {
        **LOCAL,
        "model": {**LOCAL["model"], "max_num_keypoints": a.max_kp},
        "preprocessing": {**LOCAL["preprocessing"], "resize_max": a.resize},
    }

    root, out = a.dataset, a.out
    # hloc melewati gambar dan pasangan yang sudah ada di berkas .h5 (overwrite=False). Semua yang
    # bergantung pada setelan fitur lokal masuk subfolder per setelan, supaya run dengan --max-kp
    # atau --resize lain tidak diam-diam memakai fitur lama. Fitur global dan daftar pasangan
    # tidak bergantung pada setelan itu, jadi dipakai bersama.
    run_dir = out / f"kp{a.max_kp}-r{a.resize}"
    run_dir.mkdir(parents=True, exist_ok=True)
    refs, queries = images_in(root, "mapping"), images_in(root, "query")
    # hloc mengabaikan tag rotasi EXIF, jadi foto potret diproses miring 90 derajat dan
    # menghasilkan pose salah tapi yakin. Hentikan di sini, jangan diam-diam lanjut.
    miring = [r for r in refs + queries if orientation(root / r) != 1]
    if miring:
        raise SystemExit(
            f"{len(miring)} foto punya tag rotasi EXIF (contoh: {miring[0]}). Jalankan dulu:\n"
            f"    python spike/tegakkan.py {root} {root}-tegak"
        )
    feats, matches = run_dir / "features.h5", run_dir / "matches.h5"
    feats_global = out / f"global-r{a.global_resize}.h5"  # per resolusi, supaya tidak tercampur
    t_map, t_q = {}, {}

    # 1. Peta
    timed(
        t_map,
        "local_extract",
        extract_features.main,
        LOCAL,
        root,
        image_list=refs,
        feature_path=feats,
    )
    make_pairs(
        t_map,
        "pairs",
        out / "pairs-sfm.txt",
        feats_global,
        root,
        refs,
        refs,
        a.k_map,
        a.exhaustive_max,
    )
    timed(
        t_map,
        "match",
        match_features.main,
        MATCHER,
        out / "pairs-sfm.txt",
        features=feats,
        matches=matches,
    )
    # Satu ponsel = satu kamera (intrinsik dibagi, sesuai panduan COLMAP). Foto campuran: otomatis.
    sizes = {
        (c.width, c.height) for c in (pycolmap.infer_camera_from_image(root / r) for r in refs)
    }
    mode = pycolmap.CameraMode.SINGLE if len(sizes) == 1 else pycolmap.CameraMode.AUTO
    model = timed(
        t_map,
        "reconstruction",
        reconstruction.main,
        run_dir / "sfm",
        root,
        out / "pairs-sfm.txt",
        feats,
        matches,
        camera_mode=mode,
        image_list=refs,
    )

    # 2. Foto uji (diproses sekaligus; waktu tahap termasuk memuat model sekali)
    if feats_global.exists() or len(refs) > a.exhaustive_max:
        timed(
            t_q,
            "global_extract",
            extract_features.main,
            GLOBAL,
            root,
            image_list=queries,
            feature_path=feats_global,
        )
    timed(
        t_q,
        "local_extract",
        extract_features.main,
        LOCAL,
        root,
        image_list=queries,
        feature_path=feats,
    )
    make_pairs(
        t_q,
        "pairs",
        out / "pairs-loc.txt",
        feats_global,
        root,
        queries,
        refs,
        a.k_loc,
        a.exhaustive_max,
    )
    timed(
        t_q,
        "match",
        match_features.main,
        MATCHER,
        out / "pairs-loc.txt",
        features=feats,
        matches=matches,
    )

    retrieval = parse_retrieval(out / "pairs-loc.txt")
    map_cam = next(iter(model.cameras.values()))
    localizer = QueryLocalizer(model, {"estimation": {"ransac": {"max_error": 12}}})
    rows = []
    for q in queries:
        cam = pycolmap.infer_camera_from_image(root / q)
        if (cam.width, cam.height) == (map_cam.width, map_cam.height):
            cam = map_cam  # ponsel sama, resolusi sama: pakai intrinsik hasil kalibrasi peta
        ids = [
            model.find_image_with_name(n).image_id
            for n in retrieval.get(q, [])
            if model.find_image_with_name(n)
        ]
        t0 = time.perf_counter()
        ret = None
        for cluster in (
            (do_covisibility_clustering(ids, model) if a.covis else [ids]) if ids else []
        ):
            r, _ = pose_from_cluster(localizer, q, cam, cluster, feats, matches)
            if r is not None and (ret is None or r["num_inliers"] > ret["num_inliers"]):
                ret = r
        dt = round(time.perf_counter() - t0, 3)
        ok = ret is not None
        center = ret["cam_from_world"].inverse().translation.tolist() if ok else None
        rows.append(
            {
                "query": q,
                "ok": ok,
                "inliers": ret["num_inliers"] if ok else 0,
                "correspondences": len(ret["inlier_mask"]) if ok else 0,
                "t_pose_s": dt,
                "center_xyz_model": center,
            }
        )

    n_q = max(len(queries), 1)
    summary = {
        "max_keypoints": a.max_kp,
        "resize_max": a.resize,
        "covisibility_clustering": a.covis,
        "map_images": len(refs),
        "map_registered": model.num_reg_images(),
        "map_points3D": model.num_points3D(),
        "t_map_s": t_map,
        "queries": len(queries),
        "queries_localized": sum(r["ok"] for r in rows),
        "t_query_stage_total_s": t_q,
        # ponytail: rata-rata termasuk memuat model sekali per tahap; waktu hangat asli
        # diukur nanti di layanan yang memuat model sekali saat start
        "t_per_query_amortized_s": round(
            sum(t_q.values()) / n_q + sum(r["t_pose_s"] for r in rows) / n_q, 3
        ),
        "unit_note": "posisi dalam satuan model SfM, belum meter (butuh titik acuan)",
    }
    sfx = "-covis" if a.covis else ""  # varian lokalisasi, peta dan fitur sama
    with open(run_dir / f"results{sfx}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["query"])
        w.writeheader()
        w.writerows(rows)
    (run_dir / f"summary{sfx}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
