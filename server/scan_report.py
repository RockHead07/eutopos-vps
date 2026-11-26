"""Penyusun kartu laporan scan per pekerjaan peta (spesifikasi 2026-11-25).

Fungsi di modul ini menyusun bagian recording, network, processing, dan quality dari data yang
sudah dibaca. Nilai yang tidak diketahui selalu None disertai `<kunci>_reason`, bukan 0 atau
tebakan.
"""

import json
import math
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

from server.db import MapJob

REPORT_VERSION = 1
FOOTPRINT = {"method": "trajectory_buffer", "radius_m": 1.0, "cell_m": 0.25}
MULTI_FLOOR_M = 2.5

_UNSET: Any = object()
_PARAM_KEYS = (
    "features",
    "matcher",
    "max_keypoints",
    "resize_max",
    "sequential_pairs",
    "detection_threshold",
)
_ALIGN_KEYS = ("status", "residual_median_m", "residual_max_m", "scale")


def _basename(name: str) -> str:
    return PurePosixPath(name.replace("\\", "/")).name


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def footprint_m2(polylines: list[np.ndarray], radius_m: float, cell_m: float) -> float:
    """Luas jejak lintasan (m2) dengan rasterisasi buffer radius_m pada grid cell_m.

    Tiap elemen polylines adalah array Nx2 (satu segmen); semua segmen dihitung bersama dalam
    satu grid sehingga tumpang tindih tidak terhitung ganda.
    """
    valid = []
    for poly in polylines:
        arr = np.asarray(poly, dtype=float)
        if arr.ndim == 2 and arr.shape[1] == 2 and len(arr) > 0:
            valid.append(arr)
    if not valid or radius_m < 0 or cell_m <= 0:
        return 0.0

    pts = np.vstack(valid)
    min_x = float(pts[:, 0].min()) - radius_m
    max_x = float(pts[:, 0].max()) + radius_m
    min_y = float(pts[:, 1].min()) - radius_m
    max_y = float(pts[:, 1].max()) + radius_m

    x0 = math.floor(min_x / cell_m) * cell_m + cell_m / 2
    x1 = math.ceil(max_x / cell_m) * cell_m
    y0 = math.floor(min_y / cell_m) * cell_m + cell_m / 2
    y1 = math.ceil(max_y / cell_m) * cell_m
    xs = np.arange(x0, x1, cell_m)
    ys = np.arange(y0, y1, cell_m)
    if len(xs) == 0 or len(ys) == 0:
        return 0.0

    gx, gy = np.meshgrid(xs, ys, indexing="xy")
    covered = np.zeros(gx.shape, dtype=bool)
    r2 = radius_m * radius_m

    for arr in valid:
        if len(arr) == 1:
            dx = gx - arr[0, 0]
            dy = gy - arr[0, 1]
            covered |= (dx * dx + dy * dy) <= r2
            continue
        for i in range(len(arr) - 1):
            ax, ay = float(arr[i, 0]), float(arr[i, 1])
            bx, by = float(arr[i + 1, 0]), float(arr[i + 1, 1])
            abx, aby = bx - ax, by - ay
            ab2 = abx * abx + aby * aby
            if ab2 == 0.0:
                dx = gx - ax
                dy = gy - ay
            else:
                t = ((gx - ax) * abx + (gy - ay) * aby) / ab2
                np.clip(t, 0.0, 1.0, out=t)
                dx = gx - (ax + t * abx)
                dy = gy - (ay + t * aby)
            covered |= (dx * dx + dy * dy) <= r2

    return float(int(covered.sum()) * cell_m * cell_m)


