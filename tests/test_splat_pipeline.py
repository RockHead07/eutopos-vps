"""Kontrak jalur dan argv splat, tanpa menjalankan alat pipeline."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from server.pipeline import SPIKE, run_dir

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def splat_pipeline():
    return importlib.import_module("server.splat_pipeline")


def flag_value(argv, flag):
    assert argv.count(flag) == 1, f"expected exactly one {flag}: {argv}"
    return argv[argv.index(flag) + 1]


@pytest.fixture
def commands(splat_pipeline, tmp_path):
    return [
        splat_pipeline.prepare_command(
            tmp_path / "sfm", tmp_path / "dataset", tmp_path / "prepared"
        ),
        splat_pipeline.train_command(tmp_path / "prepared", tmp_path / "result", 30000),
        splat_pipeline.check_command(tmp_path / "cloud.ply", tmp_path / "original-sfm"),
        splat_pipeline.convert_command(tmp_path / "cloud.ply", tmp_path / "scene.sog"),
    ]


def test_train_command_disables_viewer_and_world_normalization(splat_pipeline, tmp_path):
    argv = splat_pipeline.train_command(tmp_path / "prepared", tmp_path / "result", 30000)
    assert "--disable-viewer" in argv
    assert "--no-normalize-world-space" in argv
    assert "--save-ply" in argv
    assert flag_value(argv, "--data-factor") == "1"
    assert flag_value(argv, "--max-steps") == "30000"
    assert flag_value(argv, "--ply-steps") == "30000"


@pytest.mark.parametrize(("steps", "last"), [(30000, 29999), (3000, 2999), (1, 0)])
def test_ply_path_uses_last_step_index(splat_pipeline, tmp_path, steps, last):
    assert splat_pipeline.ply_path(tmp_path, steps) == tmp_path / "ply" / f"point_cloud_{last}.ply"


def test_check_command_uses_default_threshold(splat_pipeline, tmp_path):
    argv = splat_pipeline.check_command(tmp_path / "cloud.ply", tmp_path / "sfm")
    assert not any(arg.startswith("--threshold") for arg in argv)


def test_convert_command_drops_spherical_harmonics(splat_pipeline, tmp_path):
    argv = splat_pipeline.convert_command(tmp_path / "cloud.ply", tmp_path / "scene.sog")
    assert flag_value(argv, "-H") == "0"


def test_every_command_has_a_script_at_argv1(splat_pipeline, commands):
    expected = [
        (sys.executable, SPIKE / "splat_prepare.py"),
        (splat_pipeline.TRAIN_PYTHON, Path(splat_pipeline.TRAINER)),
        (sys.executable, SPIKE / "splat_check_frame.py"),
        ("node", Path(splat_pipeline.SPLAT_TRANSFORM_CLI)),
    ]
    for argv, (interpreter, script) in zip(commands, expected, strict=True):
        assert argv[0] == interpreter
        assert Path(argv[1]) == script


def test_paths_are_under_job_dir(splat_pipeline, tmp_path):
    assert splat_pipeline.work_dir(tmp_path, 37) == tmp_path / "jobs" / "37" / "splat"
    assert splat_pipeline.dataset_dir(tmp_path, 37) == tmp_path / "jobs" / "37" / "dataset"
    assert "MapJob" in splat_pipeline.work_dir.__doc__
    assert "MapJob" in splat_pipeline.dataset_dir.__doc__


def test_train_command_flag_values(splat_pipeline, tmp_path):
    prepared, result, steps = tmp_path / "prepared", tmp_path / "result", 7000
    argv = splat_pipeline.train_command(prepared, result, steps)
    assert Path(flag_value(argv, "--data-dir")) == prepared
    assert flag_value(argv, "--data-factor") == "1"
    assert Path(flag_value(argv, "--result-dir")) == result
    assert flag_value(argv, "--max-steps") == str(steps)
    assert flag_value(argv, "--eval-steps") == str(steps)
    assert flag_value(argv, "--save-steps") == str(steps)
    assert flag_value(argv, "--ply-steps") == str(steps)
    for flag in ["--save-ply", "--no-normalize-world-space", "--disable-viewer", "--disable-video"]:
        assert argv.count(flag) == 1
    assert not any(arg.startswith("--") and "_" in arg for arg in argv)
    assert argv[3:] == [
        "--data-dir",
        str(prepared),
        "--data-factor",
        "1",
        "--result-dir",
        str(result),
        "--max-steps",
        str(steps),
        "--eval-steps",
        str(steps),
        "--save-steps",
        str(steps),
        "--ply-steps",
        str(steps),
        "--save-ply",
        "--no-normalize-world-space",
        "--disable-viewer",
        "--disable-video",
    ]


def test_train_command_starts_with_interpreter_script_and_config(splat_pipeline, tmp_path):
    argv = splat_pipeline.train_command(tmp_path / "prepared", tmp_path / "result", 1)
    assert argv[:3] == [splat_pipeline.TRAIN_PYTHON, splat_pipeline.TRAINER, "default"]


def test_every_argv_item_is_a_str(commands):
    assert all(isinstance(item, str) for argv in commands for item in argv)


def test_prepare_command_images_is_the_dataset_root_and_uses_the_default_max_side(
    splat_pipeline, tmp_path
):
    dataset = splat_pipeline.dataset_dir(tmp_path, 42)
    sfm, out = splat_pipeline.sfm_dir(tmp_path / "map"), splat_pipeline.work_dir(tmp_path, 42)
    argv = splat_pipeline.prepare_command(sfm, dataset, out)
    assert Path(flag_value(argv, "--images")) == dataset
    assert Path(flag_value(argv, "--sfm")) == sfm
    assert Path(flag_value(argv, "--out")) == out
    assert not any(arg.startswith("--max-side") for arg in argv)
    assert argv == [
        sys.executable,
        str(SPIKE / "splat_prepare.py"),
        "--sfm",
        str(sfm),
        "--images",
        str(dataset),
        "--out",
        str(out),
    ]


def test_check_command_has_no_threshold_and_uses_the_given_sfm(splat_pipeline, tmp_path):
    original = splat_pipeline.sfm_dir(tmp_path / "original-map")
    ply = tmp_path / "result" / "cloud.ply"
    argv = splat_pipeline.check_command(ply, original)
    assert Path(flag_value(argv, "--sfm")) == original
    assert Path(flag_value(argv, "--ply")) == ply
    assert argv == [
        sys.executable,
        str(SPIKE / "splat_check_frame.py"),
        "--ply",
        str(ply),
        "--sfm",
        str(original),
    ]


def test_convert_command_exact(splat_pipeline, tmp_path):
    ply, sog = tmp_path / "cloud.ply", tmp_path / "scene.sog"
    assert splat_pipeline.convert_command(ply, sog) == [
        "node",
        splat_pipeline.SPLAT_TRANSFORM_CLI,
        "-g",
        "cpu",
        str(ply),
        "-H",
        "0",
        str(sog),
    ]


def test_convert_command_flag_order(splat_pipeline, tmp_path):
    ply, sog = tmp_path / "cloud.ply", tmp_path / "scene.sog"
    argv = splat_pipeline.convert_command(ply, sog)
    idx_g = argv.index("-g")
    idx_cpu = argv.index("cpu")
    idx_ply = argv.index(str(ply))
    idx_h = argv.index("-H")
    idx_0 = argv.index("0")
    idx_sog = argv.index(str(sog))
    assert idx_g < idx_cpu < idx_ply < idx_h < idx_0 < idx_sog


def test_spike_scripts_referenced_by_commands_exist(commands):
    for argv in [commands[0], commands[2]]:
        assert Path(argv[1]).is_file()


@pytest.mark.parametrize("steps", [0, -1, True, "30000", 30000.0])
@pytest.mark.parametrize("function", ["train_command", "ply_path"])
def test_steps_must_be_a_positive_int(splat_pipeline, tmp_path, steps, function):
    with pytest.raises(ValueError):
        if function == "train_command":
            splat_pipeline.train_command(tmp_path / "prepared", tmp_path / "result", steps)
        else:
            splat_pipeline.ply_path(tmp_path / "result", steps)


def test_work_dir_and_dataset_dir_differ_per_job_and_do_not_overlap(splat_pipeline, tmp_path):
    work = [splat_pipeline.work_dir(tmp_path, job) for job in [1, 2]]
    datasets = [splat_pipeline.dataset_dir(tmp_path, job) for job in [1, 2]]
    assert work[0] != work[1] and datasets[0] != datasets[1]
    for job, w, dataset in zip([1, 2], work, datasets, strict=True):
        assert w.parent == dataset.parent == tmp_path / "jobs" / str(job)
        assert w != dataset
        assert w not in dataset.parents and dataset not in w.parents


def test_sfm_dir_is_under_run_dir_of_the_map(splat_pipeline, tmp_path):
    map_dir = tmp_path / "map"
    assert splat_pipeline.sfm_dir(map_dir) == run_dir(map_dir) / "sfm"


def test_functions_do_not_touch_the_filesystem(splat_pipeline, tmp_path, monkeypatch):
    root = tmp_path / "does-not-exist"

    def forbidden(*args, **kwargs):
        pytest.fail("pipeline function accessed the filesystem")

    with monkeypatch.context() as patch:
        for name in ["open", "exists", "is_file", "is_dir", "mkdir", "iterdir"]:
            patch.setattr(Path, name, forbidden)
        work = splat_pipeline.work_dir(root, 42)
        dataset = splat_pipeline.dataset_dir(root, 42)
        sfm = splat_pipeline.sfm_dir(root / "map")
        splat_pipeline.prepare_command(sfm, dataset, work / "prepared")
        splat_pipeline.train_command(work / "prepared", work / "result", 1)
        ply = splat_pipeline.ply_path(work / "result", 1)
        splat_pipeline.check_command(ply, sfm)
        splat_pipeline.convert_command(ply, work / "scene.sog")
    assert list(tmp_path.iterdir()) == []


def test_module_imports_without_heavy_dependencies():
    code = (
        "import sys, server.splat_pipeline; "
        "bad = {'torch','gsplat','numpy','PIL','pycolmap','cv2'} & set(sys.modules); "
        "assert not bad, bad; "
        "assert not any(m == 'spike' or m.startswith('spike.') for m in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
