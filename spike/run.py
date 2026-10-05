"""Uji coba awal eutopos: bangun peta dari foto, lokalisasi foto uji, catat waktu per tahap.

Struktur data yang diharapkan:
    <dataset>/mapping/*.jpg   foto untuk membangun peta
    <dataset>/query/*.jpg     foto uji yang dilokalisasi

Contoh:
    python spike/run.py data/floor10 --out outputs/floor10

Mengikuti alur notebook resmi hloc (demo.ipynb, commit c13273b):
extract_features -> pairs -> match_features -> reconstruction -> QueryLocalizer + pose_from_cluster.
"""

import argparse
import csv
import json
import re
import time
from pathlib import Path

import pycolmap
from env_info import env
from fix_orientation import orientation
from hloc import (
    extract_features,
    match_features,
    pairs_from_exhaustive,
    pairs_from_retrieval,
    reconstruction,
)
from hloc.localize_sfm import QueryLocalizer, do_covisibility_clustering, pose_from_cluster
from hloc.utils.parsers import parse_retrieval

# Fitur lokal: (ekstraktor, pencocok).
FEATURES = {
    # Utama. Bukan SuperPoint: lisensinya non-komersial.
    "aliked": (extract_features.confs["aliked-n16"], match_features.confs["aliked+lightglue"]),
    # Pembanding klasik, setara bawaan COLMAP: SIFT (deskriptor RootSIFT, normalisasi bawaan
    # COLMAP) + tetangga terdekat dengan uji rasio 0,8 dan cek dua arah.
    "sift": (extract_features.confs["sift"], match_features.confs["NN-ratio"]),
}
# Pencocok yang bisa dipasangkan dengan fitur mana pun (uji 2x2 fitur lawan pencocok).
MATCHERS = {
    "nn-ratio": match_features.confs["NN-ratio"],
    "lightglue": {
        "lightglue-aliked": match_features.confs["aliked+lightglue"],
        "lightglue-sift": {
            "output": "matches-sift-lightglue",
            "model": {"name": "lightglue", "features": "sift"},
        },
    },
}
DEFAULT_MATCHER = {"aliked": "lightglue", "sift": "nn-ratio"}
GLOBAL = extract_features.confs["megaloc"]
EXHAUSTIVE_MAX = 30  # bawaan --exhaustive-max: di bawahnya semua pasangan, di atasnya retrieval


def sift_orientations_in_radians():
    """hloc menyimpan orientasi SIFT dalam derajat, bobot SIFT LightGlue dilatih dengan radian.

    Tanpa konversi ini SIFT + LightGlue dirugikan oleh masukan di luar sebaran latihnya.
    """
    import torch
    from hloc.matchers import lightglue as hloc_lightglue

    forward = hloc_lightglue.LightGlue._forward

    def converted(self, data):
        for k in ("oris0", "oris1"):
            if k in data:
                data[k] = torch.deg2rad(data[k])
        return forward(self, data)

    hloc_lightglue.LightGlue._forward = converted


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


