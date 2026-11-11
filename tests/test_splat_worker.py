"""Splat orchestration with SQLite, synthetic SOG and fake external tools."""

import ast
import importlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import SQLModel, create_engine, delete, select
from test_splat_prune import make_synthetic_sog

from server import splat_jobs, worker
from server import splat_pipeline as pipeline
from server.db import Area, MapJob, MapVersion, SplatJob
from server.jobs import ERROR_MAX
from spike.splat_prune import SogError

STAGES = ["inputs", "prepare", "gpu_wait", "train", "check", "convert", "prune", "place"]
SCRIPTS = {
    "prepare": "splat_prepare.py",
    "train": Path(pipeline.TRAINER).name,
    "check": "splat_check_frame.py",
    "convert": Path(pipeline.SPLAT_TRANSFORM_CLI).name,
}


@pytest.fixture
def sw():
    return importlib.import_module("server.splat_worker")


def make_case(tmp_path, file_db=False):
    url = f"sqlite:///{tmp_path / 'db.sqlite'}" if file_db else "sqlite://"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    session = worker.worker_session(engine)
    data, maps = tmp_path / "data", tmp_path / "maps"
    map_dir = maps / "floor10" / "job-7"
    mapping = pipeline.dataset_dir(data, 7) / "mapping"
    mapping.mkdir(parents=True)
    (mapping / "f_0.jpg").write_bytes(b"frame")
    sfm = pipeline.sfm_dir(map_dir)
    sfm.mkdir(parents=True)
    session.add(Area(id="floor10", name="Test floor"))
    session.commit()
    version = MapVersion(area_id="floor10", version=1, path=str(map_dir))
    session.add(version)
    session.commit()
    map_job = MapJob(
        id=7, area_id="floor10", created_by="test", status="done", map_version_id=version.id
    )
    session.add(map_job)
    session.commit()
    job = splat_jobs.enqueue(session, version.id, {"steps": 17, "min_opacity": 0.1})
    assert splat_jobs.claim_next(session) is job
    return SimpleNamespace(
        session=session,
        engine=engine,
        data=data,
        maps=maps,
        map_dir=map_dir,
        version=version,
        map_job=map_job,
        job=job,
        work=pipeline.work_dir(data, 7),
        mapping=mapping,
        sfm=sfm,
    )


@pytest.fixture
def case(tmp_path):
    c = make_case(tmp_path)
    yield c
    c.session.close()
    c.engine.dispose()


@pytest.fixture
def file_case(tmp_path):
    c = make_case(tmp_path, file_db=True)
    yield c
    c.session.close()
    c.engine.dispose()


class FakeGpuLock:
    def __init__(self, on_enter=None, error=None):
        self.held = False
        self.events = []
        self.on_enter = on_enter
        self.error = error

    def __enter__(self):
        self.events.append("enter")
        if self.on_enter is not None:
            self.on_enter()
        if self.error is not None:
            raise self.error
        self.held = True

    def __exit__(self, exc_type, exc, traceback):
        assert self.held
        self.held = False
        self.events.append("exit")


def flag_value(argv, flag):
    assert argv.count(flag) == 1
    return argv[argv.index(flag) + 1]


