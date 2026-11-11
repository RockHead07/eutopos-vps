import argparse
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path


def missing_images(names: Iterable[str], images_dir: Path) -> list[str]:
    """Return list of relative image paths from names that do not exist in images_dir."""
    images_path = Path(images_dir)
    return [name for name in names if not (images_path / name).is_file()]


def prepare_splat_data(
    sfm_dir: Path | str,
    images_dir: Path | str,
    out_dir: Path | str,
    max_side: int = 1280,
) -> None:
    """Undistort images and prepare PINHOLE SfM model for Gaussian splat training.

    Parameters
    ----------
    sfm_dir : Path | str
        Path to input COLMAP SfM directory containing cameras.bin, images.bin, points3D.bin.
    images_dir : Path | str
        Path to root directory containing input mapping frames (e.g. dataset root).
    out_dir : Path | str
        Destination directory where undistorted images/ and sparse/0/ will be written.
    max_side : int
        Maximum size of the longer image side (default: 1280).
    """
    sfm_path = Path(sfm_dir)
    images_path = Path(images_dir)
    out_path = Path(out_dir)

    if not sfm_path.exists():
        raise FileNotFoundError(f"SfM directory not found: {sfm_path}")
    if not images_path.exists():
        raise FileNotFoundError(f"Images directory not found: {images_path}")

    out_path.mkdir(parents=True, exist_ok=True)

    import pycolmap

    rec = pycolmap.Reconstruction(str(sfm_path))
    image_names = [img.name for img in rec.images.values()]

    missing = missing_images(image_names, images_path)
    if missing:
        print(
            f"ERROR: {len(missing)} registered images missing in {images_path}:",
            file=sys.stderr,
        )
        for name in missing[:5]:
            print(f"  - {name}", file=sys.stderr)
        sys.exit(1)

    opt = pycolmap.UndistortCameraOptions()
    if max_side > 0:
        opt.max_image_size = max_side

    print(
        f"Running undistort_images: sfm={sfm_path}, images={images_path}, "
        f"out={out_path}, max_side={max_side}"
    )
    pycolmap.undistort_images(
        output_path=str(out_path),
        input_path=str(sfm_path),
        image_path=str(images_path),
        undistort_options=opt,
    )

    out_images_dir = out_path / "images"
    produced_images = [p for p in out_images_dir.rglob("*") if p.is_file()]
    if len(produced_images) != len(image_names):
        print(
            f"ERROR: Produced images count ({len(produced_images)}) does not match "
            f"registered images count ({len(image_names)}).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Ensure <out>/sparse/0/ exists as required by the plan interface
    sparse_dir = out_path / "sparse"
    sparse_0_dir = sparse_dir / "0"
    if sparse_dir.exists() and not sparse_0_dir.exists():
        bin_files = list(sparse_dir.glob("*.bin"))
        if bin_files:
            sparse_0_dir.mkdir(parents=True, exist_ok=True)
            for f in bin_files:
                shutil.copy2(f, sparse_0_dir / f.name)
            print(f"Copied {len(bin_files)} .bin files to {sparse_0_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare undistorted images and PINHOLE SfM model for Gaussian splatting."
    )
    parser.add_argument("--sfm", required=True, help="Path to input COLMAP SfM directory")
    parser.add_argument("--images", required=True, help="Path to input images root directory")
    parser.add_argument("--out", required=True, help="Path to output directory")
    parser.add_argument(
        "--max-side",
        type=int,
        default=1280,
        help="Maximum image side length (default: 1280)",
    )
    args = parser.parse_args()

    prepare_splat_data(
        sfm_dir=args.sfm,
        images_dir=args.images,
        out_dir=args.out,
        max_side=args.max_side,
    )
    print("Splat data preparation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
