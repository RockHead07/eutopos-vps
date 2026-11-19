"""Compare registered SfM camera centers to Unity ARCore positions for one spike session."""

import argparse
import json
import sys
from pathlib import Path, PurePosixPath

import numpy as np


def unity_to_right_handed(positions):
    """Reflect Unity's Z axis. X and Y (up) stay unchanged; Umeyama fits a proper rotation."""
    return np.asarray(positions, dtype=float) * (1.0, 1.0, -1.0)


def fit_sim3(source, target):
    """Return positive scale, proper rotation and translation mapping source onto target."""
    if len(source) < 3:
        raise ValueError("at least three matched camera centers are required")
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    x = source - source_mean
    y = target - target_mean
    variance = np.sum(x * x) / len(x)
    if variance <= 0 or not np.any(y):
        raise ValueError("camera centers must span a nonzero distance in both trajectories")
    u, singular, vh = np.linalg.svd(y.T @ x / len(x))
    signs = np.ones(3)
    if np.linalg.det(u @ vh) < 0:
        signs[-1] = -1
    rotation = (u * signs) @ vh
    scale = float(singular @ signs / variance)
    if scale <= 0:
        raise ValueError("camera centers do not determine a positive scale")
    return scale, rotation, target_mean - scale * (rotation @ source_mean)


def compare(source, target, session_frames):
    scale, rotation, translation = fit_sim3(source, target)
    errors = np.linalg.norm(scale * (source @ rotation.T) + translation - target, axis=1)
    split = len(source) // 2
    try:
        first, _, _ = fit_sim3(source[:split], target[:split])
        second, _, _ = fit_sim3(source[split:], target[split:])
        drift = {
            "first_half_scale": first,
            "second_half_scale": second,
            "difference_percent": abs(second - first) / first * 100,
        }
    except ValueError as exc:
        drift = {"unavailable": str(exc)}
    return {
        "matched_frames": len(source),
        "session_frames": session_frames,
        "unity_to_right_handed": "x, y, -z (Y up)",
        "scale": scale,
        "rotation": rotation.tolist(),
        "translation_m": translation.tolist(),
        "rmse_m": float(np.sqrt(np.mean(errors**2))),
        "median_residual_m": float(np.median(errors)),
        "max_residual_m": float(errors.max()),
        "scale_drift": drift,
    }


def basename(name):
    return PurePosixPath(name.replace("\\", "/")).name


def load_pairs(session, model):
    import pycolmap

    reconstruction = pycolmap.Reconstruction(str(model))
    centers = {}
    for image_id in reconstruction.reg_image_ids():
        image = reconstruction.images[image_id]
        name = basename(image.name)
        if name in centers:
            raise ValueError(f"duplicate SfM image basename: {name}")
        centers[name] = image.projection_center()
    source, unity = [], []
    seen = set()
    with (session / "frames.jsonl").open(encoding="utf-8") as frames:
        # The recorder appends in capture order. Only matched frames count toward the split.
        for number, line in enumerate(frames, 1):
            try:
                frame = json.loads(line)
                name = basename(frame["file"])
                position = np.asarray(frame["position"], dtype=float)
                if not name or position.shape != (3,) or not np.isfinite(position).all():
                    raise ValueError("expected a file name and three finite coordinates")
                if name in seen:
                    raise ValueError(f"duplicate recorded image basename: {name}")
                seen.add(name)
                if name in centers:
                    source.append(centers[name])
                    unity.append(position)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"frames.jsonl line {number}: {exc}") from exc
    return np.asarray(source), unity_to_right_handed(np.asarray(unity).reshape(-1, 3)), len(seen)


def self_test():
    source = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [0, 2, 0],
            [0, 0, 3],
            [2, 1, 0],
            [1, 1, 2],
            [2, 0, 2],
            [3, 2, 4],
        ],
        dtype=float,
    )
    rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    scale = 2.5
    translation = np.array([3, -2, 7])
    target = scale * (source @ rotation.T) + translation
    unity = target.copy()
    unity[:, 2] *= -1
    converted = unity_to_right_handed(unity)
    np.testing.assert_allclose(converted, target)
    result = compare(source, converted, len(source))
    np.testing.assert_allclose(result["rotation"], rotation, atol=1e-12)
    np.testing.assert_allclose(result["translation_m"], translation, atol=1e-12)
    np.testing.assert_allclose(result["scale"], scale, atol=1e-12)
    assert result["rmse_m"] < 1e-12
    assert result["max_residual_m"] < 1e-12
    assert result["scale_drift"]["difference_percent"] < 1e-10
    assert compare(source, unity, len(source))["rmse_m"] > 0.1

    drifting = target.copy()
    drifting[4:] = 3.0 * (source[4:] @ rotation.T) + translation
    drift = compare(source, drifting, len(source))["scale_drift"]
    np.testing.assert_allclose(
        [drift["first_half_scale"], drift["second_half_scale"], drift["difference_percent"]],
        [2.5, 3.0, 20.0],
        atol=1e-12,
    )
    print(
        f"Self-test passed: scale={result['scale']:.6f}, "
        f"RMSE={result['rmse_m']:.3e} m, max={result['max_residual_m']:.3e} m, "
        f"known drift={drift['difference_percent']:.2f}%"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, nargs="?", help="spike folder with frames.jsonl")
    parser.add_argument("sfm", type=Path, nargs="?", help="COLMAP model folder (sfm/)")
    parser.add_argument("--out", type=Path, help="write JSON to this file instead of stdout")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.session is None or args.sfm is None:
        parser.error("session and sfm are required unless --self-test is set")
    try:
        result = compare(*load_pairs(args.session, args.sfm))
        output = json.dumps(result, indent=2, allow_nan=False)
        if args.out is None:
            print(output)
        else:
            args.out.write_text(output + "\n", encoding="utf-8")
    except (OSError, RuntimeError, ValueError, np.linalg.LinAlgError) as exc:
        parser.exit(1, f"{exc}\n")
    print(
        f"Matched {result['matched_frames']}/{result['session_frames']} frames. "
        f"Scale={result['scale']:.6g} m/model unit. "
        f"RMSE={result['rmse_m']:.4g} m, median={result['median_residual_m']:.4g} m, "
        f"max={result['max_residual_m']:.4g} m.",
        file=sys.stderr,
    )
    drift = result["scale_drift"]
    if "unavailable" in drift:
        print(f"Scale drift unavailable: {drift['unavailable']}", file=sys.stderr)
    else:
        print(
            f"Half scales: {drift['first_half_scale']:.6g} and {drift['second_half_scale']:.6g}. "
            f"Difference relative to first half: {drift['difference_percent']:.3g}%.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
