"""Ubah hasil lokalisasi (satuan model SfM) ke meter dan hitung galat terhadap titik acuan.

Foto uji diambil sambil berdiri di atas titik lantai yang sudah diukur. Nama foto diawali ID titik:
    query/P07_a.jpg, query/P07_b.jpg  ->  titik P07

Titik acuan (CSV, meter, relatif terhadap satu titik asal di koridor):
    titik,x_m,y_m
    P01,0.00,0.40

Penyelarasan model ke meter memakai Sim3 (skala, rotasi, translasi) dari pusat kamera foto uji ke
titik acuan. Skema leave-one-out: galat tiap titik dihitung dari Sim3 yang ditaksir TANPA titik itu,
jadi tidak ada titik yang menilai dirinya sendiri. Foto yang gagal dilokalisasi dihitung gagal.

Salah yakin: foto yang DIANGGAP berhasil oleh pipeline (ada pose) tapi galatnya > --salah-m. Untuk
navigasi ini lebih berbahaya daripada gagal: aplikasi tidak tahu harus mencoba lagi.

Contoh:
    python spike/eval_meter.py outputs/lantai10/kp1024-r1024/results.csv data/lantai10/titik.csv
    python spike/eval_meter.py --self-test
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import pycolmap

AMBANG_M = 1.0  # pertanyaan spike: galat <= 1,0 m pada >= 70% foto uji
SALAH_M = 3.0  # bawaan --salah-m: kira-kira sudah di depan pintu atau lorong yang salah


def point_id(query: str) -> str:
    return Path(query).stem.split("_")[0]


def fit(src, tgt, ransac_m):
    """Sim3 tgt_from_src dengan LO-RANSAC; None kalau gagal."""
    opts = pycolmap.RANSACOptions()
    opts.max_error = ransac_m
    ret = pycolmap.estimate_sim3d_robust(src, tgt, opts)
    return ret["tgt_from_src"] if ret else None


def evaluate(rows, gt, height_m, ransac_m, salah_m=SALAH_M):
    """rows: dict query -> pusat kamera (xyz model) atau None. gt: dict titik -> (x_m, y_m)."""
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
        err = None
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
        out.append({"query": q, "titik": point_id(q), "galat_m": err})

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

    errs = [r["galat_m"] for r in out]
    ok = [e for e in errs if e is not None]
    n_salah = sum(e > salah_m for e in ok)
    summary = {
        "foto_uji": len(errs),
        "foto_dengan_galat": len(ok),
        "titik_acuan_terpakai": len(pts),
        "sebaran_titik": round(spread, 3),
        "median_galat_m": round(float(np.median(ok)), 3) if ok else None,
        "p90_galat_m": round(float(np.percentile(ok, 90)), 3) if ok else None,
        # RMSE dan persen <= 2 m: sejajar dengan pelaporan Kim & Shin (2025)
        "rmse_galat_m": round(float(np.sqrt(np.mean(np.square(ok)))), 3) if ok else None,
        # yang gagal dilokalisasi atau gagal diselaraskan dihitung melewati ambang
        f"persen_foto_le_{AMBANG_M}m": round(100 * sum(e <= AMBANG_M for e in ok) / len(errs), 1),
        "persen_foto_le_2.0m": round(100 * sum(e <= 2.0 for e in ok) / len(errs), 1),
        f"persen_salah_yakin_gt_{salah_m}m": round(100 * n_salah / len(errs), 1),
        "sisa_median_m": round(float(np.median(sisa)), 3) if sisa is not None else None,
        "sisa_maks_m": round(float(sisa.max()), 3) if sisa is not None else None,
        "sisa_terbesar": names[int(sisa.argmax())] if sisa is not None else None,
    }
    if spread < 0.05:
        summary["peringatan"] = "titik acuan hampir segaris; penyelarasan tidak stabil"
    return out, summary, sim_all


def read_results(path: Path):
    """-> (query -> pusat kamera atau None, query -> jumlah inlier)."""
    rows, inliers = {}, {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ok = r["ok"] == "True" and r["center_xyz_model"]
            rows[r["query"]] = json.loads(r["center_xyz_model"]) if ok else None
            inliers[r["query"]] = int(r["inliers"])
    return rows, inliers


def read_gt(path: Path):
    with open(path, encoding="utf-8") as f:
        return {r["titik"]: (float(r["x_m"]), float(r["y_m"])) for r in csv.DictReader(f)}


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
    assert s["foto_uji"] == 24 and s["foto_dengan_galat"] == 23, s
    assert s["median_galat_m"] < 0.15, s
    assert s["persen_foto_le_1.0m"] == round(100 * 22 / 24, 1), s  # 2 gagal dari 24
    assert s["persen_foto_le_2.0m"] == s["persen_foto_le_1.0m"], s
    assert s["persen_salah_yakin_gt_3.0m"] == round(100 * 1 / 24, 1), s  # hanya P05_b
    assert s["rmse_galat_m"] > 10 * s["median_galat_m"], s  # RMSE peka pada satu salah besar
    assert s["sisa_median_m"] < 0.1, s  # derau 5 cm
    assert s["sisa_terbesar"] == "query/P05_b.jpg", s  # outlier tertangkap
    assert abs(sim.scale - 4.0) < 0.05, sim  # Sim3 semua titik = kebalikan model_from_world
    line = {f"L{i}": (i * 1.0, 0.0) for i in range(5)}
    _, s2, _ = evaluate({f"q/L{i}_a.jpg": [i, 0, 0] for i in range(5)}, line, 1.3, 1.0)
    assert "peringatan" in s2, s2
    print("self-test OK", json.dumps(s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path, nargs="?", help="results.csv dari spike/run.py")
    ap.add_argument("titik", type=Path, nargs="?", help="CSV titik acuan: titik,x_m,y_m")
    ap.add_argument("--tinggi", type=float, default=1.3, help="tinggi ponsel dari lantai (m)")
    ap.add_argument("--ransac-m", type=float, default=1.0, help="ambang inlier Sim3 (m)")
    ap.add_argument("--salah-m", type=float, default=SALAH_M, help="galat 'salah yakin' (m)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not (a.results and a.titik):
        ap.error("butuh results dan titik, atau --self-test")

    rows, inliers = read_results(a.results)
    out, summary, sim = evaluate(rows, read_gt(a.titik), a.tinggi, a.ransac_m, a.salah_m)
    if sim is not None:
        align = {
            "meter_from_model": {
                "skala": float(sim.scale),
                "rotasi_xyzw": sim.rotation.quat.tolist(),
                "translasi": sim.translation.tolist(),
            },
            "tinggi_ponsel_m": a.tinggi,
            "titik_acuan": summary["titik_acuan_terpakai"],
            "sisa_median_m": summary["sisa_median_m"],
        }
        # results.csv -> align.json, results-covis.csv -> align-covis.json
        dst_align = a.results.with_name(a.results.stem.replace("results", "align") + ".json")
        dst_align.write_text(json.dumps(align, indent=2), encoding="utf-8")
    for r in out:
        # untuk memilih ambang inlier: foto salah yakin dengan inlier tinggi = ambang saja tak cukup
        r["inliers"] = inliers[r["query"]]
    dst = a.results.with_name(a.results.name.replace("results", "galat_meter"))
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["query", "titik", "galat_m", "inliers"])
        w.writeheader()
        w.writerows(out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
