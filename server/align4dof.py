"""Port Python murni dari Aligner4Dof.cs dan FrameConvert.cs (eutopos-mobile) serta konsensus R5.

Konvensi kerangka:
- G (gedung/server): tangan kanan, Z atas (meter).
- B (gedung di Unity): tangan kiri, Y atas, diperoleh dengan menukar Y dan Z dari G.
- U (sesi AR Unity): tangan kiri, Y atas (meter).
- Penyelarasan 4-DoF memetakan B ke U: p_U = RotY(yaw_deg) * p_B + translation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from server.quick_align import unity_to_building

MIN_HORIZONTAL_FRACTION = 0.3
CONSENSUS_TRANSLATION_M = 0.5
CONSENSUS_YAW_DEG = 5.0
CONSENSUS_MIN_FRAMES = 2
MIN_VIEW_SPREAD_DEG = 20.0


@dataclass(frozen=True)
class Alignment4Dof:
    yaw_deg: float
    translation: np.ndarray  # shape (3,) di kerangka U (Unity)

    def __post_init__(self) -> None:
        object.__setattr__(self, "yaw_deg", wrap_deg(float(self.yaw_deg)))
        object.__setattr__(self, "translation", np.asarray(self.translation, dtype=np.float64))

    def b_to_u(self, p_b) -> np.ndarray:
        return rot_y(self.yaw_deg, p_b) + self.translation

    def u_to_b(self, p_u) -> np.ndarray:
        return rot_y(-self.yaw_deg, np.asarray(p_u, dtype=np.float64) - self.translation)


@dataclass(frozen=True)
class FrameAlignment:
    frame_index: int
    alignment: Alignment4Dof
    inliers: int


@dataclass(frozen=True)
class ConsensusResult:
    alignment: Alignment4Dof
    agreeing_indices: list[int]
    total_inliers: int


def g_to_b(g) -> np.ndarray:
    """Konversi vektor dari G (kanan, Z atas) ke B (Unity kidal, Y atas): tukar Y dan Z."""
    arr = np.asarray(g, dtype=np.float64).reshape(1, 3)
    return unity_to_building(arr)[0]


def b_to_g(b) -> np.ndarray:
    """Konversi vektor dari B (Unity kidal, Y atas) ke G (kanan, Z atas): tukar Y dan Z."""
    return g_to_b(b)


def rotate_vec_by_quat_xyzw(q_xyzw, v) -> np.ndarray:
    """Putar vektor v dengan kuaternion [x, y, z, w], identik dengan Vector3.Transform di C#."""
    q = np.asarray(q_xyzw, dtype=np.float64)
    norm = float(np.linalg.norm(q))
    if norm < 1e-12:
        raise ValueError("kuaternion nol")
    qx, qy, qz, qw = q / norm
    u = np.array([qx, qy, qz], dtype=np.float64)
    vec = np.asarray(v, dtype=np.float64)
    t = 2.0 * np.cross(u, vec)
    return vec + qw * t + np.cross(u, t)


def forward_b(building_from_cam_g_xyzw) -> np.ndarray:
    """Sumbu optik kamera (+Z_cam) di G lalu dipetakan ke B (FrameConvert.ForwardB)."""
    return g_to_b(rotate_vec_by_quat_xyzw(building_from_cam_g_xyzw, (0.0, 0.0, 1.0)))


def ar_forward_u(ar_rotation_xyzw) -> np.ndarray:
    """Arah depan kamera AR di Unity (ar_rotation * +Z), sama seperti arCamera.transform.forward."""
    return rotate_vec_by_quat_xyzw(ar_rotation_xyzw, (0.0, 0.0, 1.0))


def ar_heading_deg(ar_rotation_xyzw) -> float | None:
    """Heading yaw kamera AR (derajat, +Z ke +X), None bila kamera terlalu vertikal."""
    return yaw_deg(ar_forward_u(ar_rotation_xyzw))


def view_spread_deg(headings_deg: list[float | None]) -> float | None:
    """Selisih sudut berpasangan terbesar (0..180 derajat) dari heading yang sah; None jika < 2."""
    valid = [float(h) for h in headings_deg if h is not None]
    if len(valid) < 2:
        return None
    best = 0.0
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            diff = yaw_diff_deg(valid[i], valid[j])
            if diff > best:
                best = diff
    return best


def is_view_diverse(
    spread_deg: float | None, *, min_spread_deg: float = MIN_VIEW_SPREAD_DEG
) -> bool:
    """True bila rentang sudut pandang klaster pemenang >= min_spread_deg."""
    return spread_deg is not None and spread_deg >= min_spread_deg


