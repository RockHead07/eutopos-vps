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