def fake_runner(calls, fail_on=None, ratios=(0.001234,), after=None, stats=True):
    def run(argv, log):
        script = Path(argv[1]).name
        calls.append(list(argv))
        if script == SCRIPTS["check"]:
            with log.open("a", encoding="utf-8") as stream:
                for ratio in ratios:
                    stream.write(f"Ratio (distance / box_width): {ratio} (threshold: 0.02)\n")
        if script == SCRIPTS.get(fail_on):
            raise worker.StageError(f"failed test stage: {fail_on}")
        if script == SCRIPTS["prepare"]:
            out = Path(flag_value(argv, "--out"))
            (out / "images").mkdir(parents=True)
            (out / "sparse" / "0").mkdir(parents=True)
        elif script == SCRIPTS["train"]:
            result = Path(flag_value(argv, "--result-dir"))
            ply = pipeline.ply_path(result, int(flag_value(argv, "--max-steps")))
            ply.parent.mkdir(parents=True)
            ply.write_bytes(b"ply")
            if stats:
                step = int(flag_value(argv, "--max-steps")) - 1
                (result / "stats").mkdir(parents=True)
                (result / "stats" / f"val_step{step}.json").write_text(
                    json.dumps(
                        {
                            "psnr": 24.88562774658203,
                            "ssim": 0.8861821889877319,
                            "lpips": 0.2750255763530731,
                            "ellipse_time": 0.02,
                            "num_GS": 901798,
                        }
                    )
                )
                (result / "stats" / f"train_step{step}_rank0.json").write_text(
                    json.dumps({"mem": 1.5070815086364746, "ellipse_time": 939.4, "num_GS": 901798})
                )
        elif script == SCRIPTS["convert"]:
            make_synthetic_sog(Path(argv[-1]))
        if after is not None:
            after(script, argv, log)

    return run


def process(sw, c, **kwargs):
    options = dict(
        runner=fake_runner([]),
        lock=lambda: FakeGpuLock(),
        free_bytes=lambda p: 10**12,
        free_vram=lambda: 8000,
    )
    options.update(kwargs)
    sw.process(c.session, c.job, c.data, c.maps, **options)


def test_happy_path_writes_scene_sog_and_report_and_removes_work_dir(sw, case, monkeypatch):
    stages, calls = [], []
    case.session.refresh(case.map_job)
    case.session.refresh(case.version)
    case.session.commit()
    unchanged = (case.map_job.model_dump(), case.version.model_dump())
    real_mkdir = Path.mkdir

    def mkdir(path, *args, **kwargs):
        assert path != case.map_dir, "the version folder must never be created by splat"
        if path == case.map_dir / "splat":
            assert not kwargs.get("parents", False)
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    real_stage, real_finish, real_prune = splat_jobs.set_stage, splat_jobs.finish, sw.prune_sog
    prune_reports = []

    def stage(session, job, name):
        stages.append(name)
        real_stage(session, job, name)

    def finish(session, job, summary):
        assert case.work.is_dir(), "finish must commit before work is removed"
        real_finish(session, job, summary)

    def prune(src, dst, **kwargs):
        assert kwargs == {"min_opacity": 0.1}
        result = real_prune(src, dst, **kwargs)
        prune_reports.append(result)
        return result

    monkeypatch.setattr(splat_jobs, "set_stage", stage)
    monkeypatch.setattr(splat_jobs, "finish", finish)
    monkeypatch.setattr(sw, "prune_sog", prune)
    ticks = iter(range(1000))
    process(sw, case, runner=fake_runner(calls), clock=lambda: next(ticks))
    assert case.job.status == "done", case.job.error
    assert stages == STAGES
    assert [Path(a[1]).name for a in calls] == list(SCRIPTS.values())
    assert Path(flag_value(calls[0], "--images")) == pipeline.dataset_dir(case.data, 7)
    assert Path(flag_value(calls[0], "--sfm")) == case.sfm
    assert flag_value(calls[1], "--max-steps") == "17"
    assert Path(flag_value(calls[2], "--sfm")) == case.sfm
    splat = case.map_dir / "splat"
    with zipfile.ZipFile(splat / "scene.sog") as archive:
        assert "meta.json" in archive.namelist()
        assert json.loads(archive.read("meta.json"))["count"] == prune_reports[0]["out_count"]
    report = json.loads((splat / "report.json").read_text())
    assert set(report) == {
        "steps",
        "min_opacity",
        "check_ratio",
        "gaussians_before",
        "gaussians_after",
        "bytes_before",
        "bytes_after",
        "stage_seconds",
        "built_at",
        "metrics",
        "vram_free_mib",
    }
    assert report["metrics"] == {
        "psnr": 24.886,
        "ssim": 0.8862,
        "lpips": 0.275,
        "peak_mem_gb": 1.507,
    }
    assert report["vram_free_mib"] == 8000
    assert report["steps"] == 17 and report["min_opacity"] == 0.1
    assert report["check_ratio"] == 0.001234
    for target, source in [
        ("gaussians_before", "in_count"),
        ("gaussians_after", "out_count"),
        ("bytes_before", "in_bytes"),
        ("bytes_after", "out_bytes"),
    ]:
        assert report[target] == prune_reports[0][source]
    assert report["stage_seconds"] == dict.fromkeys(STAGES, 1)
    assert datetime.fromisoformat(report["built_at"]).utcoffset().total_seconds() == 0
    assert case.job.summary == report
    case.session.refresh(case.map_job)
    case.session.refresh(case.version)
    assert (case.map_job.model_dump(), case.version.model_dump()) == unchanged
    assert not case.work.exists()
    assert sorted(p.name for p in splat.iterdir()) == ["report.json", "scene.sog"]


