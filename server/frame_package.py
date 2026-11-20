"""Validasi paket foto ZIP sebelum menyalin file ke dataset."""

import re
import shutil
import stat
import sys
import zipfile
import zlib
from copy import copy
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

MAX_IMAGES = 1500
MAX_IMAGE_BYTES = 20 * 1024**2
MAX_TOTAL_BYTES = 3 * 1024**3
MAX_JSON_BYTES = 10 * 1024**2
MAX_DIRECTORY_BYTES = 8 * 1024**2
CHUNK_BYTES = 64 * 1024
METADATA = {"frames.jsonl", "meta.json", "configs.json"}
JPG_NAME = re.compile(r"images/[0-9]{6}\.jpg")


class PackageError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _layout(archive: zipfile.ZipFile) -> tuple[dict[str, zipfile.ZipInfo], list[zipfile.ZipInfo]]:
    entries = {}
    for info in archive.infolist():
        name = info.orig_filename
        parts = name.removesuffix("/").split("/")
        if "\\" in name or "\0" in name or ":" in name or any(p in ("", ".", "..") for p in parts):
            raise PackageError("unsafe_path", f"invalid path: {name!r}")
        mode = stat.S_IFMT(info.external_attr >> 16)
        if mode == stat.S_IFLNK:
            raise PackageError("symlink", f"symbolic link: {name!r}")
        if mode not in (0, stat.S_IFDIR if info.is_dir() else stat.S_IFREG):
            raise PackageError("unexpected_entry", f"unsupported file type: {name!r}")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise PackageError("unexpected_entry", f"unsupported compression: {name!r}")
        key = tuple(parts)
        if key in entries:
            raise PackageError("duplicate", f"duplicate entry: {name!r}")
        entries[key] = info

    roots = {parts[0] for parts in entries}
    direct = any(
        not info.is_dir() and (JPG_NAME.fullmatch("/".join(parts)) or "/".join(parts) in METADATA)
        for parts, info in entries.items()
    )
    wrapped = not direct and len(roots) == 1 and any(len(parts) > 1 for parts in entries)
    files, folders = {}, []
    for parts, info in entries.items():
        if wrapped:
            parts = parts[1:]
        name = "/".join(parts)
        if info.is_dir() and (not parts or parts == ("images",)):
            folders.append(info)
        elif len(parts) > 2:
            raise PackageError("nested_folder", f"too many folder levels: {info.filename!r}")
        elif not info.is_dir() and (JPG_NAME.fullmatch(name) or name in METADATA):
            files[name] = info
        else:
            raise PackageError("unexpected_entry", f"unexpected entry: {info.filename!r}")
    count = sum(name.startswith("images/") for name in files)
    if not count:
        raise PackageError("no_images", "package has no JPEG images")
    if count > MAX_IMAGES:
        raise PackageError("too_many_images", f"maximum {MAX_IMAGES} images")
    return files, folders


def _copy_member(archive, info, output, limit: int, remaining: int, jpeg: bool = False) -> int:
    if info.file_size > min(limit, remaining):
        raise PackageError("too_large", f"declared size exceeds limit: {info.filename!r}")
    # ZipExtFile normally truncates output to the claimed file_size. Read through the
    # actual stream independently of that claim, bounded by the entry and package budgets.
    stream_info = copy(info)
    stream_info.file_size = sys.maxsize
    size = 0
    with archive.open(stream_info) as source:
        while chunk := source.read(min(CHUNK_BYTES, min(limit, remaining) - size + 1)):
            size += len(chunk)
            if size > min(limit, remaining):
                raise PackageError("too_large", f"extracted bytes exceed limit: {info.filename!r}")
            if jpeg and not output.tell() and not chunk.startswith(b"\xff\xd8\xff"):
                raise PackageError("not_jpeg", f"invalid JPEG marker: {info.filename!r}")
            if output is not None:
                output.write(chunk)
    if size != info.file_size:
        raise PackageError("bad_zip", f"incorrect uncompressed size: {info.filename!r}")
    if jpeg and size < 3:
        raise PackageError("not_jpeg", f"missing JPEG marker: {info.filename!r}")
    return size


def _validate_frames(path: Path, images: set[str]) -> None:
    from server import quick_align

    try:
        frames = quick_align.read_frames(path)
        seen = set()
        for number, frame in enumerate(frames, 1):
            name = PurePosixPath(frame["file"].replace("\\", "/")).name
            if name not in images or name in seen:
                raise ValueError(f"frames.jsonl line {number}: missing or repeated image {name!r}")
            seen.add(name)
    except ValueError as exc:
        raise PackageError("bad_frames", str(exc)) from exc


def _publish(staged: list[tuple[Path, Path]]) -> None:
    created, written = [], []
    try:
        for source, target in staged:
            parents = []
            parent = target.parent
            while not parent.exists() and not parent.is_symlink():
                parents.append(parent)
                parent = parent.parent
            if parent.is_symlink() or target.parent.is_symlink():
                raise PackageError("symlink", "destination is a symbolic link")
            for directory in reversed(parents):
                directory.mkdir()
                created.append(directory)
            with target.open("xb") as output:
                written.append(target)
                with source.open("rb") as data:
                    shutil.copyfileobj(data, output, CHUNK_BYTES)
    except Exception:
        for file in reversed(written):
            file.unlink()
        for directory in reversed(created):
            directory.rmdir()
        raise


def extract(zip_path: Path, dest_images: Path, dest_meta: Path | None, require_frames: bool) -> int:
    # Stage on the dataset filesystem. Final paths are opened only after all entries pass.
    for destination in (dest_images, dest_meta):
        if destination is not None and any(
            p.is_symlink() or p.is_junction() for p in (destination, *destination.parents)
        ):
            raise PackageError("symlink", "destination is a symbolic link")
    scratch_root = next(p for p in dest_images.absolute().parents if p.is_dir())
    try:
        with zip_path.open("rb") as stream, TemporaryDirectory(dir=scratch_root) as temporary:
            # ZipFile reads the whole central directory before exposing its entries.
            end = zipfile._EndRecData(stream)
            if end is None:
                raise PackageError("bad_zip", "missing ZIP central directory")
            if end[zipfile._ECD_SIZE] > MAX_DIRECTORY_BYTES:
                raise PackageError("too_large", "ZIP central directory exceeds limit")
            with zipfile.ZipFile(stream) as archive:
                files, folders = _layout(archive)
                if require_frames and "frames.jsonl" not in files:
                    raise PackageError("bad_frames", "mapping package requires frames.jsonl")
                for info in folders:
                    _copy_member(archive, info, None, 0, 0)
                total = 0
                outputs = []
                images = set()
                for name, info in files.items():
                    jpeg = name.startswith("images/")
                    filename = Path(name).name
                    source = Path(temporary) / filename
                    limit = MAX_IMAGE_BYTES if jpeg else MAX_JSON_BYTES
                    with source.open("xb") as output:
                        total += _copy_member(
                            archive, info, output, limit, MAX_TOTAL_BYTES - total, jpeg
                        )
                    if jpeg:
                        images.add(filename)
                        outputs.append((source, dest_images / filename))
                    elif dest_meta is not None:
                        outputs.append((source, dest_meta / filename))
                if "frames.jsonl" in files:
                    _validate_frames(Path(temporary) / "frames.jsonl", images)
            _publish(outputs)
            return len(images)
    except (zipfile.BadZipFile, EOFError, RuntimeError, zlib.error) as exc:
        raise PackageError("bad_zip", str(exc)) from exc
