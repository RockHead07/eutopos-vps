"""Waktu rekam sebuah video dari kotak mvhd di dalam berkasnya (ISO BMFF: MP4 dan MOV).

Ponsel menulis creation_time saat merekam, jadi nilainya bertahan walau berkas disalin (tanggal
berkas tidak). Dibaca dengan seek antar kotak, tanpa memuat isi video. Gagal baca atau nilai yang
tidak masuk akal berarti tidak diketahui (None), bukan tebakan.
"""

import struct
from datetime import UTC, datetime, timedelta
from pathlib import Path

EPOCH_1904 = datetime(1904, 1, 1, tzinfo=UTC)  # mvhd menghitung detik sejak 1 Jan 1904
EARLIEST = datetime(2000, 1, 1, tzinfo=UTC)  # perangkat yang jamnya belum diatur menulis epoch
MAX_BOXES = 10_000  # batas pengaman untuk berkas rusak


def _find(f, start: int, end: int, kind: bytes) -> tuple[int, int] | None:
    """Cari kotak `kind` di antara start dan end. Hasil: (awal isi, akhir kotak)."""
    pos, n = start, 0
    while pos + 8 <= end and n < MAX_BOXES:
        n += 1
        f.seek(pos)
        head = f.read(8)
        if len(head) < 8:
            return None
        size, k = struct.unpack(">I4s", head)
        hdr = 8
        if size == 1:  # ukuran 64-bit menyusul
            big = f.read(8)
            if len(big) < 8:
                return None
            size, hdr = struct.unpack(">Q", big)[0], 16
        elif size == 0:  # sampai akhir berkas
            size = end - pos
        if size < hdr:  # kotak rusak: tidak maju, hentikan
            return None
        if k == kind:
            return pos + hdr, min(pos + size, end)
        pos += size
    return None


def recorded_at(path: Path) -> datetime | None:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            moov = _find(f, 0, size, b"moov")
            if moov is None:
                return None
            mvhd = _find(f, moov[0], moov[1], b"mvhd")
            if mvhd is None:
                return None
            f.seek(mvhd[0])
            version = f.read(4)[:1]
            body = f.read(8 if version == b"\x01" else 4)
            if len(body) < (8 if version == b"\x01" else 4):
                return None
            secs = struct.unpack(">Q" if version == b"\x01" else ">I", body)[0]
    except (OSError, struct.error, ValueError):
        return None
    if secs == 0:
        return None
    try:
        when = EPOCH_1904 + timedelta(seconds=secs)
    except OverflowError:
        return None
    return when if EARLIEST <= when <= datetime.now(UTC) + timedelta(days=1) else None