@pytest.mark.parametrize("stage", ["prepare", "train", "check", "convert", "prune"])
def test_stage_failure_marks_job_failed_with_that_stage_and_leaves_map_untouched(
    sw, case, monkeypatch, stage
):
    case.session.refresh(case.map_job)
    case.session.refresh(case.version)
    case.session.commit()
    before = (case.map_job.model_dump(), case.version.model_dump())
    if stage == "prune":

        def bad_prune(*args, **kwargs):
            raise SogError("failed test stage: prune")

        monkeypatch.setattr(sw, "prune_sog", bad_prune)
    process(sw, case, runner=fake_runner([], fail_on=stage))
    assert case.job.status == "failed"
    assert case.job.stage == stage
    assert f"failed test stage: {stage}" in case.job.error
    case.session.refresh(case.map_job)
    case.session.refresh(case.version)
    assert (case.map_job.model_dump(), case.version.model_dump()) == before
    assert case.work.is_dir()
    assert not (case.map_dir / "splat" / "scene.sog").exists()


def test_check_failure_when_ratio_fails_leaves_no_scene_sog(sw, case):
    process(sw, case, runner=fake_runner([], fail_on="check", ratios=(0.5,)))
    assert case.job.status == "failed" and case.job.stage == "check"
    assert not (case.map_dir / "splat" / "scene.sog").exists()
    assert not (case.map_dir / "splat" / "report.json").exists()


def test_lock_is_held_only_around_train(sw, case, monkeypatch):
    def on_enter():
        assert case.job.stage == "gpu_wait"

    gate = FakeGpuLock(on_enter=on_enter)
    delegate, prune, replace = fake_runner([]), sw.prune_sog, sw.os.replace

    def run(argv, log):
        assert gate.held == (Path(argv[1]).name == SCRIPTS["train"])
        if gate.held:
            assert case.job.stage == "train"
        delegate(argv, log)

    def unlocked_prune(*args, **kwargs):
        assert not gate.held
        return prune(*args, **kwargs)

    def unlocked_replace(*args):
        assert not gate.held
        return replace(*args)

    monkeypatch.setattr(sw, "prune_sog", unlocked_prune)
    monkeypatch.setattr(sw.os, "replace", unlocked_replace)
    process(sw, case, runner=run, lock=lambda: gate)
    assert case.job.status == "done", case.job.error
    assert gate.events == ["enter", "exit"] and not gate.held


def test_default_lock_is_built_from_the_session_bind(sw, case, monkeypatch):
    received = []

    def lock(engine):
        received.append(engine)
        return FakeGpuLock()

    monkeypatch.setattr(sw, "gpu_lock", lock)
    process(sw, case, lock=None)
    assert case.job.status == "done", case.job.error
    assert received == [case.session.get_bind()]
    assert received[0] is case.engine


