"""Unggah video ke eutopos lewat protokol tus, tanpa browser (stdlib saja).

Dipakai untuk menguji alur unggah di PC lab sebelum dashboard ada, dan untuk mengunggah dari skrip.
Potongan bawaan 50 MiB: di bawah batas 100 MB per permintaan Cloudflare Free.

    python -m server.upload_client floor10 "Lantai 10" peta:/data/inbox/loop.mp4 \
        --api http://api:8000 --tus http://tusd:8080/files/
"""

import argparse
import base64
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

TUS = {"Tus-Resumable": "1.0.0"}


def _request(method: str, url: str, headers: dict, data: bytes | None = None):
    token = os.environ.get("CF_ACCESS_TOKEN")  # opsional, lewat Tunnel nanti
    if token:
        headers = {**headers, "Cf-Access-Jwt-Assertion": token}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    return urllib.request.urlopen(req, timeout=300)


def _meta(**fields) -> str:
    return ",".join(f"{k} {base64.b64encode(v.encode()).decode()}" for k, v in fields.items())


def upload(path: Path, tus_url: str, job_id: int, chunk: int) -> None:
    size = path.stat().st_size
    headers = {**TUS, "Upload-Length": str(size)}
    headers["Upload-Metadata"] = _meta(job_id=str(job_id), name=path.name)
    with _request("POST", tus_url, headers) as r:
        location = urllib.parse.urljoin(tus_url, r.headers["Location"])
    offset = 0
    with path.open("rb") as f:
        while offset < size:
            data = f.read(chunk)
            headers = {**TUS, "Upload-Offset": str(offset)}
            headers["Content-Type"] = "application/offset+octet-stream"
            with _request("PATCH", location, headers, data) as r:
                offset = int(r.headers["Upload-Offset"])
            print(f"{path.name}: {offset * 100 // size}%", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("area_id")
    ap.add_argument("area_name")
    ap.add_argument("videos", nargs="+", help="peran:path, misalnya peta:/data/inbox/loop.mp4")
    ap.add_argument("--api", default="http://api:8000")
    ap.add_argument("--tus", default="http://tusd:8080/files/")
    ap.add_argument("--chunk-mb", type=int, default=50)
    a = ap.parse_args()
    items = [(role, Path(p)) for role, p in (v.split(":", 1) for v in a.videos)]
    body = {
        "area_id": a.area_id,
        "area_name": a.area_name,
        "videos": [{"name": p.name, "role": r, "size": p.stat().st_size} for r, p in items],
    }
    headers = {"Content-Type": "application/json"}
    with _request("POST", f"{a.api}/api/jobs", headers, json.dumps(body).encode()) as r:
        job = json.load(r)
    print(f"pekerjaan {job['id']} dibuat", flush=True)
    for _, p in items:
        upload(p, a.tus, job["id"], a.chunk_mb * 1024 * 1024)
    with _request("GET", f"{a.api}/api/jobs/{job['id']}", {}) as r:
        print(f"status pekerjaan {job['id']}: {json.load(r)['status']}")


if __name__ == "__main__":
    main()
