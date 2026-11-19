"""Pemasangan align.json dan navgraph.json (spesifikasi eutopos-mobile bagian 8b)."""

import copy
import json
import math

import pytest
from sqlmodel import Session, SQLModel, create_engine

from server import alignment, manage
from server.db import publish, register

GOOD_GRAPH = {
    "frame": "building",
    "units": "m",
    "nodes": [{"id": "P01", "x": 0.0, "y": 0.4}, {"id": "P02", "x": 1.5, "y": 1.6}],
    "edges": [["P01", "P02"]],
    "targets": [{"node": "P02", "name": "Pintu Lab"}],
}

GOOD_ALIGN = {
    "meter_from_model": {
        "scale": 0.25,
        "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
        "translation": [1.0, 2.0, 0.5],
    },
    "phone_height_m": 1.3,
    "reference_points": 10,
    "residual_median_m": 0.12,
}


def changed(key_path, value):
    d = copy.deepcopy(GOOD_ALIGN)
    obj = d
    for k in key_path[:-1]:
        obj = obj[k]
    obj[key_path[-1]] = value
    return d


def test_valid_align_is_accepted():
    assert alignment.validate_align(copy.deepcopy(GOOD_ALIGN)) == GOOD_ALIGN


@pytest.mark.parametrize(
    "data",
    [
        changed(["meter_from_model", "scale"], 0),
        changed(["meter_from_model", "scale"], True),
        changed(["meter_from_model", "scale"], 10**400),
        changed(["meter_from_model", "rotation_xyzw"], [0.0, 0.0, 0.0, 2.0]),
        changed(["meter_from_model", "rotation_xyzw"], [0.0, 0.0, 1.0]),
        changed(["meter_from_model", "translation"], [1.0, math.nan, 0.0]),
        changed(["reference_points"], 3),
        changed(["reference_points"], True),
        changed(["residual_median_m"], None),
        {"tanpa": "meter_from_model"},
    ],
)
def test_invalid_align_is_rejected(data):
    with pytest.raises(ValueError):
        alignment.validate_align(data)


def layout(tmp_path):
    map_dir = tmp_path / "maps" / "floor10" / "job-7"
    (map_dir / "kp1024-r1024").mkdir(parents=True)
    src = tmp_path / "src"
    src.mkdir()
    (src / "align.json").write_text(json.dumps(GOOD_ALIGN), encoding="utf-8")
    (src / "navgraph.json").write_text(json.dumps(GOOD_GRAPH), encoding="utf-8")
    return map_dir, tmp_path / "maps" / "floor10", src


def test_install_writes_both_files_where_the_service_reads_them(tmp_path):
    map_dir, area_dir, src = layout(tmp_path)
    written, warnings = alignment.install(
        map_dir, "kp1024-r1024", area_dir, src / "align.json", src / "navgraph.json"
    )
    assert written == [map_dir / "kp1024-r1024" / "align.json", area_dir / "navgraph.json"]
    assert json.loads(written[0].read_text(encoding="utf-8")) == GOOD_ALIGN
    assert json.loads(written[1].read_text(encoding="utf-8")) == GOOD_GRAPH
    assert warnings == []
    assert not list(tmp_path.rglob("*.tmp"))