def test_place_is_atomic_old_scene_sog_survives_a_failed_rebuild(sw, case, monkeypatch):
    splat = case.map_dir / "splat"
    splat.mkdir()
    (splat / "scene.sog").write_bytes(b"old-scene")
    (splat / "report.json").write_text('{"old": true}')
    real_replace = sw.os.replace

    def bad_replace(src, dst):
        if Path(dst).name == "scene.sog":
            assert json.loads((splat / "report.json").read_text())["steps"] == 17
            raise OSError("scene replace failed")
        return real_replace(src, dst)

    monkeypatch.setattr(sw.os, "replace", bad_replace)
    process(sw, case)
    assert case.job.status == "failed" and case.job.stage == "place"
    assert "scene replace failed" in case.job.error
    assert (splat / "scene.sog").read_bytes() == b"old-scene"
    assert json.loads((splat / "report.json").read_text())["check_ratio"] == 0.001234
    assert sorted(p.name for p in splat.iterdir()) == ["report.json", "scene.sog"]
    assert case.work.exists()


def test_place_temp_files_live_next_to_the_destination(sw, case, monkeypatch):
    replacements, real_replace = [], sw.os.replace

    def replace(src, dst):
        src, dst = Path(src), Path(dst)
        if dst.name == "scene-pruned.sog":
            return real_replace(src, dst)
        assert src.parent == dst.parent == case.map_dir / "splat"
        assert src.name.startswith(f".{dst.name}.tmp.")
        assert len(src.name.rsplit(".", 1)[1]) == 32
        replacements.append(dst.name)
        real_replace(src, dst)

    monkeypatch.setattr(sw.os, "replace", replace)
    process(sw, case)
    assert case.job.status == "done", case.job.error
    assert replacements == ["report.json", "scene.sog"]


def test_place_refuses_when_version_folder_is_gone(sw, case):
    def after(script, argv, log):
        if script == SCRIPTS["convert"]:
            shutil.rmtree(case.map_dir)

    process(sw, case, runner=fake_runner([], after=after))
    assert case.job.status == "failed" and case.job.stage == "place"
    assert "map folder is gone; nothing was placed" in case.job.error
    assert not case.map_dir.exists()


def test_place_refuses_when_the_version_row_is_deleted_mid_run(sw, file_case):
    c = file_case
    version_id = c.version.id

    def after(script, argv, log):
        if script == SCRIPTS["train"]:
            with worker.worker_session(c.engine) as other:
                other.exec(delete(MapVersion).where(MapVersion.id == version_id))
                other.commit()
            assert c.session.get(MapVersion, version_id) is c.version

    process(sw, c, runner=fake_runner([], after=after))
    assert c.job.status == "failed" and c.job.stage == "place"
    assert "map folder is gone" in c.job.error
    assert not (c.map_dir / "splat" / "scene.sog").exists()


def test_failure_when_the_splat_job_row_was_deleted_does_not_raise(sw, file_case, capsys):
    c = file_case
    job_id = c.job.id

    def after(script, argv, log):
        if script == SCRIPTS["train"]:
            with worker.worker_session(c.engine) as other:
                other.exec(delete(SplatJob).where(SplatJob.id == job_id))
                other.commit()
            raise RuntimeError("deleted during training")

    process(sw, c, runner=fake_runner([], after=after))
    warning = capsys.readouterr().err
    assert len(warning.splitlines()) == 1 and "warning" in warning.lower()
    assert c.session.exec(select(SplatJob.id).where(SplatJob.id == job_id)).first() is None
    assert not (c.map_dir / "splat" / "scene.sog").exists()