def _group_segments(frames: list[dict]) -> list[list[dict]]:
    by_seg: dict[Any, list[tuple[int, dict]]] = {}
    for index, frame in enumerate(frames):
        seg = frame.get("segment")
        seg_key = 0 if seg is None else seg
        by_seg.setdefault(seg_key, []).append((index, frame))

    ordered: list[list[dict]] = []
    for items in by_seg.values():
        items.sort(
            key=lambda item: (
                not _finite(item[1].get("t_ns")),
                item[1]["t_ns"] if _finite(item[1].get("t_ns")) else 0,
                item[0],
            )
        )
        ordered.append([frame for _, frame in items])
    return ordered


def _meta_fields(meta: dict | None) -> dict:
    out: dict[str, Any] = {}
    losses = meta.get("tracking_losses") if isinstance(meta, dict) else None
    if losses is not None:
        out["tracking_losses"] = losses
    else:
        out["tracking_losses"] = None
        out["tracking_losses_reason"] = "no_meta"

    model = meta.get("device_model") if isinstance(meta, dict) else None
    if isinstance(model, str) and model.strip():
        out["device_model"] = model
    else:
        out["device_model"] = None
        out["device_model_reason"] = "no_meta"
    return out


def recording(
    frames: list[dict] | None,
    meta: dict | None,
    aligned: dict[str, np.ndarray] | None,
    video_seconds: float | None,
    run: dict,
    *,
    source: str | None = _UNSET,
) -> dict:
    """Susun bagian recording dari frames ARCore atau metadata video."""
    run = run or {}
    if frames is None:
        src = (
            ("video" if (video_seconds is not None or run.get("map_images") is not None) else None)
            if source is _UNSET
            else source
        )
        out: dict[str, Any] = {
            "source": src,
            "map_photos": run.get("map_images"),
            "query_photos": run.get("queries"),
            "segments": None,
            "segments_reason": "no_arcore",
            "duration_s": float(video_seconds) if video_seconds is not None else None,
            "path_length_m": None,
            "path_length_m_reason": "no_arcore",
            "footprint_m2": None,
            "footprint_m2_reason": "no_arcore",
            "footprint": None,
            "mean_speed_m_s": None,
            "mean_speed_m_s_reason": "no_arcore",
            "tracking_losses": None,
            "tracking_losses_reason": "no_arcore",
            "device_model": None,
            "device_model_reason": "no_arcore",
            "height_range_m": None,
            "height_range_m_reason": "no_arcore",
            "warnings": [],
        }
        if video_seconds is None:
            out["duration_s_reason"] = "video_deleted"
        return out

    meta_out = _meta_fields(meta)
    if not frames:
        return {
            "source": "arcore",
            "map_photos": 0,
            "query_photos": run.get("queries"),
            "segments": 0,
            "duration_s": None,
            "duration_s_reason": "not_recorded",
            "path_length_m": None,
            "path_length_m_reason": "not_recorded",
            "footprint_m2": None,
            "footprint_m2_reason": "not_recorded",
            "footprint": {**FOOTPRINT, "frame": "arcore_per_segment"},
            "mean_speed_m_s": None,
            "mean_speed_m_s_reason": "not_recorded",
            **meta_out,
            "height_range_m": None,
            "height_range_m_reason": "not_recorded",
            "warnings": [],
        }

    ordered_segments = _group_segments(frames)
    seg_count = len(ordered_segments)

    # Durasi per segmen dari t_ns (jeda antarsegmen tidak dihitung).
    seg_durations: list[float] = []
    all_have_t = True
    for seg in ordered_segments:
        ts = [float(f["t_ns"]) for f in seg if _finite(f.get("t_ns"))]
        if not ts:
            all_have_t = False
            break
        seg_durations.append((max(ts) - min(ts)) / 1e9)
    duration_s = float(sum(seg_durations)) if all_have_t else None

    # Panjang lintasan horizontal (X, Z di ARCore Y-up) per segmen.
    path_length = 0.0
    for seg in ordered_segments:
        for a, b in pairwise(seg):
            pa, pb = a["position"], b["position"]
            path_length += math.hypot(float(pb[0]) - float(pa[0]), float(pb[2]) - float(pa[2]))

    matched_names = (
        {_basename(f["file"]) for f in frames if _basename(f["file"]) in aligned}
        if aligned
        else set()
    )
    radius_m, cell_m = FOOTPRINT["radius_m"], FOOTPRINT["cell_m"]
    upper_bound = False

    if aligned and len(matched_names) >= 2:
        frame_kind = "aligned_sfm"
        aligned_polys: list[np.ndarray] = []
        zs: list[float] = []
        for seg in ordered_segments:
            pts = [aligned[_basename(f["file"])] for f in seg if _basename(f["file"]) in aligned]
            if pts:
                arr = np.asarray(pts, dtype=float)
                aligned_polys.append(arr[:, :2])
                zs.extend(arr[:, 2].tolist())
        fp_m2 = footprint_m2(aligned_polys, radius_m, cell_m)
        height_range_m = float(max(zs) - min(zs))
    else:
        frame_kind = "arcore_per_segment"
        fp_m2 = 0.0
        seg_heights: list[float] = []
        for seg in ordered_segments:
            xz = np.array([[float(f["position"][0]), float(f["position"][2])] for f in seg], float)
            fp_m2 += footprint_m2([xz], radius_m, cell_m)
            ys = [float(f["position"][1]) for f in seg]
            seg_heights.append(max(ys) - min(ys))
        height_range_m = float(max(seg_heights))
        if seg_count > 1:
            upper_bound = True

    mean_speed = (path_length / duration_s) if (duration_s is not None and duration_s > 0) else None
    warnings = ["multi_floor"] if height_range_m > MULTI_FLOOR_M else []

    out = {
        "source": "arcore",
        "map_photos": len(frames),
        "query_photos": run.get("queries"),
        "segments": seg_count,
        "duration_s": duration_s,
        "path_length_m": float(path_length),
        "footprint_m2": float(fp_m2),
        "footprint": {**FOOTPRINT, "frame": frame_kind},
        "mean_speed_m_s": mean_speed,
        **meta_out,
        "height_range_m": height_range_m,
        "warnings": warnings,
    }
    if duration_s is None:
        out["duration_s_reason"] = "not_recorded"
        out["mean_speed_m_s_reason"] = "not_recorded"
    if upper_bound:
        out["footprint_upper_bound"] = True
    return out


