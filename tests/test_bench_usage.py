"""Uji bagian murni skrip ukur CPU/GPU (spike/bench_usage.py): tanpa GPU dan tanpa model."""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spike"))
import bench_usage as b


def frames(videos: dict[str, int]) -> list[str]:
    return sorted(f"{v}_{i:05d}.jpg" for v, n in videos.items() for i in range(n))


def fake_variances(names, lo=50.0, hi=950.0):
    # ketajaman naik turun sepanjang rute, supaya pemilihan punya rentang untuk disebar
    rng = np.random.default_rng(3)
    return {n: float(v) for n, v in zip(names, rng.uniform(lo, hi, len(names)), strict=True)}


# ---- pemilihan pasangan ------------------------------------------------------------------------


def test_pairs_are_exactly_gap_apart_within_one_video():
    names = frames({"a": 40, "b": 40})
    got = b.select_pairs(names, fake_variances(names), n_pairs=15, gap=2, seed=7)
    assert len(got) == 15
    for x, y in got:
        assert b.video_of(x) == b.video_of(y)
        assert int(y[-9:-4]) - int(x[-9:-4]) == 2


def test_selection_is_deterministic_and_seed_dependent():
    names = frames({"a": 120})
    v = fake_variances(names)
    one = b.select_pairs(names, v, 15, 2, seed=1)
    assert one == b.select_pairs(names, v, 15, 2, seed=1)
    assert one != b.select_pairs(names, v, 15, 2, seed=2)


