import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from server import localizer


@pytest.fixture
def fake_spike(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "spike"))
    run = importlib.import_module("run")
    monkeypatch.setattr(run, "GLOBAL", run.GLOBAL)
    configs = []

    def extract(conf, *_args, **_kwargs):
        configs.append(conf["model"].copy())

    camera = SimpleNamespace(width=1024, height=768)
    model = SimpleNamespace(cameras={1: camera}, num_reg_images=lambda: 1, num_points3D=lambda: 100)
    monkeypatch.setattr(run.extract_features, "main", extract)
    monkeypatch.setattr(run.match_features, "main", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(run, "make_pairs", lambda *_args: None)
    monkeypatch.setattr(run.reconstruction, "main", lambda *_args, **_kwargs: model)
    monkeypatch.setattr(run.pycolmap, "infer_camera_from_image", lambda _path: camera)
    monkeypatch.setattr(run, "QueryLocalizer", lambda *_args: None)
    monkeypatch.setattr(run, "parse_retrieval", lambda _path: {})
    monkeypatch.setattr(run, "orientation", lambda _path: 1)
    monkeypatch.setattr(run, "env", dict)

    out = tmp_path / "output"

    def build(*flags, with_query=False):
        names = {"mapping": ["mapping/ref.jpg"], "query": ["query/test.jpg"] if with_query else []}
        monkeypatch.setattr(run, "images_in", lambda _root, folder: names[folder])
        monkeypatch.setattr("sys.argv", ["run.py", str(tmp_path), "--out", str(out), *flags])
        run.main()

    return SimpleNamespace(build=build, run=run, configs=configs, directory=out / "kp1024-r1024")


@pytest.mark.parametrize(
    ("flags", "with_query", "expected"),
    [
        ((), False, 0.2),
        (("--detection-threshold", "0.01"), False, 0.01),
        (("--detection-threshold", "0.01"), True, 0.01),
        (("--detection-threshold", "0.01", "--covis"), True, 0.01),
    ],
)
def test_spike_passes_threshold_to_extractor_and_summary(fake_spike, flags, with_query, expected):
    fake_spike.build(*flags, with_query=with_query)

    assert [conf["detection_threshold"] for conf in fake_spike.configs] == [expected] * (
        2 if with_query else 1
    )
    summary = json.loads((fake_spike.directory / "summary.json").read_text(encoding="utf-8"))
    assert summary["detection_threshold"] == expected
    if "--covis" in flags:
        assert (fake_spike.directory / "summary-covis.json").is_file()


@pytest.mark.parametrize("value", ["0", "-0.01", "nan", "inf"])
def test_spike_rejects_invalid_cli_threshold(fake_spike, capsys, value):
    with pytest.raises(SystemExit) as error:
        fake_spike.build("--detection-threshold=" + value)

    assert error.value.code == 2
    assert "positive finite number" in capsys.readouterr().err
    assert not fake_spike.configs


def test_spike_rejects_other_threshold_cache_after_interrupted_build(fake_spike, monkeypatch):
    with monkeypatch.context() as temporary:

        def interrupted(*_args, **_kwargs):
            raise RuntimeError("interrupted")

        temporary.setattr(fake_spike.run.extract_features, "main", interrupted)
        with pytest.raises(RuntimeError, match="interrupted"):
            fake_spike.build("--detection-threshold", "0.01")

    assert not (fake_spike.directory / "summary.json").exists()
    with pytest.raises(SystemExit, match=r"detection_threshold.*--out"):
        fake_spike.build()
    assert not fake_spike.configs

    fake_spike.build("--detection-threshold", "0.01")
    assert fake_spike.configs[0]["detection_threshold"] == 0.01


@pytest.fixture
def fake_localizer(tmp_path, monkeypatch):
    loaded = []

    def load(_self, _pkg, conf):
        loaded.append(conf["model"].copy())

    camera = SimpleNamespace(width=1024, height=768)
    monkeypatch.setattr(localizer, "missing_files", lambda *_args: [])
    monkeypatch.setattr(localizer, "trust_megaloc_hub_repo", lambda: None)
    monkeypatch.setattr(localizer.Localizer, "_load", load)
    monkeypatch.setattr(localizer.Localizer, "_load_db", lambda *_args: {"ref": {"global": [1.0]}})
    monkeypatch.setattr(
        localizer.pycolmap, "Reconstruction", lambda _path: SimpleNamespace(cameras={1: camera})
    )
    monkeypatch.setattr(localizer, "QueryLocalizer", lambda *_args: None)
    summary = tmp_path / "kp1024-r1024" / "summary.json"
    summary.parent.mkdir()
    return SimpleNamespace(map_dir=tmp_path, summary=summary, loaded=loaded)


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ({"detection_threshold": 0.01}, 0.01),
        ({"map_registered": 10}, 0.2),
        (None, 0.2),
    ],
)
def test_localizer_uses_map_detection_threshold(fake_localizer, summary, expected):
    if summary is not None:
        fake_localizer.summary.write_text(json.dumps(summary), encoding="utf-8")

    loc = localizer.Localizer(fake_localizer.map_dir)

    assert loc.detection_threshold == expected
    assert fake_localizer.loaded[1]["name"] == "aliked"
    assert fake_localizer.loaded[1]["detection_threshold"] == expected
    assert fake_localizer.loaded[1]["max_num_keypoints"] == 1024


@pytest.mark.parametrize(
    "value",
    [0, -0.01, "0.01", True, None, {}, float("nan"), float("inf"), 10**400],
)
def test_localizer_rejects_invalid_threshold_before_loading_models(fake_localizer, value):
    fake_localizer.summary.write_text(json.dumps({"detection_threshold": value}), encoding="utf-8")

    with pytest.raises(ValueError, match=r"summary\.json.*detection_threshold.*positive finite"):
        localizer.Localizer(fake_localizer.map_dir)

    assert not fake_localizer.loaded


@pytest.mark.parametrize("invalid_summary", ['{"detection_threshold":', "[]"])
def test_localizer_rejects_broken_summary(fake_localizer, invalid_summary):
    fake_localizer.summary.write_text(invalid_summary, encoding="utf-8")

    with pytest.raises(ValueError, match=r"summary\.json"):
        localizer.Localizer(fake_localizer.map_dir)

    assert not fake_localizer.loaded