def network(videos: list[dict]) -> dict:
    """Susun bagian network (throughput unggah efektif) dari daftar entri video job."""
    if not videos or all(v.get("size") is None for v in videos):
        return {
            "uploads": None,
            "uploads_reason": "cli_job",
            "total_bytes": None,
            "seconds": None,
            "mbps": None,
        }

    uploaded_videos = [v for v in videos if v.get("size") is not None]
    starts: list[datetime] = []
    ends: list[datetime] = []
    uploads_out: list[dict] = []
    for video in uploaded_videos:
        t0 = _parse_iso(video.get("upload_started_at"))
        t1 = _parse_iso(video.get("uploaded_at"))
        if t0 is None or t1 is None:
            return {
                "uploads": None,
                "uploads_reason": "not_recorded",
                "total_bytes": None,
                "seconds": None,
                "mbps": None,
            }
        starts.append(t0)
        ends.append(t1)
        size_bytes = int(video["size"])
        secs = (t1 - t0).total_seconds()
        mbps = (size_bytes * 8 / secs / 1e6) if secs > 0 else None
        uploads_out.append(
            {
                "role": video.get("role"),
                "kind": video.get("kind", "video"),
                "size_bytes": size_bytes,
                "seconds": secs,
                "mbps": mbps,
            }
        )

    total_bytes = sum(item["size_bytes"] for item in uploads_out)
    total_seconds = (max(ends) - min(starts)).total_seconds()
    total_mbps = (total_bytes * 8 / total_seconds / 1e6) if total_seconds > 0 else None
    return {
        "uploads": uploads_out,
        "total_bytes": total_bytes,
        "seconds": total_seconds,
        "mbps": total_mbps,
    }