@pytest.mark.parametrize(
    ("problem", "message"),
    [
        ("version_row_missing", "map version no longer exists"),
        ("no_map_job", "this map version has no build job, so there are no frames to train on"),
        ("outside", "refusing to write outside the maps folder:"),
        ("traversal", "refusing to write outside the maps folder:"),
        ("maps_root", "refusing to write outside the maps folder:"),
        ("frames_missing", "frames for this map are gone:"),
        ("mapping_folder_empty", "frames for this map are gone:"),
        ("sfm_missing", "sfm model for this map is missing:"),
        ("low_disk", "less than 20 GB of free disk; job not started"),
    ],
)
def test_inputs_fail_before_work_is_created(sw, file_case, problem, message):
    c = file_case
    if problem == "version_row_missing":
        with worker.worker_session(c.engine) as other:
            other.exec(delete(MapVersion).where(MapVersion.id == c.version.id))
            other.commit()
        assert c.session.get(MapVersion, c.version.id) is c.version
    elif problem == "no_map_job":
        c.session.delete(c.map_job)
        c.session.commit()
    elif problem in {"outside", "traversal", "maps_root"}:
        paths = {
            "outside": c.maps.parent / "other",
            "traversal": c.maps / ".." / "x",
            "maps_root": c.maps,
        }
        c.version.path = str(paths[problem])
        c.session.add(c.version)
        c.session.commit()
    elif problem == "frames_missing":
        shutil.rmtree(c.mapping)
    elif problem == "mapping_folder_empty":
        (c.mapping / "f_0.jpg").unlink()
        (c.mapping / "not-a-file").mkdir()
    elif problem == "sfm_missing":
        shutil.rmtree(c.sfm)

    def forbidden(*args):
        pytest.fail("runner must not execute during inputs validation")

    process(sw, c, runner=forbidden, free_bytes=lambda p: 10 if problem == "low_disk" else 10**12)
    assert c.job.status == "failed" and c.job.stage == "inputs"
    assert message in c.job.error
    assert not c.work.exists()


def test_work_dir_kept_on_failure_and_removed_on_rebuild(sw, case):
    def after(script, argv, log):
        if script == SCRIPTS["prepare"]:
            (case.work / "sentinel").write_text("failed attempt")

    process(sw, case, runner=fake_runner([], fail_on="train", after=after))
    assert case.job.status == "failed"
    assert (case.work / "sentinel").is_file()
    splat_jobs.enqueue(case.session, case.version.id, {"steps": 17})
    splat_jobs.claim_next(case.session)
    delegate = fake_runner([])

    def retry(argv, log):
        if Path(argv[1]).name == SCRIPTS["prepare"]:
            assert not (case.work / "sentinel").exists()
        delegate(argv, log)

    process(sw, case, runner=retry)
    assert case.job.status == "done", case.job.error
    assert not case.work.exists()


def test_failure_message_keeps_error_and_log_tail(sw, case):
    message = "specific training error"

    def bad_runner(argv, log):
        log.write_text(
            "earlier\n" + ("x" * 1000 + "\n") * 100 + "FINAL LOG MARKER", encoding="utf-8"
        )
        raise worker.StageError(message)

    process(sw, case, runner=bad_runner)
    assert case.job.status == "failed"
    assert case.job.error.startswith(message + "\n")
    assert case.job.error.endswith("FINAL LOG MARKER")
    assert len(case.job.error) <= ERROR_MAX


def test_a_very_long_error_message_keeps_its_beginning(sw, case):
    """splat_jobs.fail memotong dari belakang; pesan utama (awal) tidak boleh ikut terbuang."""
    message = "BEGIN " + "m" * (ERROR_MAX * 2)

    def bad_runner(argv, log):
        log.write_text("log line\nFINAL LOG MARKER", encoding="utf-8")
        raise worker.StageError(message)

    process(sw, case, runner=bad_runner)
    assert case.job.status == "failed"
    assert case.job.error.startswith("BEGIN ")
    assert len(case.job.error) <= ERROR_MAX


@pytest.mark.parametrize("status", ["uploading", "queued", "running", "done", "failed", "deleting"])
def test_map_work_pending_counts_queued_and_running_only(sw, case, status):
    case.map_job.status = status
    case.session.add(case.map_job)
    case.session.commit()
    assert sw.map_work_pending(case.session) is (status in {"queued", "running"})


