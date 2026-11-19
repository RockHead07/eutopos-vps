"""Penyelarasan cepat dari pose ARCore atau jarak antar-frame, tanpa akses database."""

import json
from pathlib import Path, PurePosixPath

import numpy as np
import pycolmap

from server import sim3
from server.alignment import MIN_ARCORE_FRAMES, validate_align
from server.navgraph import _number

# Ambang awal untuk peringatan, belum dikalibrasi dengan data lapangan.
MIN_RECOMMENDED_DISTANCE_M = 10
MAX_GRAVITY_SPREAD_DEG = 10
MAX_SCALE_SPREAD_PERCENT = 5
MAX_ARCORE_MEDIAN_RESIDUAL_M = 0.25
MIN_MODEL_DISTANCE = 1e-8


def _basename(name: str) -> str:
    return PurePosixPath(name.replace("\\", "/")).name


def unity_to_building(p: np.ndarray) -> np.ndarray:
    """Tukar Y dan Z, dari Unity kidal Y-up ke kerangka tangan kanan Z-up."""
    return p[:, [0, 2, 1]]


def load_model(sfm_dir: Path) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    model = pycolmap.Reconstruction(str(sfm_dir))
    centers, ups = {}, {}
    for image_id in model.reg_image_ids():
        image = model.images[image_id]
        name = _basename(image.name)
        if name in centers:
            raise ValueError(f"nama dasar gambar SfM kembar: {name}")
        centers[name] = image.projection_center()
        # R mengubah dunia ke kamera. Arah atas gambar adalah -Y di kamera.
        ups[name] = -image.cam_from_world().rotation.matrix()[1]
    return centers, ups


def read_frames(path: Path) -> list[dict]:
    frames = []
    with path.open("rb") as source:
        for number, raw in enumerate(source, 1):
            try:
                frame = json.loads(raw.decode("utf-8-sig" if number == 1 else "utf-8"))
                if not isinstance(frame, dict):
                    raise ValueError("frame harus objek JSON")
                file, position = frame.get("file"), frame.get("position")
                if not isinstance(file, str) or not _basename(file.strip()):
                    raise ValueError("file harus nama frame")
                if (
                    not isinstance(position, list)
                    or len(position) != 3
                    or not all(_number(x) for x in position)
                ):
                    raise ValueError("position harus 3 angka berhingga")
            except ValueError as exc:
                raise ValueError(f"frames.jsonl baris {number}: {exc}") from exc
            frames.append(frame)
    return frames


def from_arcore(centers, frames, height_m=1.3, ransac_m=0.5) -> dict:
    matched = {}
    for frame in frames:
        name = _basename(frame["file"])
        if name not in centers:
            continue
        if name in matched:
            raise ValueError(f"nama dasar frame ARCore kembar: {name}")
        matched[name] = frame["position"]
    if len(matched) < MIN_ARCORE_FRAMES:
        raise ValueError(f"butuh >= {MIN_ARCORE_FRAMES} foto ARCore cocok, ada {len(matched)}")

    src = np.array([centers[name] for name in matched], float)
    target = unity_to_building(np.array(list(matched.values()), float))
    target[:, 2] += height_m - np.median(target[:, 2])
    sim = sim3.fit(src, target, ransac_m)
    if sim is None:
        raise ValueError("penaksiran Sim3 ARCore gagal")
    scale = float(sim.scale)
    if not _number(scale) or scale <= 0:
        raise ValueError(f"skala hasil taksiran tidak sah: {scale}")
    errors = np.linalg.norm(sim * src - target, axis=1)
    return validate_align(
        {
            "method": "arcore_pose",
            "meter_from_model": {
                "scale": scale,
                "rotation_xyzw": sim.rotation.quat.tolist(),
                "translation": sim.translation.tolist(),
            },
            "phone_height_m": height_m,
            "matched_frames": len(matched),
            "residual_median_m": round(float(np.median(errors)), 3),
            "residual_max_m": round(float(errors.max()), 3),
        }
    )