def processing(job: MapJob, now: datetime | None, live: dict | None, run: dict) -> dict:
    """Susun bagian processing: waktu antre, tunggu GPU, total proses, dan rincian tahap."""
    run = run or {}
    live = live if isinstance(live, dict) else {}
    started_at = _as_utc(job.started_at)
    now_utc = _as_utc(now)

    out: dict[str, Any] = {}
    is_cli = not job.videos or all(v.get("size") is None for v in job.videos)
    if started_at is None:
        out["queue_s"] = None
        out["queue_s_reason"] = "not_recorded"
    elif is_cli:
        created_at = _as_utc(job.created_at)
        if created_at is not None:
            out["queue_s"] = (started_at - created_at).total_seconds()
        else:
            out["queue_s"] = None
            out["queue_s_reason"] = "not_recorded"
    else:
        uploaded_times = [
            _parse_iso(v.get("uploaded_at")) for v in job.videos if v.get("size") is not None
        ]
        if uploaded_times and all(t is not None for t in uploaded_times):
            last_uploaded = max(t for t in uploaded_times if t is not None)
            out["queue_s"] = (started_at - last_uploaded).total_seconds()
        else:
            out["queue_s"] = None
            out["queue_s_reason"] = "not_recorded"

    gpu_wait_s = live.get("gpu_wait_s")
    out["gpu_wait_s"] = gpu_wait_s
    if gpu_wait_s is None:
        out["gpu_wait_s_reason"] = "not_recorded"

    if started_at is not None and now_utc is not None:
        out["total_s"] = (now_utc - started_at).total_seconds()
    else:
        out["total_s"] = None
        out["total_s_reason"] = "not_recorded"

    stage_seconds = live.get("stage_seconds")
    if isinstance(stage_seconds, dict):
        out["stage_seconds"] = dict(stage_seconds)
    else:
        out["stage_seconds"] = None
        out["stage_seconds_reason"] = "not_recorded"

    t_map = run.get("t_map_s")
    out["map_stage_seconds"] = dict(t_map) if isinstance(t_map, dict) else None
    env = run.get("env")
    out["env"] = dict(env) if isinstance(env, dict) else None
    return out


def quality(summary: dict, model_stats: dict | None) -> dict:
    """Susun bagian quality dari ringkasan run/inspect/align/gate dan statistik model SfM."""
    summary = summary or {}
    run = summary.get("run") if isinstance(summary.get("run"), dict) else {}
    inspect = summary.get("inspect") if isinstance(summary.get("inspect"), dict) else {}
    align_in = summary.get("align") if isinstance(summary.get("align"), dict) else None
    gate_in = summary.get("gate") if isinstance(summary.get("gate"), dict) else None
    stats = model_stats if isinstance(model_stats, dict) else {}

    parts_list = inspect.get("parts")
    return {
        "registered": run.get("map_registered"),
        "images": run.get("map_images"),
        "points3d": run.get("map_points3D"),
        "mean_reprojection_error_px": stats.get("mean_reprojection_error_px"),
        "mean_track_length": stats.get("mean_track_length"),
        "mean_observations_per_image": stats.get("mean_observations_per_image"),
        "parts": len(parts_list) if isinstance(parts_list, list) else None,
        "align": {k: align_in.get(k) for k in _ALIGN_KEYS} if align_in is not None else None,
        "gate": dict(gate_in) if gate_in is not None else None,
        "params": {k: run.get(k) for k in _PARAM_KEYS},
    }


def build(
    *,
    recording: dict,
    network: dict,
    processing: dict,
    quality: dict,
    now: datetime,
) -> dict:
    """Bungkus empat bagian kartu menjadi satu objek laporan berversi."""
    now_utc = _as_utc(now)
    return {
        "version": REPORT_VERSION,
        "computed_at": now_utc.isoformat() if now_utc is not None else None,
        "recording": recording,
        "network": network,
        "processing": processing,
        "quality": quality,
    }


