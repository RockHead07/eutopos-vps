"""Ukur pemakaian CPU dan GPU tiap konfigurasi fitur + pencocok, bersih dan dengan noise.

Dibuat atas permintaan pembimbing (7 Okt 2026): bandingkan pemakaian GPU dan CPU tiap konfigurasi,
dengan sekitar 30 gambar yang beragam, termasuk gambar ber-noise buatan OpenCV.

Tiga langkah (jalankan di tempat yang punya hloc, misalnya container worker):
    python spike/bench_usage.py prepare --frames data/floor10/mapping --out outputs/usage
    python spike/bench_usage.py run --out outputs/usage --devices gpu cpu --repeats 3
    python spike/bench_usage.py report --out outputs/usage

Yang diukur per tahap (ekstraksi fitur, pencocokan): waktu dinding, waktu CPU proses (dibagi waktu
dinding = rata-rata inti terpakai), RSS, VRAM puncak (torch), utilisasi GPU (cuplikan nvidia-smi).
Kualitas: keypoint per gambar, match per pasangan, dan inlier setelah verifikasi geometri RANSAC.

Batas yang dicatat apa adanya, bukan disembunyikan:
- Ekstraksi SIFT hanya jalan di CPU selama pycolmap tidak dibangun dengan CUDA (pycolmap.has_cuda).
- Waktu tahap sudah termasuk memuat model, karena hloc memuatnya di setiap panggilan main().
- GPU dipakai bersama layanan api yang sedang diam. Utilisasi diam dicatat sebagai pembanding.
"""

import argparse
import csv
import json
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from extract_frames import sharpness

try:
    import resource  # hanya Linux dan macOS
except ImportError:
    resource = None

# (fitur, pencocok, batas keypoint, sisi terpanjang gambar). Lima baris yang sama dengan hasil uji
# lorong lantai 10 (docs/sift-vs-aliked.md); sift-colmap-default = setelan bawaan COLMAP.
CONFIGS = {
    "aliked-lightglue": ("aliked", "lightglue", 1024, 1024),
    "sift-lightglue": ("sift", "lightglue", 1024, 1024),
    "aliked-nn": ("aliked", "nn-ratio", 1024, 1024),
    "sift-nn": ("sift", "nn-ratio", 1024, 1024),
    "sift-colmap-default": ("sift", "nn-ratio", 8192, 2560),
}
# Noise buatan OpenCV. Tingkatnya ditetapkan di sini sebelum ada hasil, bukan disetel sesudahnya.
VARIANTS = {
    "clean": None,
    "gauss10": ("gauss", 10),
    "gauss25": ("gauss", 25),
    "gauss50": ("gauss", 50),
    "sp2": ("sp", 0.02),
}
OPTIONAL = (
    "gpu_util_mean",
    "gpu_util_max",
    "vram_peak_mb",
    "rss_mb",
    "keypoints_mean",
    "matches_mean",
    "inliers_mean",
    "inlier_ratio",
)
SMI_FALLBACK = "/usr/lib/wsl/lib/nvidia-smi"  # di WSL2 tidak ada di PATH


# ---- pemilihan gambar --------------------------------------------------------------------------


def video_of(name: str) -> str:
    return re.sub(r"_\d+$", "", Path(name).stem)  # nama frame: <video>_<nomor>.jpg


