"""Uji pembaca waktu rekam video (kotak mvhd) dengan berkas MP4 buatan, tanpa video sungguhan."""

import struct
from datetime import UTC, datetime, timedelta

import pytest
from mp4_builder import mp4

from server.video_meta import recorded_at


@pytest.fixture
def write(tmp_path):
    def _write(data: bytes, name="v.mp4"):
        p = tmp_path / name
        p.write_bytes(data)
        return p

    return _write


WHEN = datetime(2026, 10, 1, 4, 15, 49, tzinfo=UTC)


@pytest.mark.parametrize("moov_first", [True, False])
@pytest.mark.parametrize("version", [0, 1])
def test_reads_creation_time_wherever_the_moov_box_is(write, moov_first, version):
    # Android menaruh moov di akhir berkas, iPhone dan banyak penyunting di awal.
    assert recorded_at(write(mp4(WHEN, moov_first, version))) == WHEN


def test_zero_means_unknown(write):
    assert recorded_at(write(mp4(None))) is None


def test_implausible_dates_are_rejected(write):
    # Beberapa perangkat menulis epoch 1904 atau tanggal jauh di depan saat jamnya belum diatur.
    assert recorded_at(write(mp4(datetime(1999, 1, 1, tzinfo=UTC)))) is None
    assert recorded_at(write(mp4(datetime.now(UTC) + timedelta(days=30)))) is None


@pytest.mark.parametrize(
    "data",
    [b"", b"bukan video", b"\x00\x00\x00\x08ftyp", b"\xff" * 64],
    ids=["kosong", "teks", "terpotong", "sampah"],
)
def test_garbage_never_raises(write, data):
    assert recorded_at(write(data)) is None


def test_missing_file_is_unknown(tmp_path):
    assert recorded_at(tmp_path / "tidak-ada.mp4") is None


def test_file_cut_inside_the_mvhd_box_is_unknown(write):
    # ftyp (16 byte) + kepala moov (8) + kepala mvhd (8) + versi/flag (4) + separuh waktu (2)
    assert recorded_at(write(mp4(WHEN)[: 16 + 8 + 8 + 4 + 2])) is None


def test_box_with_zero_size_does_not_loop_forever(write):
    # Ukuran 0 berarti "sampai akhir berkas"; ukuran lain yang rusak tidak boleh membuat loop.
    bad = struct.pack(">I4s", 0, b"free") + b"\x00" * 16
    assert recorded_at(write(bad)) is None
    assert recorded_at(write(struct.pack(">I4s", 3, b"free") + b"\x00" * 32)) is None