def test_claim_when_idle_leaves_the_splat_job_queued_while_map_work_is_pending(sw, case):
    splat_jobs.fail(case.session, case.job, "retry")
    splat_jobs.enqueue(case.session, case.version.id)
    case.map_job.status = "queued"
    case.session.add(case.map_job)
    case.session.commit()
    assert sw.claim_when_idle(case.session) is None
    case.session.refresh(case.job)
    assert case.job.status == "queued"


def test_claim_when_idle_claims_when_no_map_work(sw, case):
    splat_jobs.fail(case.session, case.job, "retry")
    splat_jobs.enqueue(case.session, case.version.id)
    claimed = sw.claim_when_idle(case.session)
    assert claimed is case.job and claimed.status == "running"


def test_recover_on_start_marks_running_failed(case):
    assert splat_jobs.recover_stale(case.session) == 1
    assert case.job.status == "failed"
    assert case.job.error == "the splat worker stopped mid-job; rebuild it"


def test_main_recovers_stale_before_the_polling_loop_without_executing_it(sw):
    tree = ast.parse(inspect.getsource(sw.main))
    body = tree.body[0].body
    loop_index = next(i for i, node in enumerate(body) if isinstance(node, ast.While))
    startup = ast.Module(body=body[:loop_index], type_ignores=[])
    calls = [node for node in ast.walk(startup) if isinstance(node, ast.Call)]
    assert any(
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "splat_jobs"
        and node.func.attr == "recover_stale"
        for node in calls
    )


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyError("missing")])
def test_process_never_raises_on_unexpected_errors(sw, case, error):
    def bad_runner(*args):
        raise error

    process(sw, case, runner=bad_runner)
    assert case.job.status == "failed" and str(error) in case.job.error


