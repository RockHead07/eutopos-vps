"""Foto kecil frame scan untuk "foto asli" di halaman area (spesifikasi 2026-10-21 bagian 5d)."""

from pathlib import Path

from PIL import Image
from sqlmodel import Session, SQLModel, create_engine

from server import worker
from server.db import Area, MapJob
from server.thumbs import make_thumbs


def write_frames(d: Path, names) -> None:
    d.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    exif[0x010F] = "TECNO"  # Make
    for n in names:
        Image.new("RGB", (1920, 1080), (120, 130, 140)).save(d / n, exif=exif)


def test_thumbs_are_small_and_stripped(tmp_path):
    write_frames(tmp_path / "mapping", ["a_00001.jpg", "a_00002.jpg"])
    assert make_thumbs(tmp_path / "mapping", tmp_path / "thumbs") == 2
    for n in ("a_00001.jpg", "a_00002.jpg"):
        img = Image.open(tmp_path / "thumbs" / n)
        assert img.size[0] == 480
        assert len(img.getexif()) == 0


def test_missing_frames_give_zero(tmp_path):
    assert make_thumbs(tmp_path / "tidak-ada", tmp_path / "thumbs") == 0


def test_backfill_makes_thumbs_for_finished_jobs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w.db'}")
    SQLModel.metadata.create_all(engine)
    maps, data = tmp_path / "maps", tmp_path / "data"
    with Session(engine) as s:
        s.add(Area(id="floor10", name="L10"))
        s.add(MapJob(id=21, area_id="floor10", created_by="dev", status="done"))
        s.commit()
        (maps / "floor10" / "job-21").mkdir(parents=True)
        write_frames(data / "jobs" / "21" / "dataset" / "mapping", ["v0_00001.jpg"])
        assert worker.backfill_thumbs(s, data, maps) == (1, 0)
        assert (maps / "floor10" / "job-21" / "thumbs" / "v0_00001.jpg").is_file()
        assert worker.backfill_thumbs(s, data, maps) == (0, 0)  # sudah punya, dilewati
