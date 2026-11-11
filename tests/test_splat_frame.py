import struct
import sys
from pathlib import Path

import numpy as np
import pytest

from spike import splat_check_frame
from spike.splat_check_frame import load_ply_means, median_nn_distance
from spike.splat_prepare import missing_images, prepare_splat_data


def test_median_nn_distance_small_noise():
    rng = np.random.default_rng(42)
    points = rng.uniform(0.0, 1.0, size=(500, 3))
    box_width = float(np.max(points.max(axis=0) - points.min(axis=0)))

    noise = rng.normal(scale=0.005, size=points.shape)
    means = points + noise

    dist = median_nn_distance(points, means)
    assert dist < 0.02 * box_width


def test_median_nn_distance_large_shift():
    rng = np.random.default_rng(42)
    points = rng.uniform(0.0, 1.0, size=(500, 3))
    box_width = float(np.max(points.max(axis=0) - points.min(axis=0)))

    means = points + np.array([1.0, 0.0, 0.0])

    dist = median_nn_distance(points, means)
    assert dist > 0.5 * box_width


def test_median_nn_distance_empty_raises():
    points = np.zeros((10, 3))
    empty = np.empty((0, 3))

    with pytest.raises(ValueError):
        median_nn_distance(points, empty)

    with pytest.raises(ValueError):
        median_nn_distance(empty, points)


def test_missing_images_all_present(tmp_path: Path):
    images_dir = tmp_path / "images"
    (images_dir / "mapping").mkdir(parents=True)
    (images_dir / "mapping" / "f1.jpg").write_text("fake")
    (images_dir / "mapping" / "f2.jpg").write_text("fake")

    names = ["mapping/f1.jpg", "mapping/f2.jpg"]
    missing = missing_images(names, images_dir)
    assert missing == []


def test_missing_images_some_missing(tmp_path: Path):
    images_dir = tmp_path / "images"
    (images_dir / "mapping").mkdir(parents=True)
    (images_dir / "mapping" / "f1.jpg").write_text("fake")

    names = ["mapping/f1.jpg", "mapping/f2.jpg"]
    missing = missing_images(names, images_dir)
    assert missing == ["mapping/f2.jpg"]


def test_load_ply_means_binary_little_endian(tmp_path: Path):
    ply_path = tmp_path / "test_gsplat.ply"
    props = [
        "x",
        "y",
        "z",
        "nx",
        "ny",
        "nz",
        "f_dc_0",
        "f_dc_1",
        "f_dc_2",
        "opacity",
        "scale_0",
        "scale_1",
        "scale_2",
        "rot_0",
        "rot_1",
        "rot_2",
        "rot_3",
    ]
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "element vertex 2\n" + "".join(f"property float {p}\n" for p in props) + "end_header\n"
    )
    v0 = struct.pack("<17f", 1.0, 2.0, 3.0, *([0.0] * 14))
    v1 = struct.pack("<17f", -4.5, 5.5, 6.5, *([0.0] * 14))

    with open(ply_path, "wb") as f:
        f.write(header.encode("latin1"))
        f.write(v0)
        f.write(v1)

    means = load_ply_means(ply_path)
    assert means.shape == (2, 3)
    np.testing.assert_allclose(means[0], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(means[1], [-4.5, 5.5, 6.5])


def test_load_ply_means_ascii(tmp_path: Path):
    ply_path = tmp_path / "test_ascii.ply"
    content = (
        "ply\n"
        "format ascii 1.0\n"
        "element vertex 2\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
        "10.0 20.0 30.0\n"
        "-1.0 -2.0 -3.0\n"
    )
    ply_path.write_text(content, encoding="latin1")

    means = load_ply_means(ply_path)
    assert means.shape == (2, 3)
    np.testing.assert_allclose(means[0], [10.0, 20.0, 30.0])
    np.testing.assert_allclose(means[1], [-1.0, -2.0, -3.0])


def test_load_ply_means_missing_end_header_raises(tmp_path: Path):
    ply_path = tmp_path / "truncated.ply"
    content = "ply\nformat ascii 1.0\nelement vertex 2\nproperty float x\n"
    ply_path.write_text(content, encoding="latin1")

    with pytest.raises(ValueError, match="end_header"):
        load_ply_means(ply_path)


def test_main_returns_0_when_frame_matches(monkeypatch, capsys):
    points = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]])
    monkeypatch.setattr(splat_check_frame, "load_ply_means", lambda _: points + 0.001)
    monkeypatch.setattr(splat_check_frame, "load_colmap_points", lambda _: points)
    monkeypatch.setattr(sys, "argv", ["splat_check_frame", "--ply", "fake.ply", "--sfm", "fake"])

    assert splat_check_frame.main() == 0
    captured = capsys.readouterr()
    assert "PASS" in captured.out
    assert captured.err == ""


