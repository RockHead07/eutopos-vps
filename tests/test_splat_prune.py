import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from spike.splat_prune import DEFAULT_MIN_OPACITY, SogError, main, prune_sog


def make_synthetic_sog(
    path: Path,
    *,
    count: int = 40,
    width: int = 8,
    height: int = 5,
    alphas: list[int] | None = None,
    scale_indices: list[list[int]] | None = None,
    codebook: list[float] | None = None,
    include_shN: bool = False,
    missing_texture: str | None = None,
    meta_override: dict | None = None,
) -> Path:
    """Helper to create a small synthetic SOG v2 archive in-memory for testing."""
    if alphas is None:
        # Default distribution of alpha bytes
        # 0: zero, 5: <= 5 (dropped at 0.02), 6: >= 6 (kept at 0.02), 255: full
        base = [0, 5, 6, 255, 3, 4, 7, 10, 20, 50]
        alphas = (base * ((count // len(base)) + 1))[:count]

    if codebook is None:
        codebook = [-2.0, -1.0, 0.0, 1.0]

    if scale_indices is None:
        scale_indices = [[2, 2, 2] for _ in range(count)]

    total_pixels = width * height
    textures = {}

    # 1. means_l: RGBA
    arr_l = np.zeros((total_pixels, 4), dtype=np.uint8)
    for i in range(count):
        arr_l[i] = [i % 256, (i + 1) % 256, (i + 2) % 256, 255]
    textures["means_l.webp"] = arr_l.reshape(height, width, 4)

    # 2. means_u: RGBA
    arr_u = np.zeros((total_pixels, 4), dtype=np.uint8)
    for i in range(count):
        arr_u[i] = [(i + 10) % 256, (i + 11) % 256, (i + 12) % 256, 255]
    textures["means_u.webp"] = arr_u.reshape(height, width, 4)

    # 3. quats: RGBA
    arr_q = np.zeros((total_pixels, 4), dtype=np.uint8)
    for i in range(count):
        arr_q[i] = [(i + 20) % 256, (i + 21) % 256, (i + 22) % 256, (i + 23) % 256]
    textures["quats.webp"] = arr_q.reshape(height, width, 4)

    # 4. scales: RGB codebook indices + A
    arr_s = np.zeros((total_pixels, 4), dtype=np.uint8)
    for i in range(count):
        sx, sy, sz = scale_indices[i]
        arr_s[i] = [sx, sy, sz, 255]
    textures["scales.webp"] = arr_s.reshape(height, width, 4)

    # 5. sh0: RGB color + A opacity
    arr_sh = np.zeros((total_pixels, 4), dtype=np.uint8)
    for i in range(count):
        arr_sh[i] = [(i + 50) % 256, (i + 60) % 256, (i + 70) % 256, alphas[i]]
    textures["sh0.webp"] = arr_sh.reshape(height, width, 4)

    meta = {
        "version": 2,
        "asset": {"generator": "test"},
        "count": count,
        "means": {
            "mins": [-1.0, -1.0, -1.0],
            "maxs": [1.0, 1.0, 1.0],
            "files": ["means_l.webp", "means_u.webp"],
        },
        "scales": {
            "codebook": codebook,
            "files": ["scales.webp"],
        },
        "quats": {
            "files": ["quats.webp"],
        },
        "sh0": {
            "files": ["sh0.webp"],
        },
    }

    if include_shN:
        meta["shN"] = {"files": ["sh1.webp"]}

    if meta_override:
        meta.update(meta_override)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("meta.json", json.dumps(meta))
        for name, arr in textures.items():
            if name == missing_texture:
                continue
            buf = io.BytesIO()
            Image.fromarray(arr, "RGBA").save(buf, "WEBP", lossless=True, exact=True, method=6)
            z.writestr(name, buf.getvalue())

    return path


def test_default_pruning_drops_alpha_le_5_and_keeps_ge_6(tmp_path: Path):
    # 40 Gaussians with specific alpha bytes:
    # 0, 5 should be dropped (5/255 = 0.0196 < 0.02)
    # 6, 255 should be kept (6/255 = 0.0235 >= 0.02)
    alphas = [0, 5, 6, 255] * 10
    src = tmp_path / "in.sog"
    dst = tmp_path / "out.sog"
    make_synthetic_sog(src, count=40, width=8, height=5, alphas=alphas)

    rep = prune_sog(src, dst)

    assert rep["in_count"] == 40
    # Exactly half (6 and 255) are kept -> 20 kept, 20 removed
    assert rep["out_count"] == 20
    assert rep["removed"] == 20
    assert rep["removed_pct"] == 50.0
    assert rep["rules"]["min_opacity"] == DEFAULT_MIN_OPACITY

    # Inspect destination SOG
    with zipfile.ZipFile(dst, "r") as z:
        out_meta = json.loads(z.read("meta.json"))
        assert out_meta["count"] == 20

        # Read textures from both src and dst
        with zipfile.ZipFile(src, "r") as z_src:
            kept_indices = [i for i, a in enumerate(alphas) if a >= 6]
            for tex_name in [
                "means_l.webp",
                "means_u.webp",
                "quats.webp",
                "scales.webp",
                "sh0.webp",
            ]:
                src_img = np.asarray(Image.open(io.BytesIO(z_src.read(tex_name))).convert("RGBA"))
                dst_img = np.asarray(Image.open(io.BytesIO(z.read(tex_name))).convert("RGBA"))

                src_flat = src_img.reshape(-1, 4)[:40]
                dst_flat = dst_img.reshape(-1, 4)

                # Row order and exact bytes must match for all kept Gaussians
                np.testing.assert_array_equal(dst_flat[:20], src_flat[kept_indices])


def test_texture_dimensions_width_preserved_height_ceil(tmp_path: Path):
    # 40 Gaussians, 8 width x 5 height. Keep 21 Gaussians.
    # New height should be ceil(21 / 8) = 3.
    # Total pixels = 8 * 3 = 24.
    # Pixels 0..20 are Gaussians, pixels 21..23 must be all zeros [0, 0, 0, 0].
    alphas = [6] * 21 + [5] * 19
    src = tmp_path / "in.sog"
    dst = tmp_path / "out.sog"
    make_synthetic_sog(src, count=40, width=8, height=5, alphas=alphas)

    rep = prune_sog(src, dst)
    assert rep["out_count"] == 21

    with zipfile.ZipFile(dst, "r") as z:
        for tex_name in ["means_l.webp", "means_u.webp", "quats.webp", "scales.webp", "sh0.webp"]:
            dst_img = np.asarray(Image.open(io.BytesIO(z.read(tex_name))).convert("RGBA"))
            assert dst_img.shape == (3, 8, 4)
            dst_flat = dst_img.reshape(-1, 4)
            # Remaining padding pixels (indices 21 to 23) must be zero
            np.testing.assert_array_equal(dst_flat[21:], np.zeros((3, 4), dtype=np.uint8))


def test_min_opacity_zero_keeps_all(tmp_path: Path):
    alphas = [0, 1, 5, 6, 255] * 8
    src = tmp_path / "in.sog"
    dst = tmp_path / "out.sog"
    make_synthetic_sog(src, count=40, width=8, height=5, alphas=alphas)

    rep = prune_sog(src, dst, min_opacity=0.0)
    assert rep["in_count"] == 40
    assert rep["out_count"] == 40
    assert rep["removed"] == 0
    assert rep["removed_pct"] == 0.0

    with zipfile.ZipFile(dst, "r") as z:
        out_meta = json.loads(z.read("meta.json"))
        assert out_meta["count"] == 40
        for tex_name in ["means_l.webp", "means_u.webp", "quats.webp", "scales.webp", "sh0.webp"]:
            dst_img = np.asarray(Image.open(io.BytesIO(z.read(tex_name))).convert("RGBA"))
            assert dst_img.shape == (5, 8, 4)


def test_drop_zero_and_max_scale(tmp_path: Path):
    # Test drop_zero: alpha == 0 dropped, alpha > 0 kept when min_opacity=0.0
    alphas = [0] * 10 + [1] * 10 + [5] * 10 + [255] * 10
    src = tmp_path / "in_zero.sog"
    dst = tmp_path / "out_zero.sog"
    make_synthetic_sog(src, count=40, width=8, height=5, alphas=alphas)

    rep = prune_sog(src, dst, min_opacity=0.0, drop_zero=True)
    assert rep["out_count"] == 30
    assert rep["removed"] == 10

    # Test max_scale via scale codebook
    # codebook = [-2.0, -1.0, 0.0, 1.0] -> exp(codebook) = [exp(-2), exp(-1), 1.0, exp(1)=2.718]
    # Set scale_indices: 35 have index 2 (scale 1.0), 5 have index 3 (scale 2.718)
    scale_indices = [[2, 2, 2]] * 35 + [[3, 2, 2]] * 5
    src_scale = tmp_path / "in_scale.sog"
    dst_scale = tmp_path / "out_scale.sog"
    make_synthetic_sog(
        src_scale,
        count=40,
        width=8,
        height=5,
        alphas=[255] * 40,
        scale_indices=scale_indices,
        codebook=[-2.0, -1.0, 0.0, 1.0],
    )

    # Max scale = 2.0 -> the 5 Gaussians with scale 2.718 should be dropped
    rep_s = prune_sog(src_scale, dst_scale, min_opacity=0.0, max_scale=2.0)
    assert rep_s["out_count"] == 35
    assert rep_s["removed"] == 5


def test_atomic_write_and_cleanup_on_error(tmp_path: Path):
    src = tmp_path / "invalid.sog"
    src.write_bytes(b"not a valid zip")
    dst = tmp_path / "out.sog"

    with pytest.raises(SogError):
        prune_sog(src, dst)

    assert not dst.exists()
    # Ensure no temporary files remain in tmp_path
    tmp_files = list(tmp_path.glob("*.tmp*"))
    assert not tmp_files

    # If dst already existed, verify it is unmodified on failure
    dst.write_text("existing content", encoding="utf-8")
    with pytest.raises(SogError):
        prune_sog(src, dst)
    assert dst.read_text(encoding="utf-8") == "existing content"
    tmp_files = list(tmp_path.glob("*.tmp*"))
    assert not tmp_files


def make_corrupt_texture_sog(path: Path) -> None:
    """SOG dengan meta valid tetapi satu tekstur WebP rusak."""
    good = path.with_suffix(".good")
    make_synthetic_sog(good)
    with zipfile.ZipFile(good) as zin, zipfile.ZipFile(path, "w") as zout:
        for name in zin.namelist():
            data = b"RIFFxxxxWEBPgarbage" if name == "quats.webp" else zin.read(name)
            zout.writestr(name, data)
    good.unlink()


@pytest.mark.parametrize(
    "case,setup_fn",
    [
        ("not_a_zip", lambda p: p.write_bytes(b"corrupted")),
        (
            "missing_meta",
            lambda p: zipfile.ZipFile(p, "w").writestr("dummy.txt", "hello"),
        ),
        (
            "has_shN",
            lambda p: make_synthetic_sog(p, include_shN=True),
        ),
        (
            "missing_texture",
            lambda p: make_synthetic_sog(p, missing_texture="means_u.webp"),
        ),
        (
            "invalid_min_opacity_negative",
            lambda p: make_synthetic_sog(p),
        ),
        (
            "invalid_min_opacity_ge_one",
            lambda p: make_synthetic_sog(p),
        ),
        (
            "same_src_and_dst",
            lambda p: make_synthetic_sog(p),
        ),
        (
            "zero_surviving_gaussians",
            lambda p: make_synthetic_sog(p, alphas=[0, 1, 2, 3, 4, 5] * 7),
        ),
        (
            "invalid_count_zero",
            lambda p: make_synthetic_sog(p, meta_override={"count": 0}),
        ),
        (
            "corrupt_texture",
            make_corrupt_texture_sog,
        ),
        (
            "invalid_count_exceeds_wh",
            lambda p: make_synthetic_sog(p, meta_override={"count": 100}),
        ),
    ],
)
def test_sog_error_cases(tmp_path: Path, case: str, setup_fn):
    src = tmp_path / f"src_{case}.sog"
    dst = tmp_path / f"dst_{case}.sog"
    setup_fn(src)

    if case == "invalid_min_opacity_negative":
        with pytest.raises(SogError, match="min_opacity"):
            prune_sog(src, dst, min_opacity=-0.01)
    elif case == "invalid_min_opacity_ge_one":
        with pytest.raises(SogError, match="min_opacity"):
            prune_sog(src, dst, min_opacity=1.0)
    elif case == "same_src_and_dst":
        with pytest.raises(SogError, match="sama"):
            prune_sog(src, src)
    elif case == "zero_surviving_gaussians":
        # All alphas are <= 5, with min_opacity=0.02 all are dropped
        with pytest.raises(SogError, match="nol Gaussian"):
            prune_sog(src, dst, min_opacity=0.02)
    else:
        with pytest.raises(SogError):
            prune_sog(src, dst)

    if case != "same_src_and_dst":
        assert not dst.exists()
    assert not list(tmp_path.glob("*.tmp*"))


def test_cli_main_default_and_report(tmp_path: Path, capsys):
    alphas = [0, 5, 6, 255] * 10
    src = tmp_path / "in.sog"
    dst = tmp_path / "out.sog"
    rep_file = tmp_path / "report.json"
    make_synthetic_sog(src, count=40, width=8, height=5, alphas=alphas)

    code = main([str(src), str(dst), "--report", str(rep_file)])
    assert code == 0
    captured = capsys.readouterr()
    assert "in_count" in captured.out

    assert rep_file.exists()
    rep_data = json.loads(rep_file.read_text(encoding="utf-8"))
    assert rep_data["in_count"] == 40
    assert rep_data["out_count"] == 20
    assert rep_data["rules"]["min_opacity"] == 0.02

    # CLI failure prints error to stderr and returns non-zero
    code_bad = main([str(src), str(src)])
    assert code_bad != 0
    captured_bad = capsys.readouterr()
    assert "Error:" in captured_bad.err


def test_existing_dst_is_untouched_when_pruning_fails(tmp_path: Path):
    src = tmp_path / "bad.sog"
    dst = tmp_path / "scene.sog"
    make_corrupt_texture_sog(src)
    dst.write_bytes(b"previous")

    with pytest.raises(SogError):
        prune_sog(src, dst)

    assert dst.read_bytes() == b"previous"
    assert not list(tmp_path.glob("*.tmp*"))


def test_cli_returns_nonzero_for_corrupt_texture(tmp_path: Path, capsys):
    src = tmp_path / "bad.sog"
    make_corrupt_texture_sog(src)

    assert main([str(src), str(tmp_path / "out.sog")]) != 0
    assert "Error:" in capsys.readouterr().err
