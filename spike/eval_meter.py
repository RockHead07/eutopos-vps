"""Ubah hasil lokalisasi (satuan model SfM) ke meter dan hitung galat terhadap titik acuan.

Foto uji diambil sambil berdiri di atas titik lantai yang sudah diukur. Nama foto diawali ID titik:
    query/P07_a.jpg, query/P07_b.jpg  ->  titik P07

Titik acuan (CSV, meter, relatif terhadap satu titik asal di koridor):
    point,x_m,y_m
    P01,0.00,0.40

Penyelarasan model ke meter memakai Sim3 (skala, rotasi, translasi) dari pusat kamera foto uji ke
titik acuan. Skema leave-one-out: galat tiap titik dihitung dari Sim3 yang ditaksir TANPA titik itu,
jadi tidak ada titik yang menilai dirinya sendiri. Foto yang gagal dilokalisasi dihitung gagal.

Arah hadap: foto yang namanya berakhiran arah sumbu menghadap arah yang diketahui:
    P07_xp.jpg (+x, 0 derajat), P07_yp.jpg (+y, 90), P07_xn.jpg (-x, 180), P07_yn.jpg (-y, 270)
Sudut diukur dari +x ke arah +y. Galatnya = selisih sudut horizontal sumbu optik kamera hasil
lokalisasi (setelah Sim3) terhadap arah itu. Foto tanpa akhiran arah (P07_a.jpg) hanya dinilai
posisinya. Ketelitian galat arah dibatasi ketelitian memegang ponsel lurus ke sumbu.

Confident wrong (salah yakin): foto yang DIANGGAP berhasil oleh pipeline (ada pose) tapi galatnya
> --wrong-m. Untuk navigasi ini lebih berbahaya daripada gagal: aplikasi tidak tahu harus mencoba
lagi.

Contoh:
    python spike/eval_meter.py outputs/floor10/kp1024-r1024/results.csv \
        data/floor10/reference_points.csv
    python spike/eval_meter.py --self-test
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import pycolmap

AMBANG_M = 1.0  # pertanyaan spike: galat <= 1,0 m pada >= 70% foto uji
SALAH_M = 3.0  # bawaan --wrong-m: kira-kira sudah di depan pintu atau lorong yang salah
HEADING_DEG = {"xp": 0.0, "yp": 90.0, "xn": 180.0, "yn": 270.0}  # akhiran nama foto -> arah hadap
# ponytail: ambang pelaporan, bukan target PA. 10 derajat = ambang kasar benchmark lokalisasi
# visual; 30 derajat = kira-kira batas panah AR masih menunjuk koridor yang benar.
HEADING_OK_DEG = (10.0, 30.0)


def point_id(query: str) -> str:
    return Path(query).stem.split("_")[0]


def heading_gt(query: str):
    """Arah hadap yang diketahui dari akhiran nama foto, atau None."""
    parts = Path(query).stem.split("_")
    return HEADING_DEG.get(parts[1].lower()) if len(parts) > 1 else None


def heading_error(sim, view_model, gt_deg):
    """Selisih sudut horizontal (derajat) sumbu optik kamera di kerangka meter terhadap gt_deg."""
    d = sim.rotation.matrix() @ np.asarray(view_model, float)
    if np.hypot(d[0], d[1]) < 0.3 * np.linalg.norm(d):  # kamera nyaris tegak lurus lantai
        return None
    yaw = np.degrees(np.arctan2(d[1], d[0]))
    return round(float(abs((yaw - gt_deg + 180) % 360 - 180)), 1)


def fit(src, tgt, ransac_m):
    """Sim3 tgt_from_src dengan LO-RANSAC; None kalau gagal."""
    opts = pycolmap.RANSACOptions()
    opts.max_error = ransac_m
    ret = pycolmap.estimate_sim3d_robust(src, tgt, opts)
    return ret["tgt_from_src"] if ret else None


def evaluate(rows, gt, height_m, ransac_m, salah_m=SALAH_M, dirs=None):
    """rows: dict query -> pusat kamera (xyz model) atau None. gt: dict titik -> (x_m, y_m).

    dirs (opsional): dict query -> sumbu optik kamera (xyz model). Bila ada, foto berakhiran arah
    (lihat HEADING_DEG) juga dinilai arah hadapnya dengan Sim3 leave-one-out yang sama.
    """
    dirs = dirs or {}
    loc = {q: c for q, c in rows.items() if c is not None and point_id(q) in gt}
    pts = sorted({point_id(q) for q in loc})
    if len(pts) < 4:
        raise SystemExit(f"butuh foto terlokalisasi di >= 4 titik acuan, ada {len(pts)}")

    xy = np.array([gt[p] for p in pts])
    sv = np.linalg.svd(xy - xy.mean(0), compute_uv=False)
    spread = float(sv[1] / sv[0])  # ~0 = titik segaris, rotasi di sekitar garis itu tak tentu

    def target(q):
        x, y = gt[point_id(q)]
        return [x, y, height_m]  # ponytail: tinggi ponsel dianggap tetap, galat dilaporkan 2D

    out = []
    for q in sorted(rows):
        if point_id(q) not in gt:
            continue
        err = herr = None
        if rows[q] is not None:
            train = [k for k in loc if point_id(k) != point_id(q)]
            sim = fit(
                np.array([loc[k] for k in train], float),
                np.array([target(k) for k in train], float),
                ransac_m,
            )
            if sim is not None:
                p = sim * np.array([rows[q]], float)
                err = round(float(np.linalg.norm(p[0, :2] - np.array(gt[point_id(q)]))), 3)
                if dirs.get(q) is not None and heading_gt(q) is not None:
                    herr = heading_error(sim, dirs[q], heading_gt(q))
        out.append({"query": q, "point": point_id(q), "error_m": err, "heading_err_deg": herr})

    # Satu Sim3 dari SEMUA titik: disimpan sebagai align.json (peta ke meter). Sisa per foto yang
    # menonjol biasanya berarti salah ukur atau salah nama file, bukan kesalahan VPS.
    names = list(loc)
    src = np.array([loc[k] for k in names], float)
    sim_all = fit(src, np.array([target(k) for k in names], float), ransac_m)
    sisa = (
        np.linalg.norm((sim_all * src)[:, :2] - np.array([gt[point_id(k)] for k in names]), axis=1)
        if sim_all is not None
        else None
    )

    errs = [r["error_m"] for r in out]
    ok = [e for e in errs if e is not None]
    n_salah = sum(e > salah_m for e in ok)
    summary = {
        "queries": len(errs),
        "queries_with_error": len(ok),
        "reference_points_used": len(pts),
        "point_spread": round(spread, 3),
        "median_error_m": round(float(np.median(ok)), 3) if ok else None,
        "p90_error_m": round(float(np.percentile(ok, 90)), 3) if ok else None,
        # RMSE dan persen <= 2 m: sejajar dengan pelaporan Kim & Shin (2025)
        "rmse_error_m": round(float(np.sqrt(np.mean(np.square(ok)))), 3) if ok else None,
        # yang gagal dilokalisasi atau gagal diselaraskan dihitung melewati ambang
        f"pct_within_{AMBANG_M}m": round(100 * sum(e <= AMBANG_M for e in ok) / len(errs), 1),
        "pct_within_2.0m": round(100 * sum(e <= 2.0 for e in ok) / len(errs), 1),
        f"pct_confident_wrong_gt_{salah_m}m": round(100 * n_salah / len(errs), 1),
        "residual_median_m": round(float(np.median(sisa)), 3) if sisa is not None else None,
        "residual_max_m": round(float(sisa.max()), 3) if sisa is not None else None,
        "residual_worst": names[int(sisa.argmax())] if sisa is not None else None,
    }
    # foto berarah yang gagal dilokalisasi juga dihitung melewati ambang, sama seperti posisi
    with_heading = [r for r in out if heading_gt(r["query"]) is not None]
    if with_heading:
        h_ok = [r["heading_err_deg"] for r in with_heading if r["heading_err_deg"] is not None]
        summary["heading_queries"] = len(with_heading)
        summary["heading_queries_with_error"] = len(h_ok)
        summary["median_heading_err_deg"] = round(float(np.median(h_ok)), 1) if h_ok else None
        summary["p90_heading_err_deg"] = round(float(np.percentile(h_ok, 90)), 1) if h_ok else None
        for lim in HEADING_OK_DEG:
            within = sum(e <= lim for e in h_ok)
            summary[f"pct_heading_within_{lim:g}deg"] = round(100 * within / len(with_heading), 1)
    if spread < 0.05:
        summary["warning"] = "reference points nearly collinear; alignment unstable"
    return out, summary, sim_all


def read_results(path: Path):
    """-> (query -> pusat kamera atau None, query -> jumlah inlier, query -> sumbu optik atau None).

    Kolom view_dir_model hanya ada di results.csv baru; berkas lama tetap terbaca tanpa arah.
    """
    rows, inliers, dirs = {}, {}, {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ok = r["ok"] == "True" and r["center_xyz_model"]
            rows[r["query"]] = json.loads(r["center_xyz_model"]) if ok else None
            inliers[r["query"]] = int(r["inliers"])
            view = r.get("view_dir_model")
            dirs[r["query"]] = json.loads(view) if ok and view else None
    return rows, inliers, dirs


def read_gt(path: Path):
    with open(path, encoding="utf-8") as f:
        return {r["point"]: (float(r["x_m"]), float(r["y_m"])) for r in csv.DictReader(f)}


def self_test():
    """Data sintetis: model = Sim3 acak dari dunia meter + derau. Galat harus kembali kecil."""
    rng = np.random.default_rng(0)
    gt = {f"P{i:02d}": (i * 1.5, 0.3 if i % 2 else 1.7) for i in range(12)}  # zig-zag, lebar 2 m
    q = np.array([0.1, 0.7, 0.2, 0.68])  # rotasi sembarang, xyzw
    world_from_model = pycolmap.Sim3d(
        4.0, pycolmap.Rotation3d(q / np.linalg.norm(q)), np.array([3.0, -1, 2])
    )
    model_from_world = world_from_model.inverse()
    rows = {}
    for p, (x, y) in gt.items():
        for s in "ab":
            w = np.array([[x, y, 1.3]]) + rng.normal(0, 0.05, 3)  # derau 5 cm
            rows[f"query/{p}_{s}.jpg"] = (model_from_world * w)[0].tolist()
    rows["query/P03_b.jpg"] = None  # gagal lokalisasi
    far = model_from_world * np.array([[50.0, 50, 1.3]])
    rows["query/P05_b.jpg"] = far[0].tolist()  # lokalisasi salah besar
    _, s, sim = evaluate(rows, gt, 1.3, 1.0)
    assert s["queries"] == 24 and s["queries_with_error"] == 23, s
    assert s["median_error_m"] < 0.15, s
    assert s["pct_within_1.0m"] == round(100 * 22 / 24, 1), s  # 2 gagal dari 24
    assert s["pct_within_2.0m"] == s["pct_within_1.0m"], s
    assert s["pct_confident_wrong_gt_3.0m"] == round(100 * 1 / 24, 1), s  # hanya P05_b
    assert s["rmse_error_m"] > 10 * s["median_error_m"], s  # RMSE peka pada satu salah besar
    assert s["residual_median_m"] < 0.1, s  # derau 5 cm
    assert s["residual_worst"] == "query/P05_b.jpg", s  # outlier tertangkap
    assert abs(sim.scale - 4.0) < 0.05, sim  # Sim3 semua titik = kebalikan model_from_world
    # Arah hadap: tiap titik difoto ke empat arah sumbu, kamera sedikit menunduk, derau 2 derajat.
    rot = model_from_world.rotation.matrix()
    rows_h, dirs = {}, {}
    for p, (x, y) in gt.items():
        for sfx, deg in HEADING_DEG.items():
            name = f"query/{p}_{sfx}.jpg"
            w = np.array([[x, y, 1.3]]) + rng.normal(0, 0.05, 3)
            rows_h[name] = (model_from_world * w)[0].tolist()
            yaw = np.radians(deg + rng.normal(0, 2))
            dirs[name] = (rot @ np.array([np.cos(yaw), np.sin(yaw), -0.2])).tolist()
    dirs["query/P04_xp.jpg"] = (rot @ np.array([0.0, -1.0, 0.0])).tolist()  # salah 90 derajat
    dirs["query/P06_yp.jpg"] = None  # tanpa arah (results.csv lama): tidak dinilai, tapi dihitung
    out_h, s3, _ = evaluate(rows_h, gt, 1.3, 1.0, dirs=dirs)
    assert s3["heading_queries"] == 48 and s3["heading_queries_with_error"] == 47, s3
    assert s3["median_heading_err_deg"] < 5, s3
    worst = max(out_h, key=lambda r: r["heading_err_deg"] or 0)
    assert worst["query"] == "query/P04_xp.jpg" and abs(worst["heading_err_deg"] - 90) < 5, worst
    assert s3["pct_heading_within_10deg"] == round(100 * 46 / 48, 1), s3  # salah 90 dan tanpa arah
    assert heading_gt("query/P01_a.jpg") is None and heading_gt("q/P01_YN.jpg") == 270.0
    assert "heading_queries" not in s, s  # tanpa foto berarah: ringkasan tidak berubah
    line = {f"L{i}": (i * 1.0, 0.0) for i in range(5)}
    _, s2, _ = evaluate({f"q/L{i}_a.jpg": [i, 0, 0] for i in range(5)}, line, 1.3, 1.0)
    assert "warning" in s2, s2
    print("self-test OK", json.dumps(s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path, nargs="?", help="results.csv dari spike/run.py")
    ap.add_argument("points", type=Path, nargs="?", help="CSV titik acuan: point,x_m,y_m")
    ap.add_argument("--height", type=float, default=1.3, help="tinggi ponsel dari lantai (m)")
    ap.add_argument("--ransac-m", type=float, default=1.0, help="ambang inlier Sim3 (m)")
    ap.add_argument("--wrong-m", type=float, default=SALAH_M, help="galat 'salah yakin' (m)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not (a.results and a.points):
        ap.error("butuh results dan points, atau --self-test")

    rows, inliers, dirs = read_results(a.results)
    out, summary, sim = evaluate(rows, read_gt(a.points), a.height, a.ransac_m, a.wrong_m, dirs)
    if sim is not None:
        align = {
            "meter_from_model": {
                "scale": float(sim.scale),
                "rotation_xyzw": sim.rotation.quat.tolist(),
                "translation": sim.translation.tolist(),
            },
            "phone_height_m": a.height,
            "reference_points": summary["reference_points_used"],
            "residual_median_m": summary["residual_median_m"],
        }
        # results.csv -> align.json, results-covis.csv -> align-covis.json
        dst_align = a.results.with_name(a.results.stem.replace("results", "align") + ".json")
        dst_align.write_text(json.dumps(align, indent=2), encoding="utf-8")
    for r in out:
        # untuk memilih ambang inlier: foto salah yakin dengan inlier tinggi = ambang saja tak cukup
        r["inliers"] = inliers[r["query"]]
    dst = a.results.with_name(a.results.name.replace("results", "errors_m"))
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["query", "point", "error_m", "heading_err_deg", "inliers"]
        )
        w.writeheader()
        w.writerows(out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