def test_main_returns_1_when_frame_is_shifted(monkeypatch, capsys):
    points = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]])
    monkeypatch.setattr(splat_check_frame, "load_ply_means", lambda _: points + 100.0)
    monkeypatch.setattr(splat_check_frame, "load_colmap_points", lambda _: points)
    monkeypatch.setattr(sys, "argv", ["splat_check_frame", "--ply", "fake.ply", "--sfm", "fake"])

    assert splat_check_frame.main() == 1
    assert "FAIL" in capsys.readouterr().out


def test_main_returns_1_when_model_has_no_points(monkeypatch, capsys):
    monkeypatch.setattr(splat_check_frame, "load_ply_means", lambda _: np.ones((3, 3)))
    monkeypatch.setattr(splat_check_frame, "load_colmap_points", lambda _: np.empty((0, 3)))
    monkeypatch.setattr(sys, "argv", ["splat_check_frame", "--ply", "fake.ply", "--sfm", "fake"])

    assert splat_check_frame.main() == 1
    assert "COLMAP model has no 3D points" in capsys.readouterr().err


def test_main_returns_1_when_ply_has_no_means(monkeypatch, capsys):
    points = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]])
    monkeypatch.setattr(splat_check_frame, "load_ply_means", lambda _: np.empty((0, 3)))
    monkeypatch.setattr(splat_check_frame, "load_colmap_points", lambda _: points)
    monkeypatch.setattr(sys, "argv", ["splat_check_frame", "--ply", "fake.ply", "--sfm", "fake"])

    assert splat_check_frame.main() == 1
    assert "PLY file has no Gaussian means" in capsys.readouterr().err


def test_main_threshold_is_configurable(monkeypatch, capsys):
    points = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]])
    monkeypatch.setattr(splat_check_frame, "load_ply_means", lambda _: points + 0.1)
    monkeypatch.setattr(splat_check_frame, "load_colmap_points", lambda _: points)
    argv = ["splat_check_frame", "--ply", "fake.ply", "--sfm", "fake", "--threshold"]

    monkeypatch.setattr(sys, "argv", [*argv, "0.5"])
    assert splat_check_frame.main() == 0
    assert "PASS" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", [*argv, "0.001"])
    assert splat_check_frame.main() == 1
    assert "FAIL" in capsys.readouterr().out


def test_main_default_threshold_is_0_02(monkeypatch, capsys):
    """Kriteria keselamatan rencana: rasio >= 0,02 berarti splat di kerangka yang salah."""
    points = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]])
    monkeypatch.setattr(splat_check_frame, "load_colmap_points", lambda _: points)
    monkeypatch.setattr(sys, "argv", ["splat_check_frame", "--ply", "fake.ply", "--sfm", "fake"])
    shift_x = np.array([1.0, 0.0, 0.0])

    # lebar kotak 10: geser 0,1 memberi rasio 0,01 (lulus), geser 0,3 memberi 0,03 (gagal)
    monkeypatch.setattr(splat_check_frame, "load_ply_means", lambda _: points + 0.1 * shift_x)
    assert splat_check_frame.main() == 0
    assert "threshold: 0.02" in capsys.readouterr().out

    monkeypatch.setattr(splat_check_frame, "load_ply_means", lambda _: points + 0.3 * shift_x)
    assert splat_check_frame.main() == 1
    assert "FAIL" in capsys.readouterr().out


def test_prepare_raises_when_sfm_dir_missing(tmp_path):
    images = tmp_path / "images"
    images.mkdir()

    with pytest.raises(FileNotFoundError, match="SfM directory not found"):
        prepare_splat_data(tmp_path / "missing-sfm", images, tmp_path / "out")


def test_prepare_raises_when_images_dir_missing(tmp_path):
    sfm = tmp_path / "sfm"
    sfm.mkdir()

    with pytest.raises(FileNotFoundError, match="Images directory not found"):
        prepare_splat_data(sfm, tmp_path / "missing-images", tmp_path / "out")