def test_pairs_are_spread_along_the_route_one_per_slice():
    names = frames({"a": 150})
    got = b.select_pairs(names, fake_variances(names), 15, 2, seed=7)
    starts = [int(x[-9:-4]) for x, _ in got]
    assert starts == sorted(starts)
    slices = {s * 15 // 148 for s in starts}  # 148 = kandidat awal pasangan (150 - gap)
    assert len(slices) == 15


def test_sharpness_range_is_covered_not_just_the_typical_frames():
    names = frames({"a": 300})
    v = fake_variances(names)
    got = b.select_pairs(names, v, 15, 2, seed=7)
    chosen = sorted(v[x] for x, _ in got)
    allv = sorted(v[n] for n in names[:-2])
    span = allv[-1] - allv[0]
    assert chosen[0] - allv[0] < 0.15 * span  # ada yang buram
    assert allv[-1] - chosen[-1] < 0.15 * span  # ada yang tajam


def test_too_few_candidates_is_an_error_not_a_silent_shortfall():
    names = frames({"a": 10})
    with pytest.raises(ValueError, match="15"):
        b.select_pairs(names, fake_variances(names), n_pairs=15, gap=2, seed=7)


def test_gap_never_crosses_into_another_video():
    names = frames({"a": 3, "b": 3})  # a_00002 + 2 tidak boleh jadi b_00000
    got = b.select_pairs(names, fake_variances(names), n_pairs=2, gap=2, seed=7)
    assert sorted(got) == [("a_00000.jpg", "a_00002.jpg"), ("b_00000.jpg", "b_00002.jpg")]


# ---- noise dari OpenCV -------------------------------------------------------------------------


def gray(value=128, size=(120, 160)):
    return np.full((*size, 3), value, dtype=np.uint8)


@pytest.mark.parametrize("sigma", [10, 25, 50])
def test_gaussian_noise_has_the_requested_sigma(sigma):
    out = b.gaussian_noise(gray(), sigma, seed=5)
    assert out.dtype == np.uint8 and out.shape == (120, 160, 3)
    measured = float(np.std(out.astype(np.float64) - 128))
    assert measured == pytest.approx(sigma, rel=0.1)


def test_gaussian_noise_is_reproducible_and_does_not_touch_the_input():
    img = gray()
    a1, a2 = b.gaussian_noise(img, 25, seed=5), b.gaussian_noise(img, 25, seed=5)
    assert np.array_equal(a1, a2) and not np.array_equal(a1, b.gaussian_noise(img, 25, seed=6))
    assert np.array_equal(img, gray())


def test_gaussian_noise_clips_instead_of_wrapping():
    out = b.gaussian_noise(gray(250), 50, seed=5)
    assert out.max() == 255
    # Overflow uint8 melempar sekitar sepertiga piksel ke nilai kecil. Tanpa overflow, nilai di
    # bawah 40 (lebih dari 4 sigma dari 250) praktis tidak ada.
    assert (out < 40).mean() < 0.001


def test_salt_and_pepper_flips_about_the_requested_fraction_to_extremes():
    out = b.salt_pepper(gray(), 0.02, seed=5)
    changed = np.any(out != 128, axis=2)
    assert changed.mean() == pytest.approx(0.02, abs=0.006)
    assert set(np.unique(out[changed])) <= {0, 255}
    both = {int(out[changed][:, 0].min()), int(out[changed][:, 0].max())}
    assert both == {0, 255}  # ada garam dan merica


def test_variants_clean_is_identity_and_names_are_stable():
    img = gray()
    assert np.array_equal(b.make_variant(img, "clean", seed=1), img)
    assert list(b.VARIANTS) == ["clean", "gauss10", "gauss25", "gauss50", "sp2"]
    noisy = b.make_variant(img, "gauss25", seed=1)
    assert not np.array_equal(noisy, img)
    with pytest.raises(KeyError):
        b.make_variant(img, "tidak-ada", seed=1)


# ---- sampler GPU dan agregasi ------------------------------------------------------------------


def test_gpu_window_uses_only_samples_inside_the_stage():
    samples = [(0.0, 5.0), (1.0, 40.0), (2.0, 80.0), (3.0, 60.0), (9.0, 99.0)]
    mean, peak = b.window_stats(samples, 1.0, 3.0)
    assert (mean, peak) == (pytest.approx(60.0), 80.0)


def test_gpu_window_without_samples_is_unknown_not_zero():
    assert b.window_stats([], 0.0, 1.0) == (None, None)
    assert b.window_stats([(5.0, 10.0)], 0.0, 1.0) == (None, None)


def test_parse_nvidia_smi_line():
    assert b.parse_smi_line("37, 2288") == (37.0, 2288.0)
    assert b.parse_smi_line("  0 ,  15 \n") == (0.0, 15.0)
    assert b.parse_smi_line("[N/A], 15") is None
    assert b.parse_smi_line("") is None


def rec(wall, cpu, **kw):
    base = {"config": "c", "device": "cpu", "variant": "clean", "stage": "extract", "repeat": 0}
    return {**base, "wall_s": wall, "cpu_s": cpu, **kw}


def test_aggregate_reports_median_and_range_over_repeats():
    out = b.aggregate([rec(1.0, 8.0, repeat=0), rec(3.0, 24.0, repeat=1), rec(2.0, 16.0, repeat=2)])
    assert len(out) == 1
    row = out[0]
    assert row["repeats"] == 3
    assert (row["wall_s"], row["wall_min"], row["wall_max"]) == (2.0, 1.0, 3.0)
    assert row["cpu_cores"] == pytest.approx(8.0)  # CPU time dibagi waktu dinding


def test_aggregate_keeps_missing_gpu_numbers_missing():
    out = b.aggregate([rec(1.0, 1.0, gpu_util_mean=None, vram_peak_mb=None)])
    assert out[0]["gpu_util_mean"] is None and out[0]["vram_peak_mb"] is None


def test_aggregate_separates_devices_variants_and_stages():
    rows = [
        rec(1, 1),
        rec(1, 1, device="gpu"),
        rec(1, 1, variant="gauss25"),
        rec(1, 1, stage="match"),
    ]
    assert len(b.aggregate(rows)) == 4


def test_per_item_time_uses_the_item_count_of_each_stage():
    out = b.aggregate([rec(8.0, 8.0, items=8), rec(4.0, 4.0, items=8, repeat=1)])
    assert out[0]["items"] == 8 and out[0]["per_item_s"] == pytest.approx(0.75)
    assert b.aggregate([rec(1.0, 1.0)])[0]["per_item_s"] is None  # tanpa jumlah item: tidak ditebak


@pytest.mark.skipif(b.resource is None, reason="RUSAGE_CHILDREN hanya ada di Linux dan macOS")
def test_cpu_seconds_counts_child_processes_that_have_finished():
    # Pekerja DataLoader hloc adalah proses anak. Tanpa menghitungnya CPU terlihat terlalu kecil.
    import subprocess
    import sys

    before = b.cpu_seconds()
    burn = "x = sum(i * i for i in range(4_000_000))"
    subprocess.run([sys.executable, "-c", burn], check=True)
    assert b.cpu_seconds() - before > 0.1


def test_cpu_seconds_never_goes_backwards_and_is_a_number():
    first = b.cpu_seconds()
    sum(i * i for i in range(200_000))
    assert b.cpu_seconds() >= first


# ---- konfigurasi -------------------------------------------------------------------------------


def test_the_five_configs_match_the_earlier_experiment():
    assert list(b.CONFIGS) == [
        "aliked-lightglue",
        "sift-lightglue",
        "aliked-nn",
        "sift-nn",
        "sift-colmap-default",
    ]
    assert b.CONFIGS["aliked-lightglue"] == ("aliked", "lightglue", 1024, 1024)
    assert b.CONFIGS["sift-colmap-default"] == ("sift", "nn-ratio", 8192, 2560)


def test_confs_follow_run_py_settings():
    local, matcher = b.build_confs("aliked", "lightglue", 1024, 1024)
    assert local["model"]["max_num_keypoints"] == 1024
    assert local["preprocessing"]["resize_max"] == 1024
    sift, sift_matcher = b.build_confs("sift", "nn-ratio", 8192, 2560)
    assert sift["model"]["options"] == {"max_num_features": 8192}
    assert sift["preprocessing"]["resize_max"] == 2560
    _, sift_lg = b.build_confs("sift", "lightglue", 1024, 1024)
    assert sift_lg["model"]["features"] == "sift"
    assert matcher != sift_matcher


# ---- pengukur ketajaman pakai ulang extract_frames --------------------------------------------


def test_sharpness_is_higher_for_textured_than_for_flat_images():
    rng = np.random.default_rng(0)
    textured = rng.integers(0, 255, (200, 300, 3), dtype=np.uint8)
    blurred = cv2.GaussianBlur(textured, (0, 0), 6)
    assert b.sharpness(textured) > b.sharpness(blurred) > b.sharpness(gray())