def select_pairs(names, variances, n_pairs, gap, seed):
    """Pilih n_pairs pasangan frame berjarak `gap` frame di video yang sama.

    Tersebar di sepanjang rute (satu pasangan per irisan) dan di rentang ketajaman, dari buram
    sampai tajam: tiap target kuantil ketajaman diambil dari irisan rute yang belum terpakai.
    Hasil tetap untuk seed yang sama. Frame diekstrak 2 fps, jadi gap 2 = sekitar 1 detik.
    """
    by_video: dict[str, list[str]] = {}
    for n in sorted(names):
        by_video.setdefault(video_of(n), []).append(n)
    cands = [
        (f[i], f[i + gap])
        for v in sorted(by_video)
        for f in [by_video[v]]
        for i in range(len(f) - gap)
    ]
    if len(cands) < n_pairs:
        raise ValueError(f"only {len(cands)} candidate pairs, need {n_pairs}")
    size = len(cands)
    bins = [range(-(-size * k // n_pairs), -(-size * (k + 1) // n_pairs)) for k in range(n_pairs)]
    values = [variances[a] for a, _ in cands]
    quantiles = [k / (n_pairs - 1) if n_pairs > 1 else 0.5 for k in range(n_pairs)]
    targets = [float(np.quantile(values, q)) for q in quantiles]
    # Dua ujung (paling buram dan paling tajam) dulu supaya pasti terambil, sisanya urutannya
    # diacak oleh seed.
    rest = list(range(1, n_pairs - 1))
    random.Random(seed).shuffle(rest)
    order = [0, n_pairs - 1, *rest] if n_pairs > 1 else [0]
    free = set(range(n_pairs))
    chosen: dict[int, int] = {}
    for t in order:
        best = min(
            ((abs(values[i] - targets[t]), i, j) for j in free for i in bins[j]),
            key=lambda x: (x[0], x[1]),
        )
        chosen[best[2]] = best[1]
        free.discard(best[2])
    return [cands[chosen[j]] for j in sorted(chosen)]


def frame_variances(folder: Path, names) -> dict[str, float]:
    out = {}
    for n in names:
        img = cv2.imread(str(folder / n))
        if img is None:
            raise SystemExit(f"gambar tidak terbaca: {folder / n}")
        out[n] = sharpness(img)
    return out


# ---- noise dari OpenCV -------------------------------------------------------------------------


def gaussian_noise(img, sigma, seed):
    cv2.setRNGSeed(seed)
    noise = np.zeros(img.shape, np.int16)
    cv2.randn(noise, (0, 0, 0), (sigma, sigma, sigma))
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def salt_pepper(img, amount, seed):
    """Sebagian `amount` piksel menjadi hitam atau putih, sama banyak."""
    cv2.setRNGSeed(seed)
    u = np.zeros(img.shape[:2], np.float32)
    cv2.randu(u, 0.0, 1.0)
    out = img.copy()
    out[u < amount / 2] = 0
    out[u > 1 - amount / 2] = 255
    return out


def make_variant(img, name, seed):
    spec = VARIANTS[name]
    if spec is None:
        return img.copy()
    kind, level = spec
    return gaussian_noise(img, level, seed) if kind == "gauss" else salt_pepper(img, level, seed)


# ---- sampler GPU dan agregasi ------------------------------------------------------------------


def parse_smi_line(line: str):
    """'37, 2288' -> (utilisasi %, memori MiB). None kalau bukan angka (misalnya [N/A])."""
    try:
        util, mem = (float(x) for x in line.split(","))
    except ValueError:
        return None
    return util, mem


def window_stats(samples, t0, t1):
    """Rata-rata dan puncak utilisasi dari cuplikan (t, util) di dalam [t0, t1]."""
    inside = [u for t, u in samples if t0 <= t <= t1]
    return (statistics.mean(inside), max(inside)) if inside else (None, None)


class GpuSampler:
    """Cuplik utilisasi GPU tiap 200 ms lewat nvidia-smi. Tanpa nvidia-smi: tidak tersedia."""

    def __init__(self):
        exe = shutil.which("nvidia-smi") or (SMI_FALLBACK if Path(SMI_FALLBACK).exists() else None)
        self.samples: list[tuple[float, float]] = []
        self.proc = None
        if exe:
            cmd = [exe, "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"]
            self.proc = subprocess.Popen(
                [*cmd, "-lms", "200"], stdout=subprocess.PIPE, text=True, stderr=subprocess.DEVNULL
            )
            threading.Thread(target=self._read, daemon=True).start()

    @property
    def available(self) -> bool:
        return self.proc is not None

    def _read(self):
        for line in self.proc.stdout:
            parsed = parse_smi_line(line)
            if parsed:
                self.samples.append((time.perf_counter(), parsed[0]))

    def stop(self):
        if self.proc:
            self.proc.terminate()


def aggregate(records):
    """Median dan rentang per (konfigurasi, perangkat, variasi, tahap) atas ulangan."""
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        groups.setdefault((r["config"], r["device"], r["variant"], r["stage"]), []).append(r)
    rows = []
    for (config, device, variant, stage), g in groups.items():
        wall = [r["wall_s"] for r in g]
        row = {
            "config": config,
            "device": device,
            "variant": variant,
            "stage": stage,
            "repeats": len(g),
            "wall_s": statistics.median(wall),
            "wall_min": min(wall),
            "wall_max": max(wall),
            "cpu_s": statistics.median(r["cpu_s"] for r in g),
            "cpu_cores": statistics.median(r["cpu_s"] / r["wall_s"] for r in g),
            "items": g[0].get("items"),
            "per_item_s": statistics.median(r["wall_s"] / r["items"] for r in g)
            if all(r.get("items") for r in g)
            else None,
        }
        for key in OPTIONAL:
            vals = [r[key] for r in g if r.get(key) is not None]
            row[key] = statistics.median(vals) if vals else None
        rows.append(row)
    return rows


# ---- konfigurasi hloc (mengikuti spike/run.py) -------------------------------------------------


def build_confs(features, matcher, max_kp, resize):
    """Konfigurasi ekstraktor dan pencocok persis seperti spike/run.py membuatnya."""
    from run import FEATURES, MATCHERS

    local, match = FEATURES[features]
    if matcher == "lightglue":
        match = MATCHERS["lightglue"][f"lightglue-{features}"]
    else:
        match = MATCHERS[matcher]
    model = dict(local["model"])
    if features == "sift":
        model["options"] = {"max_num_features": max_kp if max_kp > 0 else 8192}
    else:
        model["max_num_keypoints"] = max_kp
    local = {
        **local,
        "model": model,
        "preprocessing": {**local["preprocessing"], "resize_max": resize},
    }
    return local, match


# ---- langkah prepare ---------------------------------------------------------------------------


def prepare(a):
    names = sorted(
        p.name for p in a.frames.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    pairs = select_pairs(names, frame_variances(a.frames, names), a.pairs, a.gap, a.seed)
    var = frame_variances(a.frames, sorted({x for p in pairs for x in p}))
    manifest = {
        "frames": str(a.frames),
        "gap": a.gap,
        "seed": a.seed,
        "variants": VARIANTS,
        "pairs": [
            {"id": f"p{i:02d}", "a": x, "b": y, "sharpness_a": round(var[x], 1)}
            for i, (x, y) in enumerate(pairs)
        ],
    }
    (a.out / "pairs").mkdir(parents=True, exist_ok=True)
    for vi, variant in enumerate(VARIANTS):
        folder = a.out / "images" / variant
        folder.mkdir(parents=True, exist_ok=True)
        lines = []
        for pi, p in enumerate(manifest["pairs"]):
            for side, key in enumerate(("a", "b")):
                img = cv2.imread(str(a.frames / p[key]))
                seed = a.seed * 100_000 + vi * 1_000 + pi * 2 + side
                out = make_variant(img, variant, seed)
                cv2.imwrite(
                    str(folder / f"{p['id']}_{key}.jpg"), out, [cv2.IMWRITE_JPEG_QUALITY, 95]
                )
            lines.append(f"{variant}/{p['id']}_a.jpg {variant}/{p['id']}_b.jpg")
        (a.out / "pairs" / f"{variant}.txt").write_text("\n".join(lines), encoding="utf-8")
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    rng = [p["sharpness_a"] for p in manifest["pairs"]]
    span = f"ketajaman {min(rng):.0f} sampai {max(rng):.0f}"
    print(f"{len(pairs)} pasangan, {span}, {len(VARIANTS)} variasi")


# ---- langkah run (satu proses anak per konfigurasi dan perangkat) ------------------------------


def cpu_seconds() -> float:
    """Waktu CPU proses ini ditambah proses anak yang sudah selesai (user + sys).

    hloc memuat gambar di pekerja DataLoader yang terpisah. Tanpa menghitungnya, pemakaian CPU
    ekstraksi terlihat jauh lebih kecil dari sebenarnya. Di Windows tidak ada modul resource,
    jadi hanya proses ini (meta mencatatnya di cpu_includes_children).
    """
    total = time.process_time()
    if resource is not None:
        ru = resource.getrusage(resource.RUSAGE_CHILDREN)
        total += ru.ru_utime + ru.ru_stime
    return total


def rss_mb():
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except OSError:
        pass
    return None


def measure(fn, cuda, sampler):
    import torch

    if cuda:
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    c0, t0 = cpu_seconds(), time.perf_counter()
    fn()
    if cuda:
        torch.cuda.synchronize()
    t1, c1 = time.perf_counter(), cpu_seconds()
    util = window_stats(sampler.samples, t0, t1) if cuda and sampler.available else (None, None)
    return {
        "wall_s": t1 - t0,
        "cpu_s": c1 - c0,
        "rss_mb": rss_mb(),
        "vram_peak_mb": torch.cuda.max_memory_allocated() / 2**20 if cuda else None,
        "gpu_util_mean": util[0],
        "gpu_util_max": util[1],
    }


def quality(fp, mp, manifest, variant):
    from hloc.utils import io

    n_kp, n_match, n_inl = [], [], []
    for p in manifest["pairs"]:
        a, b = f"{variant}/{p['id']}_a.jpg", f"{variant}/{p['id']}_b.jpg"
        k0, k1 = io.get_keypoints(fp, a), io.get_keypoints(fp, b)
        n_kp += [len(k0), len(k1)]
        m = io.get_matches(mp, a, b)[0]
        n_match.append(len(m))
        inl = 0
        if len(m) >= 8:
            _, mask = cv2.findFundamentalMat(k0[m[:, 0]], k1[m[:, 1]], cv2.FM_RANSAC, 1.0, 0.999)
            inl = int(mask.sum()) if mask is not None else 0
        n_inl.append(inl)
    total = sum(n_match)
    return {
        "keypoints_mean": statistics.mean(n_kp),
        "matches_mean": statistics.mean(n_match),
        "inliers_mean": statistics.mean(n_inl),
        "inlier_ratio": sum(n_inl) / total if total else None,
    }


def child(a):
    import pycolmap
    import torch
    from hloc import extract_features, match_features

    cuda = torch.cuda.is_available()
    if a.device == "gpu" and not cuda:
        print(f"{a.config} gpu: dilewati, CUDA tidak tersedia")
        sys.exit(3)
    if a.device == "cpu" and cuda:
        raise SystemExit("run CPU tapi CUDA terlihat: proses induk harus menyembunyikan GPU")
    features, matcher, max_kp, resize = CONFIGS[a.config]
    local, match_conf = build_confs(features, matcher, max_kp, resize)
    if features == "sift" and matcher == "lightglue":
        from run import sift_orientations_in_radians

        sift_orientations_in_radians()
    manifest = json.loads((a.out / "manifest.json").read_text(encoding="utf-8"))
    images = a.out / "images"
    work = a.out / "work" / f"{a.config}-{a.device}"
    work.mkdir(parents=True, exist_ok=True)
    results = a.out / "results"
    results.mkdir(exist_ok=True)
    log = results / f"{a.config}-{a.device}.jsonl"
    log.unlink(missing_ok=True)

    sampler = GpuSampler() if cuda else None
    idle = None
    if sampler and sampler.available:
        time.sleep(2)
        idle = window_stats(sampler.samples, 0, time.perf_counter())[0]
    meta = {
        "type": "meta",
        "config": a.config,
        "device": a.device,
        "torch": torch.__version__,
        "torch_threads": torch.get_num_threads(),
        "cuda_visible": cuda,
        "pycolmap_has_cuda": pycolmap.has_cuda,
        "extract_device": "cpu" if features == "sift" and not pycolmap.has_cuda else a.device,
        "cpu_includes_children": resource is not None,
        "gpu_idle_util_mean": idle,
        "gpu_util_available": bool(sampler and sampler.available),
    }
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(meta) + "\n")

    def one_run(variant, rep, record):
        names = [f"{variant}/{p['id']}_{k}.jpg" for p in manifest["pairs"] for k in ("a", "b")]
        pairs_txt = a.out / "pairs" / f"{variant}.txt"
        fp, mp = work / f"f-{variant}-{rep}.h5", work / f"m-{variant}-{rep}.h5"
        n_images, n_pairs = len(names), len(manifest["pairs"])
        ext = measure(
            lambda: extract_features.main(
                local, images, image_list=names, feature_path=fp, overwrite=True
            ),
            cuda,
            sampler,
        )
        mat = measure(
            lambda: match_features.main(
                match_conf, pairs_txt, features=fp, matches=mp, overwrite=True
            ),
            cuda,
            sampler,
        )
        if record:
            q = quality(fp, mp, manifest, variant)
            base = {"type": "run", "config": a.config, "device": a.device, "variant": variant}
            rows = [
                {**base, "stage": "extract", "repeat": rep, "items": n_images, **ext}
                | {"keypoints_mean": q["keypoints_mean"]},
                {**base, "stage": "match", "repeat": rep, "items": n_pairs, **mat}
                | {k: q[k] for k in q if k != "keypoints_mean"},
            ]
            with open(log, "a", encoding="utf-8") as f:
                f.writelines(json.dumps(r) + "\n" for r in rows)
        fp.unlink(missing_ok=True)
        mp.unlink(missing_ok=True)

    one_run("clean", -1, record=False)  # pemanasan (kernel CUDA, cache berkas), tidak dicatat
    for variant in a.variants:
        for rep in range(a.repeats):
            one_run(variant, rep, record=True)
            print(f"{a.config} {a.device} {variant} ulangan {rep + 1}/{a.repeats}", flush=True)
    if sampler:
        sampler.stop()


def run(a):
    if not (a.out / "manifest.json").exists():
        raise SystemExit("jalankan 'prepare' dulu")
    for config in a.configs:
        for device in a.devices:
            env = os.environ.copy()
            if device == "cpu":
                env["CUDA_VISIBLE_DEVICES"] = ""  # sembunyikan GPU dari torch di proses anak
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "child",
                "--out",
                str(a.out),
                "--config",
                config,
                "--device",
                device,
                "--repeats",
                str(a.repeats),
                "--variants",
                *a.variants,
            ]
            rc = subprocess.run(cmd, env=env).returncode
            status = {0: "selesai", 3: "dilewati"}.get(rc, f"GAGAL ({rc})")
            print(f"== {config} {device}: {status}")
            if rc not in (0, 3):
                raise SystemExit(rc)


# ---- langkah report ----------------------------------------------------------------------------


def fmt(v, digits=1):
    return "-" if v is None else f"{v:.{digits}f}"


def report(a):
    records, metas = [], []
    for f in sorted((a.out / "results").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            (records if r["type"] == "run" else metas).append(r)
    rows = aggregate(records)
    cols = list(rows[0]) if rows else []
    with open(a.out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    lines = ["## Pemakaian sumber daya, gambar bersih (median atas ulangan)", ""]
    lines.append(
        "| Konfigurasi | Perangkat | Tahap | Total (s) | Per item (s) | Inti CPU rata2 | "
        "GPU % rata2 | VRAM puncak MB |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in (x for x in rows if x["variant"] == "clean"):
        lines.append(
            f"| {r['config']} | {r['device']} | {r['stage']} | {fmt(r['wall_s'], 2)} | "
            f"{fmt(r['per_item_s'], 2)} | {fmt(r['cpu_cores'])} | {fmt(r['gpu_util_mean'], 0)} | "
            f"{fmt(r['vram_peak_mb'], 0)} |"
        )
    lines += ["", "## Kualitas pencocokan per variasi noise (inlier rata2 per pasangan)", ""]
    lines.append("| Konfigurasi | " + " | ".join(VARIANTS) + " |")
    lines.append("|---|" + "---|" * len(VARIANTS))
    by = {(r["config"], r["variant"]): r for r in rows if r["stage"] == "match"}
    for config in dict.fromkeys(r["config"] for r in rows):
        cells = [
            fmt(by[(config, v)]["inliers_mean"], 0) if (config, v) in by else "-" for v in VARIANTS
        ]
        lines.append(f"| {config} | " + " | ".join(cells) + " |")
    lines += ["", "## Catatan lingkungan", ""]
    for m in metas:
        lines.append(
            f"- {m['config']} {m['device']}: torch {m['torch']}, {m['torch_threads']} thread, "
            f"ekstraksi di {m['extract_device']}, pycolmap CUDA {m['pycolmap_has_cuda']}, "
            f"CPU proses anak {'dihitung' if m['cpu_includes_children'] else 'TIDAK dihitung'}, "
            f"GPU diam {fmt(m['gpu_idle_util_mean'], 0)}%, sampler GPU "
            f"{'ada' if m['gpu_util_available'] else 'tidak ada'}"
        )
    (a.out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="pilih pasangan dan tulis gambar bersih dan ber-noise")
    p.add_argument("--frames", type=Path, required=True, help="folder frame peta (<video>_<n>.jpg)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pairs", type=int, default=15, help="15 pasangan = 30 gambar")
    p.add_argument("--gap", type=int, default=2, help="jarak frame dalam pasangan (2 = ~1 detik)")
    p.add_argument("--seed", type=int, default=7)
    r = sub.add_parser(
        "run", help="jalankan pengukuran, satu proses anak per konfigurasi dan perangkat"
    )
    c = sub.add_parser("child")
    for x in (r, c):
        x.add_argument("--out", type=Path, required=True)
        x.add_argument("--repeats", type=int, default=3)
        x.add_argument("--variants", nargs="+", choices=list(VARIANTS), default=list(VARIANTS))
    r.add_argument("--configs", nargs="+", choices=list(CONFIGS), default=list(CONFIGS))
    r.add_argument("--devices", nargs="+", choices=["gpu", "cpu"], default=["gpu", "cpu"])
    c.add_argument("--config", choices=list(CONFIGS), required=True)
    c.add_argument("--device", choices=["gpu", "cpu"], required=True)
    rep = sub.add_parser("report", help="ringkas hasil menjadi summary.csv dan summary.md")
    rep.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    {"prepare": prepare, "run": run, "child": child, "report": report}[a.cmd](a)


if __name__ == "__main__":
    main()