def test_broken_navgraph_stops_the_align_copy_too(tmp_path):
    map_dir, area_dir, src = layout(tmp_path)
    bad = copy.deepcopy(GOOD_GRAPH)
    bad["edges"] = [["P01", "P99"]]
    (src / "navgraph.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="P99"):
        alignment.install(
            map_dir, "kp1024-r1024", area_dir, src / "align.json", src / "navgraph.json"
        )
    assert not (map_dir / "kp1024-r1024" / "align.json").exists()


def test_disconnected_graph_installs_with_a_warning(tmp_path):
    map_dir, area_dir, src = layout(tmp_path)
    g = copy.deepcopy(GOOD_GRAPH)
    g["nodes"].append({"id": "P03", "x": 9.0, "y": 9.0})
    (src / "navgraph.json").write_text(json.dumps(g), encoding="utf-8")
    _, warnings = alignment.install(map_dir, "kp1024-r1024", area_dir, None, src / "navgraph.json")
    assert any("P03" in w for w in warnings)


def test_missing_run_folder_is_an_error(tmp_path):
    map_dir, area_dir, src = layout(tmp_path)
    with pytest.raises(ValueError, match="kp2048-r1024"):
        alignment.install(map_dir, "kp2048-r1024", area_dir, src / "align.json", None)


def test_nothing_to_install_is_an_error(tmp_path):
    map_dir, area_dir, _ = layout(tmp_path)
    with pytest.raises(ValueError):
        alignment.install(map_dir, "kp1024-r1024", area_dir, None, None)


def test_cli_installs_for_a_registered_version(tmp_path, monkeypatch, capsys):
    map_dir, area_dir, src = layout(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        from server.db import Area
        from tests.conftest import make_building

        bld = make_building(s)
        s.add(Area(id="floor10", name="Lantai 10", building_id=bld.id))
        s.commit()
        vid = publish(s, register(s, "floor10", "Lantai 10", str(map_dir)).id).id
    monkeypatch.setattr(manage, "engine_from_env", lambda: engine)
    monkeypatch.setenv("EUTOPOS_MAPS_ROOT", str(tmp_path / "maps"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "manage",
            "align",
            "--version",
            str(vid),
            "--align",
            str(src / "align.json"),
            "--navgraph",
            str(src / "navgraph.json"),
        ],
    )
    manage.main()
    out = capsys.readouterr().out
    assert (map_dir / "kp1024-r1024" / "align.json").exists()
    assert (area_dir / "navgraph.json").exists()
    assert "tanpa restart" in out and "sedang aktif" in out


def test_cli_unknown_version_exits_with_message(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(manage, "engine_from_env", lambda: engine)
    monkeypatch.setattr("sys.argv", ["manage", "align", "--version", "99", "--align", "x.json"])
    with pytest.raises(SystemExit, match="99"):
        manage.main()


def test_align_file_follows_the_file_without_restarting_the_service(tmp_path):
    # manage align pada versi aktif: /localize memakai align.json baru tanpa docker compose restart.
    p = tmp_path / "align.json"
    f = alignment.AlignFile(p)
    assert f.get() is None
    alignment._write_atomic(p, GOOD_ALIGN)
    assert f.get()["reference_points"] == 10
    newer = copy.deepcopy(GOOD_ALIGN)
    newer["reference_points"] = 8
    alignment._write_atomic(p, newer)
    assert f.get()["reference_points"] == 8
    p.unlink()
    assert f.get() is None


def test_broken_align_file_keeps_serving_the_last_good_alignment(tmp_path):
    p = tmp_path / "align.json"
    alignment._write_atomic(p, GOOD_ALIGN)
    f = alignment.AlignFile(p)
    assert f.get() is not None
    p.write_text('{"meter_from_model": rusak', encoding="utf-8")
    assert f.get()["reference_points"] == 10


def _db_with_version(tmp_path):
    from server.db import Alignment

    engine = create_engine(f"sqlite:///{tmp_path / 'a.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        from server.db import Area
        from tests.conftest import make_building

        bld = make_building(s)
        s.add(Area(id="floor10", name="Lantai 10", building_id=bld.id))
        s.commit()
        v1 = register(s, "floor10", "Lantai 10", "/maps/v1").id
        v2 = register(s, "floor10", "Lantai 10", "/maps/v2").id
    return engine, v1, v2, Alignment


def _applied(engine, Alignment, version_id, params, status="applied"):
    with Session(engine) as s:
        s.add(
            Alignment(
                map_version_id=version_id,
                params=params,
                stats={},
                status=status,
                source="fit",
                created_by="a",
            )
        )
        s.commit()


def test_db_align_reads_the_applied_alignment_of_its_own_version(tmp_path):
    engine, v1, v2, Alignment = _db_with_version(tmp_path)
    src = alignment.DbAlign(engine, v1)
    assert src.get() is None
    _applied(engine, Alignment, v2, GOOD_ALIGN)
    assert src.get() is None  # milik versi lain
    _applied(engine, Alignment, v1, GOOD_ALIGN, status="superseded")
    assert src.get() is None  # yang diganti tidak berlaku
    _applied(engine, Alignment, v1, GOOD_ALIGN)
    assert src.get()["reference_points"] == 10


def test_db_align_follows_a_new_applied_row_without_restarting_the_service(tmp_path):
    from sqlmodel import select

    engine, v1, _, Alignment = _db_with_version(tmp_path)
    _applied(engine, Alignment, v1, GOOD_ALIGN)
    src = alignment.DbAlign(engine, v1)
    assert src.get()["reference_points"] == 10
    newer = copy.deepcopy(GOOD_ALIGN)
    newer["reference_points"] = 8
    with Session(engine) as s:
        old = s.exec(select(Alignment)).one()
        old.status = "superseded"
        s.add(old)
        s.flush()
        s.add(
            Alignment(
                map_version_id=v1,
                params=newer,
                stats={},
                status="applied",
                source="fit",
                created_by="a",
            )
        )
        s.commit()
    assert src.get()["reference_points"] == 8


def test_db_align_keeps_serving_the_last_good_alignment_when_the_database_fails(
    tmp_path, monkeypatch
):
    engine, v1, _, Alignment = _db_with_version(tmp_path)
    _applied(engine, Alignment, v1, GOOD_ALIGN)
    src = alignment.DbAlign(engine, v1)
    assert src.get() is not None

    def boom(self, *a, **k):
        raise RuntimeError("database mati")

    monkeypatch.setattr(Session, "exec", boom)
    assert src.get()["reference_points"] == 10


def test_localizer_prefers_the_dashboard_alignment_over_the_file(tmp_path):
    from server.localizer import Localizer

    p = tmp_path / "align.json"
    alignment._write_atomic(p, GOOD_ALIGN)
    loc = object.__new__(Localizer)  # tanpa memuat model: hanya sifat align yang diuji
    loc._align = alignment.AlignFile(p)
    dash = copy.deepcopy(GOOD_ALIGN)
    dash["reference_points"] = 7
    loc._align_source = lambda: dash
    assert loc.align["reference_points"] == 7
    loc._align_source = lambda: None  # belum ada yang diterapkan: berkas lama (manage align)
    assert loc.align["reference_points"] == 10
    loc._align_source = None
    assert loc.align["reference_points"] == 10


def test_cli_warns_when_a_dashboard_alignment_takes_precedence(tmp_path, monkeypatch, capsys):
    from server.db import Alignment

    map_dir, _area_dir, src = layout(tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        from server.db import Area
        from tests.conftest import make_building

        bld = make_building(s)
        s.add(Area(id="floor10", name="Lantai 10", building_id=bld.id))
        s.commit()
        vid = publish(s, register(s, "floor10", "Lantai 10", str(map_dir)).id).id
        s.add(
            Alignment(
                map_version_id=vid,
                params=GOOD_ALIGN,
                stats={},
                status="applied",
                source="fit",
                created_by="a",
            )
        )
        s.commit()
    monkeypatch.setattr(manage, "engine_from_env", lambda: engine)
    monkeypatch.setenv("EUTOPOS_MAPS_ROOT", str(tmp_path / "maps"))
    monkeypatch.setattr(
        "sys.argv", ["manage", "align", "--version", str(vid), "--align", str(src / "align.json")]
    )
    manage.main()
    out = capsys.readouterr().out
    assert "didahulukan" in out and "tanpa restart" not in out


def test_validate_align_accepts_legacy_survey_without_method():
    assert alignment.validate_align(copy.deepcopy(GOOD_ALIGN)) == GOOD_ALIGN


def test_validate_align_preserves_survey_point_minimum():
    with pytest.raises(ValueError, match="reference_points"):
        alignment.validate_align(dict(GOOD_ALIGN, method="survey", reference_points=3))


QUICK_ALIGN = {
    "known_distance": {
        "known_distances": [
            {"frame_a": "a.jpg", "frame_b": "b.jpg", "distance_m": 10, "model_distance": 5}
        ],
        "gravity_spread_deg": 1.5,
    },
    "arcore_pose": {"matched_frames": 10, "residual_median_m": 0.1, "residual_max_m": 0.42},
}


@pytest.mark.parametrize("method", QUICK_ALIGN)
def test_valid_quick_align_is_used_by_localizer(method, tmp_path):
    import pycolmap

    from server.localizer import Localizer

    data = {"method": method, "meter_from_model": GOOD_ALIGN["meter_from_model"]}
    data.update(QUICK_ALIGN[method])
    assert alignment.validate_align(data) is data
    path = tmp_path / "align.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    localizer = object.__new__(Localizer)
    localizer._align = alignment.AlignFile(path)
    localizer._align_source = None
    center, _ = localizer.to_building(pycolmap.Rigid3d())
    assert center == pytest.approx([1, 2, 0.5])


@pytest.mark.parametrize(
    "method, field, value",
    [
        ("known_distance", "known_distances", None),
        ("known_distance", "known_distances", []),
        ("known_distance", "gravity_spread_deg", math.inf),
        ("arcore_pose", "matched_frames", 9),
        ("arcore_pose", "matched_frames", True),
        ("arcore_pose", "matched_frames", 10.0),
        ("arcore_pose", "residual_max_m", math.inf),
        ("arcore_pose", "residual_median_m", False),
    ],
)
def test_validate_align_rejects_bad_quick_method_fields(method, field, value):
    data = {"method": method, "meter_from_model": GOOD_ALIGN["meter_from_model"]}
    data.update(QUICK_ALIGN[method])
    if value is None:
        del data[field]
    else:
        data[field] = value
    with pytest.raises(ValueError, match=field):
        alignment.validate_align(data)


@pytest.mark.parametrize("field", ["distance_m", "model_distance"])
def test_validate_align_requires_positive_known_distances(field):
    pairs = copy.deepcopy(QUICK_ALIGN["known_distance"]["known_distances"])
    pairs[0][field] = 0
    data = dict(GOOD_ALIGN, method="known_distance", known_distances=pairs, gravity_spread_deg=0)
    with pytest.raises(ValueError, match=field):
        alignment.validate_align(data)


def test_validate_align_rejects_an_unknown_method():
    with pytest.raises(ValueError, match="method"):
        alignment.validate_align(dict(GOOD_ALIGN, method="other"))


@pytest.fixture
def quick_align_cli(tmp_path, monkeypatch):
    from server.pipeline import run_dir
    from tests.conftest import make_building

    map_dir = tmp_path / "maps" / "floor10" / "job-1"
    run = run_dir(map_dir)
    sfm = run / "sfm"
    sfm.mkdir(parents=True)
    (sfm / "cameras.txt").write_text("1 PINHOLE 640 480 500 500 320 240\n", encoding="utf-8")
    (sfm / "images.txt").write_text(
        "1 1 0 0 0 0 0 0 1 mapping/000001.jpg\n\n2 1 0 0 0 -4 0 0 1 mapping/000002.jpg\n\n",
        encoding="utf-8",
    )
    (sfm / "points3D.txt").touch()
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        vid = register(s, "floor10", "Lantai 10", str(map_dir), building_id=make_building(s).id).id
    monkeypatch.setattr(manage, "engine_from_env", lambda: engine)
    monkeypatch.setenv("EUTOPOS_MAPS_ROOT", str(tmp_path / "maps"))
    argv = [
        "manage",
        "quick-align",
        "--version",
        str(vid),
        "--method",
        "distance",
        "--pair",
        "mapping/000001.jpg",
        "000002.jpg",
        "10",
    ]
    yield engine, vid, run / "align.json", argv
    engine.dispose()


@pytest.mark.parametrize("existing", ["legacy-file", "survey-file", "survey-db"])
def test_quick_align_cli_replaces_survey_only_with_flag(
    quick_align_cli, monkeypatch, capsys, existing, tmp_path
):
    from server.db import Alignment

    engine, vid, destination, args = quick_align_cli
    if existing == "survey-db":
        with Session(engine) as s:
            applied = Alignment(
                map_version_id=vid,
                params=GOOD_ALIGN,
                stats={},
                status="applied",
                source="fit",
                created_by="a",
            )
            s.add(applied)
            s.commit()
            dashboard_id = applied.id
    else:
        prior = GOOD_ALIGN if existing == "legacy-file" else dict(GOOD_ALIGN, method="survey")
        destination.write_text(json.dumps(prior), encoding="utf-8")

    exported = tmp_path / "result.json"
    before = destination.read_bytes() if destination.exists() else None
    argv = [*args, "--install", "--out", str(exported)]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit, match="--replace-survey"):
        manage.main()
    assert (destination.read_bytes() if destination.exists() else None) == before
    assert not exported.exists()

    monkeypatch.setattr("sys.argv", [*argv, "--replace-survey"])
    manage.main()
    out = capsys.readouterr().out
    installed = alignment.AlignFile(destination).get()
    assert installed == json.loads(exported.read_text(encoding="utf-8"))
    assert installed["method"] == "known_distance"
    assert installed["meter_from_model"]["scale"] == pytest.approx(2.5)
    assert "PERINGATAN:" in out
    if existing == "survey-db":
        assert f"dashboard (id {dashboard_id})" in out and "didahulukan" in out
        with Session(engine) as s:
            assert s.get(Alignment, dashboard_id).params == GOOD_ALIGN


def test_quick_align_cli_exports_without_installing(quick_align_cli, monkeypatch, tmp_path):
    _, _, destination, argv = quick_align_cli
    export = tmp_path / "export.json"
    monkeypatch.setattr("sys.argv", [*argv, "--out", str(export)])
    manage.main()
    assert json.loads(export.read_text(encoding="utf-8"))["method"] == "known_distance"
    assert not destination.exists()


def test_quick_align_cli_requires_install_even_if_out_points_to_align(quick_align_cli, monkeypatch):
    _, _, destination, argv = quick_align_cli
    destination.write_text(json.dumps(GOOD_ALIGN), encoding="utf-8")
    before = destination.read_bytes()
    monkeypatch.setattr("sys.argv", [*argv, "--out", str(destination)])
    with pytest.raises(SystemExit, match="--install"):
        manage.main()
    assert destination.read_bytes() == before