def model_stats(sfm_dir: Path) -> dict | None:
    """Statistik rekonstruksi SfM dari pycolmap.Reconstruction; None bila gagal atau tidak ada."""
    try:
        if not sfm_dir.is_dir():
            return None
        import pycolmap

        model = pycolmap.Reconstruction(str(sfm_dir))

        def _val(raw: Any) -> float | None:
            return float(raw) if _finite(raw) else None

        return {
            "mean_reprojection_error_px": _val(model.compute_mean_reprojection_error()),
            "mean_track_length": _val(model.compute_mean_track_length()),
            "mean_observations_per_image": _val(model.compute_mean_observations_per_reg_image()),
        }
    except Exception:
        return None


def aligned_centers(map_dir: Path, summary: dict) -> dict[str, np.ndarray] | None:
    """Pusat kamera SfM terdaftar di kerangka bangunan (meter, Z-up) bila align diterapkan."""
    align_info = (summary or {}).get("align")
    if not isinstance(align_info, dict) or align_info.get("status") != "applied":
        return None
    try:
        from server import pipeline, quick_align, sim3

        run_path = pipeline.run_dir(map_dir)
        align_path = run_path / "align.json"
        if not align_path.is_file():
            return None
        align_data = json.loads(align_path.read_text(encoding="utf-8-sig"))
        transform = sim3.from_align(align_data["meter_from_model"])
        centers, _ = quick_align.load_model(run_path / "sfm")
        return {name: np.asarray(transform * pos, dtype=float) for name, pos in centers.items()}
    except Exception:
        return None


def _video_seconds(videos: list[dict]) -> tuple[float | None, bool]:
    peta_videos = [
        v
        for v in (videos or [])
        if isinstance(v, dict) and v.get("role") == "peta" and v.get("kind", "video") != "frames"
    ]
    if not peta_videos:
        return None, False
    durs = [v.get("duration_s") for v in peta_videos]
    if all(_finite(d) for d in durs):
        return float(sum(float(d) for d in durs)), True
    return None, True


def _read_meta(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def from_disk(
    job: MapJob,
    map_dir: Path,
    summary: dict,
    live: dict | None,
    now: datetime | None,
    *,
    computed_at: datetime | None = None,
) -> dict:
    """Susun kartu laporan penuh dengan membaca berkas hasil di map_dir.

    Setiap bagian dibungkus sendiri agar galat di satu bagian tidak mengosongkan bagian lain.
    """
    try:
        from server import pipeline, quick_align

        summary = summary if isinstance(summary, dict) else {}
        run = summary.get("run") if isinstance(summary.get("run"), dict) else {}

        try:
            frames_path = map_dir / "capture" / "frames.jsonl"
            if frames_path.is_file():
                frames = quick_align.read_frames(frames_path)
                meta = _read_meta(map_dir / "capture" / "meta.json")
                centers = aligned_centers(map_dir, summary)
                rec = recording(frames, meta, centers, None, run)
            else:
                vid_s, has_video = _video_seconds(job.videos or [])
                rec = recording(None, None, None, vid_s, run, source="video" if has_video else None)
        except Exception as exc:
            rec = {"error": str(exc)}

        try:
            net = network(job.videos or [])
        except Exception as exc:
            net = {"error": str(exc)}

        try:
            proc = processing(job, now, live, run)
        except Exception as exc:
            proc = {"error": str(exc)}

        try:
            stats = model_stats(pipeline.run_dir(map_dir) / "sfm")
            qual = quality(summary, stats)
        except Exception as exc:
            qual = {"error": str(exc)}

        stamp = computed_at if computed_at is not None else (now or datetime.now(UTC))
        return build(recording=rec, network=net, processing=proc, quality=qual, now=stamp)
    except Exception as exc:
        return {"version": REPORT_VERSION, "error": str(exc)}