def add_sequential_pairs(pairs_path: Path, refs: list[str], n: int):
    """Tambahkan pasangan frame berurutan (i dengan i+1..i+n) dari video yang sama.

    Setara sequential matching COLMAP untuk video. Retrieval saja bisa melewatkan tetangga
    langsung di tikungan yang buram, dan peta pecah jadi beberapa potongan.
    """
    by_video: dict[str, list[str]] = {}
    for r in refs:  # refs sudah terurut nama, nama frame = <video>_<nomor>.jpg
        by_video.setdefault(re.sub(r"_\d+$", "", Path(r).stem), []).append(r)
    extra = [
        f"{frames[i]} {frames[j]}"
        for frames in by_video.values()
        for i in range(len(frames))
        for j in range(i + 1, min(i + n + 1, len(frames)))
    ]
    # Pasangan ganda atau terbalik tidak masalah, hloc membuangnya saat mencocokkan dan mengimpor.
    # Baris kosong tidak boleh ada: import_matches hloc memecah setiap baris jadi dua nama.
    lines = pairs_path.read_text(encoding="utf-8").splitlines() + extra
    pairs_path.write_text("\n".join(p for p in lines if p.strip()), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--features", choices=FEATURES, default="aliked", help="fitur lokal")
    ap.add_argument(
        "--matcher",
        choices=["auto", *MATCHERS],
        default="auto",
        help="pencocok fitur; auto = pasangan bawaan fitur (aliked: lightglue, sift: nn-ratio)",
    )
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
    ap.add_argument(
        "--seq",
        type=int,
        default=0,
        help="frame video: tambah pasangan dengan N frame berikutnya (0 = mati). Pakai --out lain",
    )
    a = ap.parse_args()

    global GLOBAL
    GLOBAL = {**GLOBAL, "preprocessing": {**GLOBAL["preprocessing"], "resize_max": a.global_resize}}
    LOCAL, MATCHER = FEATURES[a.features]
    matcher_name = DEFAULT_MATCHER[a.features] if a.matcher == "auto" else a.matcher
    if matcher_name == "lightglue":
        MATCHER = MATCHERS["lightglue"][f"lightglue-{a.features}"]
        if a.features == "sift":
            sift_orientations_in_radians()
    else:
        MATCHER = MATCHERS[matcher_name]
    model = dict(LOCAL["model"])
    if a.features == "sift":
        # Opsi SIFT bawaan COLMAP (first_octave -1, peak_threshold 0,0067), bukan bawaan hloc
        # (0 dan 0,01): hloc lebih ketat, dan di lorong dalam ruangan hanya dapat ~260 keypoint
        # per gambar. Jumlahnya dibatasi lewat max_num_features pycolmap seperti COLMAP sendiri,
        # karena opsi max_keypoints ekstraktor DoG hloc (commit c13273b) rusak: topk pada skor
        # yang semuanya nol.
        model["options"] = {"max_num_features": a.max_kp if a.max_kp > 0 else 8192}
    else:
        model["max_num_keypoints"] = a.max_kp
    LOCAL = {
        **LOCAL,
        "model": model,
        "preprocessing": {**LOCAL["preprocessing"], "resize_max": a.resize},
    }

    root, out = a.dataset, a.out
    # hloc melewati gambar dan pasangan yang sudah ada di berkas .h5 (overwrite=False). Semua yang
    # bergantung pada setelan fitur lokal masuk subfolder per setelan, supaya run dengan --max-kp
    # atau --resize lain tidak diam-diam memakai fitur lama. Fitur global dan daftar pasangan
    # tidak bergantung pada setelan itu, jadi dipakai bersama.
    # ALIKED tanpa awalan: jalur peta layanan (server/pipeline.py) tetap sama.
    prefix = "" if a.features == "aliked" else f"{a.features}-"
    if matcher_name != DEFAULT_MATCHER[a.features]:
        prefix = f"{a.features}-{matcher_name}-"
    run_dir = out / f"{prefix}kp{a.max_kp}-r{a.resize}"
    run_dir.mkdir(parents=True, exist_ok=True)
    refs, queries = images_in(root, "mapping"), images_in(root, "query")
    # hloc mengabaikan tag rotasi EXIF, jadi foto potret diproses miring 90 derajat dan
    # menghasilkan pose salah tapi yakin. Hentikan di sini, jangan diam-diam lanjut.
    miring = [r for r in refs + queries if orientation(root / r) != 1]
    if miring:
        raise SystemExit(
            f"{len(miring)} foto punya tag rotasi EXIF (contoh: {miring[0]}). Jalankan dulu:\n"
            f"    python spike/fix_orientation.py {root} {root}-upright"
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
    if a.seq:
        add_sequential_pairs(out / "pairs-sfm.txt", refs, a.seq)
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

    base = {
        "features": a.features,
        "matcher": matcher_name,
        "max_keypoints": a.max_kp,
        "resize_max": a.resize,
        "covisibility_clustering": a.covis,
        "sequential_pairs": a.seq,
        "map_images": len(refs),
        "map_registered": model.num_reg_images(),
        "map_points3D": model.num_points3D(),
        "t_map_s": t_map,
    }
    if not queries:  # peta produksi: semua video berperan peta, tidak ada foto uji
        summary = {**base, "queries": 0, "env": env()}
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return

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
        **base,
        "queries": len(queries),
        "queries_localized": sum(r["ok"] for r in rows),
        "t_query_stage_total_s": t_q,
        # ponytail: rata-rata termasuk memuat model sekali per tahap; waktu hangat asli
        # diukur nanti di layanan yang memuat model sekali saat start
        "t_per_query_amortized_s": round(
            sum(t_q.values()) / n_q + sum(r["t_pose_s"] for r in rows) / n_q, 3
        ),
        "unit_note": "posisi dalam satuan model SfM, belum meter (butuh titik acuan)",
        "env": env(),
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