def from_known_distance(centers, ups, pairs, height_m=1.3) -> dict:
    if not 1 <= len(pairs) <= 2:
        raise ValueError("butuh 1 atau 2 pasangan jarak")
    if not centers or centers.keys() != ups.keys():
        raise ValueError("arah atas diperlukan untuk setiap frame terdaftar")

    names = sorted(centers)
    points = np.array([centers[name] for name in names], float)
    directions = np.array([ups[name] for name in names], float)
    norms = np.linalg.norm(directions, axis=1)
    if not np.isfinite(norms).all() or np.any(norms == 0):
        raise ValueError("arah atas frame tidak sah")
    directions /= norms[:, None]
    up = directions.mean(axis=0)
    norm = np.linalg.norm(up)
    if norm < MIN_MODEL_DISTANCE:
        raise ValueError("rata-rata arah atas terlalu kecil untuk menaksir gravitasi")
    up /= norm
    spread = np.median(np.degrees(np.arccos(np.clip(directions @ up, -1, 1))))

    distances, scales = [], []
    for frame_a, frame_b, distance_m in pairs:
        a, b = _basename(frame_a), _basename(frame_b)
        if a not in centers or b not in centers:
            raise ValueError(f"frame tidak terdaftar: {a if a not in centers else b}")
        if not _number(distance_m) or distance_m <= 0:
            raise ValueError("jarak meter harus angka positif berhingga")
        delta = np.asarray(centers[b]) - centers[a]
        model_distance = float(np.linalg.norm(delta - (delta @ up) * up))
        if not _number(model_distance) or model_distance < MIN_MODEL_DISTANCE:
            raise ValueError(f"jarak horizontal model terlalu kecil atau tidak sah: {a}, {b}")
        scales.append(distance_m / model_distance)
        distances.append(
            {"frame_a": a, "frame_b": b, "distance_m": distance_m, "model_distance": model_distance}
        )
    scale = float(np.mean(scales))
    if not _number(scale) or scale <= 0:
        raise ValueError(f"skala hasil taksiran tidak sah: {scale}")

    relative = points - points[0]
    floor = relative - np.outer(relative @ up, up)
    _, _, axes = np.linalg.svd(floor - floor.mean(axis=0), full_matrices=False)
    x = axes[0]
    along_x = floor @ x
    # Pilih tanda PCA dari kamera pertama menuju kamera terjauh di sepanjang sumbu itu.
    if along_x[np.argmax(np.abs(along_x))] < 0:
        x = -x
    rotation = np.stack([x, np.cross(up, x), up])
    translation = -scale * (rotation @ points[0])
    translation[2] = height_m - scale * np.median(points @ up)
    align = {
        "method": "known_distance",
        "meter_from_model": {
            "scale": scale,
            "rotation_xyzw": pycolmap.Rotation3d(rotation).quat.tolist(),
            "translation": translation.tolist(),
        },
        "phone_height_m": height_m,
        "known_distances": distances,
        "gravity_spread_deg": float(spread),
    }
    if len(scales) == 2:
        align["scale_spread_percent"] = abs(scales[0] - scales[1]) / scale * 100
    return validate_align(align)


def warnings(align: dict) -> list[str]:
    result = []
    method = align.get("method")
    if method == "known_distance":
        pairs = align["known_distances"]
        if len(pairs) == 1:
            result.append("Hanya satu pasangan jarak. Gunakan pasangan kedua untuk mengecek skala.")
        if any(pair["distance_m"] < MIN_RECOMMENDED_DISTANCE_M for pair in pairs):
            result.append(f"Ada jarak di bawah {MIN_RECOMMENDED_DISTANCE_M} m.")
        if align["gravity_spread_deg"] > MAX_GRAVITY_SPREAD_DEG:
            result.append(f"Sebaran gravitasi di atas {MAX_GRAVITY_SPREAD_DEG} derajat.")
        if align.get("scale_spread_percent", 0) > MAX_SCALE_SPREAD_PERCENT:
            result.append(f"Selisih skala antar-pasangan di atas {MAX_SCALE_SPREAD_PERCENT}%.")
    elif method == "arcore_pose" and align["residual_median_m"] > MAX_ARCORE_MEDIAN_RESIDUAL_M:
        result.append(f"Median residu ARCore di atas {MAX_ARCORE_MEDIAN_RESIDUAL_M:g} m.")
    return result
