"""Training camera views in the unchanged SfM/model frame."""

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

import numpy as np
import pycolmap

MAX_VIEWS = 300


def level_rotation(up: np.ndarray) -> list[float]:
    length = np.linalg.norm(up)
    if length < 1e-12:
        return [0.0, 0.0, 0.0, 1.0]
    up = up / length
    dot = float(np.clip(up[1], -1, 1))
    if dot > 0.9999:
        return [0.0, 0.0, 0.0, 1.0]
    if dot < -0.9999:
        return [1.0, 0.0, 0.0, 0.0]
    axis = np.cross(up, [0.0, 1.0, 0.0])
    axis /= np.linalg.norm(axis)
    half_angle = np.arccos(dot) / 2
    return [*(axis * np.sin(half_angle)).tolist(), float(np.cos(half_angle))]


def training_views(images: Iterable, max_views: int = MAX_VIEWS) -> dict:
    images = sorted(images, key=lambda image: image.name)
    if not images:
        raise ValueError("no registered images")
    if max_views < 1:
        raise ValueError("max_views must be positive")
    centers = np.array([image.projection_center() for image in images], dtype=float)
    rotations = np.array([image.cam_from_world().rotation.matrix() for image in images])
    indices = np.arange(len(images))
    if len(images) > max_views:
        indices = np.unique(np.linspace(0, len(images) - 1, max_views).round().astype(int))
    start = int(np.argmin(np.linalg.norm(centers[indices] - centers.mean(axis=0), axis=1)))
    views = []
    for i in indices:
        forward = rotations[i, 2, :]
        forward = forward / np.linalg.norm(forward)
        views.append(
            {"name": images[i].name, "center": centers[i].tolist(), "forward": forward.tolist()}
        )
    return {
        "start": start,
        "level_rotation_xyzw": level_rotation(-rotations[:, 1, :].mean(axis=0)),
        "views": views,
    }


def load_views(sfm: Path) -> dict:
    return _load_views(str(sfm), (sfm / "images.bin").stat().st_mtime_ns)


@lru_cache(maxsize=8)
def _load_views(sfm: str, mtime_ns: int) -> dict:
    # ponytail: Reconstruction also loads points3D: slow once per version, then cached.
    rec = pycolmap.Reconstruction(sfm)
    return training_views(rec.images.values())
