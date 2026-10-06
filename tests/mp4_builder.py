"""MP4 buatan (ftyp, moov/mvhd, mdat) untuk menguji pembaca waktu rekam, tanpa video sungguhan."""

import struct
from datetime import UTC, datetime

EPOCH_1904 = datetime(1904, 1, 1, tzinfo=UTC)


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def mvhd(when: datetime | None, version: int = 0) -> bytes:
    secs = 0 if when is None else int((when - EPOCH_1904).total_seconds())
    if version == 1:
        body = bytes([1, 0, 0, 0]) + struct.pack(">QQ", secs, secs)
    else:
        body = bytes([0, 0, 0, 0]) + struct.pack(">II", secs, secs)
    return box(b"mvhd", body + b"\x00" * 80)


def mp4(when, moov_first=True, version=0) -> bytes:
    ftyp = box(b"ftyp", b"isom" + b"\x00" * 4)
    moov = box(b"moov", mvhd(when, version))
    mdat = box(b"mdat", b"\x00" * 2000)
    return ftyp + (moov + mdat if moov_first else mdat + moov)
