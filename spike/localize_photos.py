"""Lokalisasi satu folder foto lewat layanan /localize; tulis results.csv seperti spike/run.py.

Untuk foto titik acuan (P07_xp.jpg, ...) terhadap peta yang SUDAH dilayani, tanpa membangun ulang
peta. Hasilnya langsung dibaca spike/eval_meter.py (posisi meter, arah hadap, dan align.json).
Foto di bawah ambang inlier layanan tercatat gagal, sama seperti yang dialami aplikasi.

    python spike/localize_photos.py data/lab10/query-pagi --out outputs/lab10/pagi/results.csv
    python spike/eval_meter.py outputs/lab10/pagi/results.csv data/lab10/reference_points.csv

Token Cloudflare Access dari env CF_ACCESS_CLIENT_ID dan CF_ACCESS_CLIENT_SECRET; alamat dari
EUTOPOS_URL (bawaan https://eutopos.rockhead07.tech). Intrinsik diambil layanan dari EXIF foto.
"""

import argparse
import csv
import json
import os
from pathlib import Path

import httpx

COLUMNS = [
    "query",
    "ok",
    "inliers",
    "correspondences",
    "t_pose_s",
    "center_xyz_model",
    "view_dir_model",
]


def view_dir(q_xyzw) -> list[float]:
    """Sumbu optik kamera (z) di kerangka peta dari rotasi world_from_cam (x, y, z, w)."""
    x, y, z, w = q_xyzw
    return [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)]


def row(query: str, status: int, body: dict | None) -> dict:
    if 300 <= status < 400:
        raise SystemExit(f"{query}: HTTP {status} dari Access, token tidak ada atau salah")
    b = body if status == 200 and body else {}
    pose = b.get("pose_model")
    ok = b.get("status") == "ok" and pose is not None
    center = json.dumps([float(v) for v in pose["position"]]) if ok else ""
    view = json.dumps([float(v) for v in view_dir(pose["rotation_xyzw"])]) if ok else ""
    return {
        "query": query,
        "ok": ok,
        "inliers": b.get("inliers", 0),
        "correspondences": b.get("correspondences", 0),
        "t_pose_s": (b.get("t_s") or {}).get("total", ""),
        "center_xyz_model": center,
        "view_dir_model": view,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photos", type=Path, help="folder berisi foto JPEG")
    ap.add_argument("--out", type=Path, required=True, help="results.csv yang ditulis")
    a = ap.parse_args()
    url = os.environ.get("EUTOPOS_URL", "https://eutopos.rockhead07.tech").rstrip("/") + "/localize"
    headers = {
        "CF-Access-Client-Id": os.environ.get("CF_ACCESS_CLIENT_ID", ""),
        "CF-Access-Client-Secret": os.environ.get("CF_ACCESS_CLIENT_SECRET", ""),
    }
    photos = sorted(p for p in a.photos.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))
    if not photos:
        raise SystemExit(f"tidak ada foto JPEG di {a.photos}")
    rows = []
    with httpx.Client(headers=headers, timeout=60, follow_redirects=False) as client:
        for p in photos:
            resp = client.post(url, files={"image": (p.name, p.read_bytes(), "image/jpeg")})
            try:
                body = resp.json()
            except ValueError:
                body = None
            r = row(p.name, resp.status_code, body)
            rows.append(r)
            state = "ok" if r["ok"] else "gagal"
            print(f"{p.name}: HTTP {resp.status_code}, {state}, {r['inliers']} inlier")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"{a.out}: {sum(r['ok'] for r in rows)} dari {len(rows)} foto terlokalisasi")


if __name__ == "__main__":
    main()