def test_module_imports_without_heavy_dependencies(sw):
    code = (
        "import sys, server.splat_worker; "
        "bad = {'torch','gsplat','hloc','pycolmap','cv2'} & set(sys.modules); "
        "assert not bad, bad"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(("ratios", "expected"), [((0.1, 0.001234), 0.001234), ((), None)])
def test_check_ratio_uses_last_match_or_null_when_absent(sw, case, ratios, expected):
    process(sw, case, runner=fake_runner([], ratios=ratios))
    assert case.job.status == "done", case.job.error
    assert case.job.summary["check_ratio"] == expected


def test_convert_must_produce_a_scene(sw, case):
    delegate = fake_runner([])

    def run(argv, log):
        if Path(argv[1]).name != SCRIPTS["convert"]:
            delegate(argv, log)

    process(sw, case, runner=run)
    assert case.job.status == "failed" and case.job.stage == "convert"
    assert "convert produced no scene.sog" in case.job.error
    assert not (case.map_dir / "splat" / "scene.sog").exists()


@pytest.mark.parametrize("operation", ["copy", "report_write", "report_replace"])
def test_place_io_failures_keep_old_scene_and_clean_temps(sw, case, monkeypatch, operation):
    splat = case.map_dir / "splat"
    splat.mkdir()
    (splat / "scene.sog").write_bytes(b"old-scene")
    (splat / "report.json").write_text('{"old": true}')
    write, replace = Path.write_text, sw.os.replace

    def bad_copy(src, dst, *args, **kwargs):
        Path(dst).write_bytes(b"partial")
        raise OSError("copy failed")

    def bad_write(path, *args, **kwargs):
        if path.name.startswith(".report.json.tmp."):
            write(path, "partial")
            raise OSError("report_write failed")
        return write(path, *args, **kwargs)

    def bad_replace(src, dst):
        if Path(dst).name == "report.json":
            raise OSError("report_replace failed")
        return replace(src, dst)

    if operation == "copy":
        monkeypatch.setattr(sw.shutil, "copyfile", bad_copy)
    elif operation == "report_write":
        monkeypatch.setattr(Path, "write_text", bad_write)
    else:
        monkeypatch.setattr(sw.os, "replace", bad_replace)
    process(sw, case)
    assert case.job.status == "failed" and case.job.stage == "place"
    assert f"{operation} failed" in case.job.error
    assert (splat / "scene.sog").read_bytes() == b"old-scene"
    assert json.loads((splat / "report.json").read_text()) == {"old": True}
    assert sorted(p.name for p in splat.iterdir()) == ["report.json", "scene.sog"]


def test_cleanup_failure_does_not_fail_a_finished_job(sw, case, monkeypatch):
    real_rmtree = sw.shutil.rmtree

    def cleanup(path, *args, **kwargs):
        if Path(path) == case.work and kwargs.get("ignore_errors"):
            raise OSError("cleanup unavailable")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(sw.shutil, "rmtree", cleanup)
    process(sw, case)
    assert case.job.status == "done", case.job.error
    assert (case.map_dir / "splat" / "scene.sog").is_file()


def test_lock_acquisition_failure_is_gpu_wait_and_preserves_work(sw, case):
    gate = FakeGpuLock(error=RuntimeError("GPU lock unavailable"))
    calls = []
    process(sw, case, runner=fake_runner(calls), lock=lambda: gate)
    assert case.job.status == "failed" and case.job.stage == "gpu_wait"
    assert "GPU lock unavailable" in case.job.error
    assert [Path(argv[1]).name for argv in calls] == [SCRIPTS["prepare"]]
    assert case.work.is_dir()


def test_failure_handler_survives_an_unreadable_log(sw, case, monkeypatch):
    def bad_tail(log):
        raise OSError("log unreadable")

    monkeypatch.setattr(sw, "log_tail", bad_tail)
    process(sw, case, runner=fake_runner([], fail_on="train"))
    assert case.job.status == "failed"
    assert "failed test stage: train" in case.job.error


# --- metrik pelatih dan VRAM bebas ---------------------------------------------------------------


def write_stats(result, step, val=None, train=None):
    stats = result / "stats"
    stats.mkdir(parents=True, exist_ok=True)
    if val is not None:
        (stats / f"val_step{step}.json").write_text(val)
    if train is not None:
        (stats / f"train_step{step}_rank0.json").write_text(train)


GOOD_VAL = '{"psnr": 24.88562774658203, "ssim": 0.8861821889877319, "lpips": 0.2750255763530731}'
GOOD_TRAIN = '{"mem": 1.5070815086364746, "ellipse_time": 939.4, "num_GS": 901798}'


def test_train_metrics_reads_the_final_step_and_rounds(sw, tmp_path):
    write_stats(tmp_path, 29999, GOOD_VAL, GOOD_TRAIN)
    write_stats(tmp_path, 6999, '{"psnr": 1, "ssim": 1, "lpips": 1}', '{"mem": 9}')  # langkah lain
    assert sw.train_metrics(tmp_path, 30000) == {
        "psnr": 24.886,
        "ssim": 0.8862,
        "lpips": 0.275,
        "peak_mem_gb": 1.507,
    }


def test_train_metrics_without_train_file_keeps_quality_numbers(sw, tmp_path):
    write_stats(tmp_path, 16, GOOD_VAL, None)
    assert sw.train_metrics(tmp_path, 17) == {
        "psnr": 24.886,
        "ssim": 0.8862,
        "lpips": 0.275,
        "peak_mem_gb": None,
    }


@pytest.mark.parametrize(
    "val",
    [
        None,
        "not json",
        "[1, 2, 3]",
        '{"psnr": 24.8}',
        '{"psnr": "24.8", "ssim": 0.8, "lpips": 0.2}',
        '{"psnr": true, "ssim": 0.8, "lpips": 0.2}',
        '{"psnr": null, "ssim": 0.8, "lpips": 0.2}',
    ],
)
def test_train_metrics_is_none_when_quality_stats_are_unusable(sw, tmp_path, val):
    write_stats(tmp_path, 16, val, GOOD_TRAIN)
    assert sw.train_metrics(tmp_path, 17) is None


def test_train_metrics_is_none_when_nothing_was_written(sw, tmp_path):
    assert sw.train_metrics(tmp_path / "missing", 17) is None


def completed(stdout="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_free_vram_asks_the_trainer_python_for_mem_get_info(sw, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"], seen["kwargs"] = argv, kwargs
        return completed("6791\n")

    monkeypatch.setattr(sw.subprocess, "run", fake_run)
    assert sw.free_vram_mib() == 6791
    assert seen["argv"][0] == pipeline.TRAIN_PYTHON
    assert "mem_get_info" in seen["argv"][-1]
    assert seen["kwargs"]["timeout"] > 0 and seen["kwargs"]["capture_output"] is True


@pytest.mark.parametrize(
    "outcome",
    [
        completed("", 1),
        completed("Traceback\n", 1),
        completed("not a number\n"),
        completed(""),
        completed("-5\n"),
        subprocess.TimeoutExpired(cmd="x", timeout=1),
        FileNotFoundError("no python"),
    ],
)
def test_free_vram_is_none_when_it_cannot_be_measured(sw, monkeypatch, outcome):
    def fake_run(argv, **kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(sw.subprocess, "run", fake_run)
    assert sw.free_vram_mib() is None


def test_low_free_vram_fails_before_training_with_a_clear_message(sw, case):
    calls = []
    lock = FakeGpuLock()
    process(sw, case, runner=fake_runner(calls), lock=lambda: lock, free_vram=lambda: 1000)
    assert case.job.status == "failed" and case.job.stage == "gpu_wait"
    assert "1000 MiB" in case.job.error and f"{sw.MIN_FREE_VRAM_MIB} MiB" in case.job.error
    assert [Path(a[1]).name for a in calls] == [SCRIPTS["prepare"]]  # pelatih tidak jalan
    assert lock.events == ["enter", "exit"] and not lock.held
    assert not (case.map_dir / "splat" / "scene.sog").exists()


def test_vram_threshold_is_inclusive(sw, case):
    process(sw, case, free_vram=lambda: sw.MIN_FREE_VRAM_MIB - 1)
    assert case.job.status == "failed" and case.job.stage == "gpu_wait"


def test_exactly_the_threshold_trains(sw, case):
    process(sw, case, free_vram=lambda: sw.MIN_FREE_VRAM_MIB)
    assert case.job.status == "done", case.job.error
    assert case.job.summary["vram_free_mib"] == sw.MIN_FREE_VRAM_MIB


def test_unmeasurable_vram_does_not_block_training(sw, case):
    process(sw, case, free_vram=lambda: None)
    assert case.job.status == "done", case.job.error
    assert case.job.summary["vram_free_mib"] is None


def test_missing_trainer_stats_do_not_fail_the_job(sw, case):
    process(sw, case, runner=fake_runner([], stats=False))
    assert case.job.status == "done", case.job.error
    assert case.job.summary["metrics"] is None
    report = json.loads((case.map_dir / "splat" / "report.json").read_text())
    assert report["metrics"] is None


def test_vram_is_checked_while_holding_the_gpu_lock(sw, case):
    order = []
    lock = FakeGpuLock(on_enter=lambda: order.append("lock"))
    process(sw, case, lock=lambda: lock, free_vram=lambda: order.append("vram") or 8000)
    assert order == ["lock", "vram"]


def test_train_metrics_rounds_lpips_to_four_decimals(sw, tmp_path):
    write_stats(tmp_path, 16, '{"psnr": 20, "ssim": 0.5, "lpips": 0.27549}', GOOD_TRAIN)
    assert sw.train_metrics(tmp_path, 17)["lpips"] == 0.2755


def test_vram_threshold_keeps_a_margin_over_the_measured_need_and_fits_the_lab_gpu(sw):
    measured_trainer_mib = 2022  # Task 8 B7: 3.397 MiB total - 1.375 MiB lokalisasi produksi
    gpu_total_mib, production_resident_mib = 8192, 1375
    assert sw.MIN_FREE_VRAM_MIB >= 2 * measured_trainer_mib
    assert sw.MIN_FREE_VRAM_MIB <= gpu_total_mib - production_resident_mib
