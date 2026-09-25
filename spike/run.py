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
from hloc.localize_sfm import QueryLocalizer, pose_from_cluster
from hloc.utils.parsers import parse_retrieval

LOCAL = extract_features.confs["aliked-n16"]  # bukan SuperPoint: lisensinya non-komersial
MATCHER = match_features.confs["aliked+lightglue"]
GLOBAL = extract_features.confs["megaloc"]
EXHAUSTIVE_MAX = 30  # di bawah ini semua pasangan dicocokkan; di atasnya pakai retrieval


def images_in(root: Path, sub: str) -> list[str]:
    exts = {".jpg", ".jpeg", ".png"}
    return sorted(
        p.relative_to(root).as_posix() for p in (root / sub).iterdir() if p.suffix.lower() in exts
    )


def timed(times: dict, key: str, fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    times[key] = round(time.perf_counter() - t0, 3)
    return out


def make_pairs(times, key, out, feats_global, root, queries, refs, k):
    # ponytail: exhaustive untuk data kecil (demo), retrieval MegaLoc untuk data lapangan
    if len(refs) <= EXHAUSTIVE_MAX:
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
        num_matched=k,
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
    a = ap.parse_args()

    global LOCAL
    LOCAL = {
        **LOCAL,
        "output": f"{LOCAL['output']}-kp{a.max_kp}-r{a.resize}",
        "model": {**LOCAL["model"], "max_num_keypoints": a.max_kp},
        "preprocessing": {**LOCAL["preprocessing"], "resize_max": a.resize},
    }

    root, out = a.dataset, a.out
    out.mkdir(parents=True, exist_ok=True)
    refs, queries = images_in(root, "mapping"), images_in(root, "query")
    feats, matches = out / "features.h5", out / "matches.h5"
    feats_global = out / "global.h5"
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
    make_pairs(t_map, "pairs", out / "pairs-sfm.txt", feats_global, root, refs, refs, a.k_map)
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
        out / "sfm",
        root,
        out / "pairs-sfm.txt",
        feats,
        matches,
        camera_mode=mode,
        image_list=refs,
    )

    # 2. Foto uji (diproses sekaligus; waktu tahap termasuk memuat model sekali)
    if feats_global.exists() or len(refs) > EXHAUSTIVE_MAX:
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
    make_pairs(t_q, "pairs", out / "pairs-loc.txt", feats_global, root, queries, refs, a.k_loc)
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
        ret, _ = pose_from_cluster(localizer, q, cam, ids, feats, matches) if ids else (None, {})
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
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["query"])
        w.writeheader()
        w.writerows(rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
