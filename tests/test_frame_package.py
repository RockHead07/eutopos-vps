import stat
import warnings
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from server import frame_package as package

JPG = b"\xff\xd8\xff" + b"image"
POSES = '{"file":"000001.jpg","position":[0,1,2]}\n'


def make_zip(path, entries):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Duplicate name:")
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
            for name, data in entries:
                archive.writestr(name, data)


@pytest.mark.parametrize("prefix", ["", "session/"])
def test_valid_package(tmp_path, prefix):
    source = tmp_path / "package"
    entries = [("images/", ""), ("images/000001.jpg", JPG), ("frames.jsonl", POSES)]
    entries += [("meta.json", '{"test":true}'), ("configs.json", "{}")]
    if prefix:
        entries = [(prefix, "")] + [(prefix + name, data) for name, data in entries]
    make_zip(source, entries)
    images, meta = tmp_path / "images", tmp_path / "capture"
    assert package.extract(source, images, meta, True) == 1
    assert (images / "000001.jpg").read_bytes() == JPG
    assert (meta / "frames.jsonl").read_text() == POSES
    assert (meta / "meta.json").read_text() == '{"test":true}'
    assert (meta / "configs.json").read_text() == "{}"


def test_query_package_without_frames(tmp_path):
    source = tmp_path / "package"
    make_zip(source, [("images/000001.jpg", JPG), ("meta.json", "{}")])
    assert package.extract(source, tmp_path / "images", None, False) == 1
    assert not (tmp_path / "meta.json").exists()


symlink = ZipInfo("images/000002.jpg")
symlink.create_system = 3
symlink.external_attr = (stat.S_IFLNK | 0o777) << 16


@pytest.mark.parametrize(
    "extra, code",
    [
        ([("../escape.jpg", JPG)], "unsafe_path"),
        ([("/escape.jpg", JPG)], "unsafe_path"),
        ([("C:/escape.jpg", JPG)], "unsafe_path"),
        ([(symlink, "outside")], "symlink"),
        ([("images/000001.jpg", JPG)], "duplicate"),
        ([("images/other.jpg", JPG)], "unexpected_entry"),
        ([("images/000002.jpg", b"entirely fake")], "not_jpeg"),
        ([("frames.jsonl", POSES.replace("000001", "000002"))], "bad_frames"),
        ([("frames.jsonl", POSES + POSES)], "bad_frames"),
        ([("frames.jsonl", "{}")], "bad_frames"),
    ],
)
def test_rejects_invalid_entries_without_output(tmp_path, extra, code):
    source = tmp_path / "package"
    make_zip(source, [("images/000001.jpg", JPG), *extra])
    with pytest.raises(package.PackageError) as exc:
        package.extract(source, tmp_path / "images", tmp_path / "capture", False)
    assert exc.value.code == code
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize(
    "entries, required, code",
    [
        ([("meta.json", "{}")], False, "no_images"),
        ([("images/000001.jpg", JPG)], True, "bad_frames"),
        ([("one/two/images/000001.jpg", JPG)], False, "nested_folder"),
    ],
)
def test_rejects_bad_structure(tmp_path, entries, required, code):
    source = tmp_path / "package"
    make_zip(source, entries)
    with pytest.raises(package.PackageError) as exc:
        package.extract(source, tmp_path / "images", None, required)
    assert exc.value.code == code
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize(
    "limit, size, entry, code",
    [
        ("MAX_IMAGES", 1, ("images/000002.jpg", JPG), "too_many_images"),
        ("MAX_IMAGE_BYTES", 7, ("images/000002.jpg", JPG), "too_large"),
        ("MAX_JSON_BYTES", 1, ("meta.json", "{}"), "too_large"),
    ],
)
def test_enforces_individual_limits(tmp_path, monkeypatch, limit, size, entry, code):
    source = tmp_path / "package"
    make_zip(source, [("images/000001.jpg", JPG), entry])
    monkeypatch.setattr(package, limit, size)
    with pytest.raises(package.PackageError) as exc:
        package.extract(source, tmp_path / "images", None, False)
    assert exc.value.code == code
    assert list(tmp_path.iterdir()) == [source]


def test_total_limit_counts_stream_even_when_size_headers_underreport(tmp_path, monkeypatch):
    source = tmp_path / "package"
    make_zip(source, [("images/000001.jpg", JPG + b"A" * 8192)])
    data = bytearray(source.read_bytes())
    local, central = data.index(b"PK\x03\x04"), data.index(b"PK\x01\x02")
    data[local + 22 : local + 26] = data[central + 24 : central + 28] = len(JPG).to_bytes(
        4, "little"
    )
    source.write_bytes(data)
    monkeypatch.setattr(package, "MAX_TOTAL_BYTES", len(JPG) + 1)
    with pytest.raises(package.PackageError) as exc:
        package.extract(source, tmp_path / "images", None, False)
    assert exc.value.code == "too_large"
    assert list(tmp_path.iterdir()) == [source]


def test_rejects_actual_backslash_in_zip_headers(tmp_path):
    source = tmp_path / "package"
    make_zip(source, [("images/000001.jpg", JPG), ("images/000002.jpg", JPG)])
    source.write_bytes(source.read_bytes().replace(b"images/000002.jpg", rb"images\000002.jpg"))
    with pytest.raises(package.PackageError) as exc:
        package.extract(source, tmp_path / "images", None, False)
    assert exc.value.code == "unsafe_path"
    assert list(tmp_path.iterdir()) == [source]


def test_bad_zip_rejected(tmp_path):
    source = tmp_path / "package"
    source.write_bytes(b"not a zip")
    with pytest.raises(package.PackageError) as exc:
        package.extract(source, tmp_path / "images", None, False)
    assert exc.value.code == "bad_zip"


def test_output_collision_rolls_back_only_new_files(tmp_path):
    source = tmp_path / "package"
    make_zip(source, [("images/000001.jpg", JPG), ("images/000002.jpg", JPG)])
    dest = tmp_path / "images"
    dest.mkdir()
    existing = dest / "000002.jpg"
    existing.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        package.extract(source, dest, None, False)
    assert list(dest.iterdir()) == [existing]
    assert existing.read_bytes() == b"original"
