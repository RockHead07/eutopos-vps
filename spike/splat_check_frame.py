import argparse
import sys
from pathlib import Path

import numpy as np


def median_nn_distance(points: np.ndarray, means: np.ndarray) -> float:
    """Calculate median distance from each COLMAP 3D point to its nearest Gaussian center.

    Parameters
    ----------
    points : np.ndarray
        Array of shape (N, 3) containing 3D points from COLMAP reconstruction.
    means : np.ndarray
        Array of shape (M, 3) containing 3D Gaussian centers from splat PLY.

    Returns
    -------
    float
        The median nearest-neighbor distance.
    """
    points = np.asarray(points, dtype=np.float64)
    means = np.asarray(means, dtype=np.float64)

    if points.size == 0 or means.size == 0:
        raise ValueError("points and means must not be empty")

    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(f"points must have shape (N, 3), got {points.shape}")

    if means.ndim != 2 or means.shape[1] != 3:
        raise ValueError(f"means must have shape (M, 3), got {means.shape}")

    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(means)
        distances, _ = tree.query(points, k=1)
        return float(np.median(distances))
    except ImportError:
        block_size = 512
        min_dists = []
        for i in range(0, len(points), block_size):
            pts_block = points[i : i + block_size]
            diff = pts_block[:, np.newaxis, :] - means[np.newaxis, :, :]
            dists = np.linalg.norm(diff, axis=-1)
            min_dists.append(dists.min(axis=1))
        all_min = np.concatenate(min_dists)
        return float(np.median(all_min))


def load_ply_means(ply_path: Path | str) -> np.ndarray:
    """Read 3D Gaussian centers (x, y, z) from a PLY file without external ply libraries."""
    ply_path = Path(ply_path)
    if not ply_path.exists():
        raise FileNotFoundError(f"PLY file not found: {ply_path}")

    with open(ply_path, "rb") as f:
        header_lines = []
        found_end_header = False
        while True:
            raw_line = f.readline()
            if not raw_line:
                break
            line = raw_line.decode("latin1").strip()
            header_lines.append(line)
            if line == "end_header":
                found_end_header = True
                break

        if not found_end_header:
            raise ValueError(f"Unexpected EOF before end_header in PLY file: {ply_path}")

        format_line = next(
            (line_item for line_item in header_lines if line_item.startswith("format ")),
            "",
        )
        is_binary = "binary_little_endian" in format_line
        is_ascii = "ascii" in format_line

        if not (is_binary or is_ascii):
            raise ValueError(f"Unsupported PLY format: {format_line}")

        num_vertices = 0
        properties = []
        in_vertex = False

        for line in header_lines:
            tokens = line.split()
            if not tokens:
                continue
            if tokens[0] == "element":
                in_vertex = tokens[1] == "vertex"
                if in_vertex:
                    num_vertices = int(tokens[2])
            elif tokens[0] == "property" and in_vertex:
                prop_type = tokens[1]
                prop_name = tokens[2]
                properties.append((prop_name, prop_type))

        if num_vertices == 0:
            return np.empty((0, 3), dtype=np.float64)

        type_map = {
            "float": "<f4",
            "float32": "<f4",
            "double": "<f8",
            "float64": "<f8",
            "uchar": "u1",
            "uint8": "u1",
            "char": "i1",
            "int8": "i1",
            "int": "<i4",
            "int32": "<i4",
            "uint": "<u4",
            "uint32": "<u4",
            "short": "<i2",
            "int16": "<i2",
            "ushort": "<u2",
            "uint16": "<u2",
        }

        dtype_fields = []
        for name, ptype in properties:
            if ptype not in type_map:
                raise ValueError(f"Unknown PLY property type: {ptype}")
            dtype_fields.append((name, type_map[ptype]))

        vertex_dtype = np.dtype(dtype_fields)

        if is_binary:
            data = np.fromfile(f, dtype=vertex_dtype, count=num_vertices)
            x = data["x"].astype(np.float64)
            y = data["y"].astype(np.float64)
            z = data["z"].astype(np.float64)
            return np.column_stack([x, y, z])
        else:
            prop_names = [p[0] for p in properties]
            x_idx = prop_names.index("x")
            y_idx = prop_names.index("y")
            z_idx = prop_names.index("z")
            pts = []
            for _ in range(num_vertices):
                vals = f.readline().decode("latin1").split()
                pts.append([float(vals[x_idx]), float(vals[y_idx]), float(vals[z_idx])])
            return np.asarray(pts, dtype=np.float64)


def load_colmap_points(sfm_dir: Path | str) -> np.ndarray:
    """Read COLMAP 3D points lazily importing pycolmap."""
    sfm_path = Path(sfm_dir)
    if not sfm_path.exists():
        raise FileNotFoundError(f"SfM directory not found: {sfm_path}")

    import pycolmap

    rec = pycolmap.Reconstruction(str(sfm_path))
    pts = [p.xyz for p in rec.points3D.values()]
    if not pts:
        return np.empty((0, 3), dtype=np.float64)
    return np.asarray(pts, dtype=np.float64)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check if Gaussian splat frame matches COLMAP SfM model frame."
    )
    parser.add_argument("--ply", required=True, help="Path to scene.ply")
    parser.add_argument("--sfm", required=True, help="Path to COLMAP SfM directory")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.02,
        help="Max allowable ratio of median NN distance to bounding box width (default: 0.02)",
    )
    args = parser.parse_args()

    ply_path = Path(args.ply)
    sfm_path = Path(args.sfm)

    means = load_ply_means(ply_path)
    points = load_colmap_points(sfm_path)

    if points.size == 0:
        print("ERROR: COLMAP model has no 3D points.", file=sys.stderr)
        return 1

    if means.size == 0:
        print("ERROR: PLY file has no Gaussian means.", file=sys.stderr)
        return 1

    box_width = float(np.max(points.max(axis=0) - points.min(axis=0)))
    if box_width <= 0:
        print("ERROR: Bounding box width is zero.", file=sys.stderr)
        return 1

    dist = median_nn_distance(points, means)
    ratio = dist / box_width

    print(f"Points: {len(points)}, Splats: {len(means)}")
    print(f"Bounding box width: {box_width:.4f}")
    print(f"Median NN distance: {dist:.6f}")
    print(f"Ratio (distance / box_width): {ratio:.6f} (threshold: {args.threshold})")

    if ratio < args.threshold:
        print("PASS: Splat frame matches COLMAP model frame.")
        return 0
    else:
        print(f"FAIL: Ratio {ratio:.6f} >= {args.threshold}. Splat frame is misaligned!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
