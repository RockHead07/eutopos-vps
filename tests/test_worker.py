"""Uji pekerja dengan perintah subprocess palsu: tanpa GPU, tanpa hloc."""

import sys
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from server import jobs, pipeline, worker
from server.db import MapVersion
from server.map_layout import required_files


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def fake_runner(calls, fail_on=None):
    """Meniru alat spike: buat berkas yang biasanya ditulis tiap skrip."""

    def run(argv, log):
        script = Path(argv[1]).name
        calls.append(script)
        if script == fail_on:
            raise worker.StageError(f"perintah gagal (kode 1): {script}")
        if script == "run.py":
            map_dir = Path(argv[argv.index("--out") + 1])
            for p in required_files(map_dir, 1024, 1024, 512):
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
            (pipeline.run_dir(map_dir) / "summary.json").write_text('{"map_registered": 80}')
        if script == "inspect_map.py":
            Path(argv[argv.index("--json") + 1]).write_text('{"parts": [], "accepted": 20}')

    return run


def make_inputs(tmp_path):
    data, maps = tmp_path / "data", tmp_path / "maps"
    (data / "uploads").mkdir(parents=True)
    uploaded = data / "uploads" / "abc"
    uploaded.write_bytes(b"video")
    own = tmp_path / "pemilik" / "v2.mp4"  # berkas milik pemilik, diberikan lewat CLI
    own.parent.mkdir()
    own.write_bytes(b"video")
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "f_00000.jpg").write_bytes(b"jpg")
    videos = [
        {"path": str(uploaded), "role": "peta"},
        {"path": str(own), "role": "uji"},
        {"path": str(frames), "role": "peta"},
    ]
    return data, maps, uploaded, own, videos


def queued(session, videos):
    job = jobs.create_job(session, "floor10", "Lantai 10", "cli", videos, "queued")
    jobs.claim_next(session)
    return job


def test_extract_commands_split_by_role(tmp_path):
    v1, v2 = tmp_path / "v1.mp4", tmp_path / "v2.mp4"
    v1.touch()
    v2.touch()
    videos = [{"path": str(v1), "role": "peta"}, {"path": str(v2), "role": "uji"}]
    cmds = pipeline.extract_commands(videos, tmp_path / "ds")
    assert [c[c.index("--fps") + 1] for c in cmds] == ["2.0", "0.5"]
    assert cmds[0][cmds[0].index("--out") + 1].endswith("mapping")
    assert cmds[1][cmds[1].index("--out") + 1].endswith("query")


def test_build_command_matches_service_settings(tmp_path):
    cmd = pipeline.build_command(tmp_path / "ds", tmp_path / "map")
    for flag, value in [("--max-kp", "1024"), ("--resize", "1024"), ("--global-resize", "512")]:
        assert cmd[cmd.index(flag) + 1] == value
    assert cmd[cmd.index("--seq") + 1] == "10"
    # retrieval selalu, supaya global-r512.h5 ada juga untuk peta kecil (<= 30 frame)
    assert cmd[cmd.index("--exhaustive-max") + 1] == "0"


def test_process_success_registers_candidate_and_spares_cli_files(session, tmp_path):
    data, maps, uploaded, own, videos = make_inputs(tmp_path)
    job = queued(session, videos)
    calls = []

    worker.process(session, job, data, maps, runner=fake_runner(calls), free_bytes=lambda p: 10**12)

    assert job.status == "done", job.error
    assert calls == ["extract_frames.py", "extract_frames.py", "run.py", "inspect_map.py"]
    v = session.get(MapVersion, job.map_version_id)
    assert (v.status, v.path) == ("candidate", str(maps / "floor10" / f"job-{job.id}"))
    assert job.summary == {"run": {"map_registered": 80}, "inspect": {"parts": [], "accepted": 20}}
    assert not uploaded.exists()  # video unggahan dihapus setelah ekstraksi
    assert own.exists()  # berkas CLI di luar uploads tidak pernah dihapus
    assert (data / "jobs" / str(job.id) / "dataset" / "mapping" / "f_00000.jpg").exists()