def yaw_deg(f) -> float | None:
    """Yaw dari +Z ke +X (derajat), None bila kamera terlalu tegak lurus lantai."""
    v = np.asarray(f, dtype=np.float64)
    length = float(np.linalg.norm(v))
    horizontal = math.hypot(float(v[0]), float(v[2]))
    if length < 1e-6 or horizontal < MIN_HORIZONTAL_FRACTION * length:
        return None
    return math.degrees(math.atan2(float(v[0]), float(v[2])))


def wrap_deg(deg: float) -> float:
    """Bungkus sudut ke rentang [-180, 180)."""
    return ((float(deg) + 180.0) % 360.0) - 180.0


def yaw_diff_deg(a: float, b: float) -> float:
    return abs(wrap_deg(a - b))


def rot_y(deg: float, v) -> np.ndarray:
    """Putar di sekitar +Y (+Z ke +X), sama dengan Quaternion.Euler(0, deg, 0) di Unity."""
    vec = np.asarray(v, dtype=np.float64)
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([c * vec[0] + s * vec[2], vec[1], -s * vec[0] + c * vec[2]], dtype=np.float64)


def solve(cam_pos_u, cam_fwd_u, cam_pos_b, cam_fwd_b) -> Alignment4Dof | None:
    """Port langsung Aligner4Dof.Solve(camPosU, camFwdU, camPosB, camFwdB)."""
    yu = yaw_deg(cam_fwd_u)
    yb = yaw_deg(cam_fwd_b)
    if yu is None or yb is None:
        return None
    theta = wrap_deg(yu - yb)
    pos_u = np.asarray(cam_pos_u, dtype=np.float64)
    pos_b = np.asarray(cam_pos_b, dtype=np.float64)
    return Alignment4Dof(theta, pos_u - rot_y(theta, pos_b))


def solve_from_poses(
    ar_position, ar_rotation_xyzw, building_position_g, building_rotation_xyzw
) -> Alignment4Dof | None:
    """Hitung penyelarasan 4-DoF dari pose AR (Unity U) dan pose_building (server G)."""
    cam_fwd_u = ar_forward_u(ar_rotation_xyzw)
    cam_pos_b = g_to_b(building_position_g)
    cam_fwd_b = forward_b(building_rotation_xyzw)
    return solve(ar_position, cam_fwd_u, cam_pos_b, cam_fwd_b)


def consensus(
    items: list[FrameAlignment],
    *,
    max_translation_m: float = CONSENSUS_TRANSLATION_M,
    max_yaw_deg: float = CONSENSUS_YAW_DEG,
    min_frames: int = CONSENSUS_MIN_FRAMES,
) -> ConsensusResult | None:
    """Klaster penyelarasan dengan jarak <= max_translation_m DAN yaw <= max_yaw_deg.

    Mengambil klaster terbesar (seri: total inlier lebih tinggi), lalu rata-rata tertimbang inlier
    (rata-rata sirkular untuk yaw). Mengembalikan None bila klaster terbesar < min_frames.
    """
    if len(items) < min_frames:
        return None

    best_cluster: list[FrameAlignment] = []
    best_inliers = -1
    for seed in items:
        cluster = [
            other
            for other in items
            if float(np.linalg.norm(other.alignment.translation - seed.alignment.translation))
            <= max_translation_m
            and yaw_diff_deg(other.alignment.yaw_deg, seed.alignment.yaw_deg) <= max_yaw_deg
        ]
        total_inl = sum(m.inliers for m in cluster)
        if (len(cluster), total_inl) > (len(best_cluster), best_inliers):
            best_cluster = cluster
            best_inliers = total_inl

    if len(best_cluster) < min_frames:
        return None

    weights = np.array([max(1, m.inliers) for m in best_cluster], dtype=np.float64)
    w_sum = float(weights.sum())
    mean_t = (
        sum(w * m.alignment.translation for w, m in zip(weights, best_cluster, strict=True)) / w_sum
    )
    rads = np.radians([m.alignment.yaw_deg for m in best_cluster])
    sin_sum = float(np.sum(weights * np.sin(rads)))
    cos_sum = float(np.sum(weights * np.cos(rads)))
    mean_yaw = wrap_deg(math.degrees(math.atan2(sin_sum, cos_sum)))
    return ConsensusResult(
        alignment=Alignment4Dof(mean_yaw, mean_t),
        agreeing_indices=[m.frame_index for m in best_cluster],
        total_inliers=int(best_inliers),
    )