def test_process_failure_keeps_stage_and_log(session, tmp_path):
    data, maps, _, _, videos = make_inputs(tmp_path)
    job = queued(session, videos)
    runner = fake_runner([], fail_on="run.py")
    worker.process(session, job, data, maps, runner=runner, free_bytes=lambda p: 10**12)
    assert (job.status, job.stage) == ("failed", "build")
    assert "run.py" in job.error
    assert job.map_version_id is None


def test_process_refuses_when_disk_is_low(session, tmp_path):
    data, maps, uploaded, _, videos = make_inputs(tmp_path)
    job = queued(session, videos)
    calls = []
    worker.process(session, job, data, maps, runner=fake_runner(calls), free_bytes=lambda p: 10)
    assert (job.status, job.stage) == ("failed", "extract")
    assert "ruang disk" in job.error and calls == []
    assert not uploaded.exists()  # pekerjaan gagal tidak pernah diulang, video tidak ditinggal


def test_process_reports_missing_input(session, tmp_path):
    data, maps, *_ = make_inputs(tmp_path)
    job = queued(session, [{"path": str(tmp_path / "tidak-ada.mp4"), "role": "peta"}])
    worker.process(session, job, data, maps, runner=fake_runner([]), free_bytes=lambda p: 10**12)
    assert job.status == "failed" and "tidak-ada.mp4" in job.error


def test_run_appends_command_and_raises_on_failure(tmp_path):
    log = tmp_path / "log.txt"
    with pytest.raises(worker.StageError, match="kode 3"):
        worker.run([sys.executable, "-c", "print('halo'); raise SystemExit(3)"], log)
    text = log.read_text(encoding="utf-8")
    assert text.startswith("$ ") and "halo" in text


def test_megaloc_hub_repo_is_trusted_once(tmp_path, monkeypatch):
    import torch

    from server.localizer import trust_megaloc_hub_repo

    monkeypatch.setattr(torch.hub, "get_dir", lambda: str(tmp_path / "hub"))
    trust_megaloc_hub_repo()
    trust_megaloc_hub_repo()
    trusted = (tmp_path / "hub" / "trusted_list").read_text(encoding="utf-8").split()
    assert trusted == ["gmberton_MegaLoc"]


def test_error_keeps_message_when_log_is_long(session, tmp_path):
    data, maps, _, _, videos = make_inputs(tmp_path)
    job = queued(session, videos)
    log = data / "jobs" / str(job.id) / "log.txt"
    log.parent.mkdir(parents=True)
    log.write_text("".join("x" * 120 + "\n" for _ in range(60)), encoding="utf-8")
    runner = fake_runner([], fail_on="run.py")
    worker.process(session, job, data, maps, runner=runner, free_bytes=lambda p: 10**12)
    assert job.error.startswith("perintah gagal (kode 1): run.py")
    assert len(job.error) <= jobs.ERROR_MAX


def test_worker_session_holds_no_transaction_during_stage(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w.db'}")
    SQLModel.metadata.create_all(engine)
    with worker.worker_session(engine) as s:
        job = queued(s, [{"path": str(tmp_path), "role": "peta"}])
        jobs.set_stage(s, job, "build")
        assert not s.in_transaction()  # subprocess berjam-jam tidak boleh menahan transaksi
        assert job.stage == "build"


def test_delete_upload_files_removes_data_and_info(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    for name in ["job1-v0-abc", "job1-v0-abc.info", "lain"]:
        (uploads / name).write_text("x")
    worker.delete_upload_files(["job1-v0-abc", "../lain"], uploads)
    assert sorted(p.name for p in uploads.iterdir()) == ["lain"]


def test_failed_job_still_deletes_uploaded_videos(session, tmp_path):
    data, maps, uploaded, own, videos = make_inputs(tmp_path)
    job = queued(session, videos)
    runner = fake_runner([], fail_on="extract_frames.py")
    worker.process(session, job, data, maps, runner=runner, free_bytes=lambda p: 10**12)
    assert job.status == "failed"
    assert not uploaded.exists() and own.exists()  # privasi: video unggahan tidak tertinggal
