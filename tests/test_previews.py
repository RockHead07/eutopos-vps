"""Uji pratinjau job: pemilihan frame pertama dan pengecilan gambar, dengan JPEG buatan."""

import cv2
import numpy as np
import pytest

from server.previews import WIDTH, first_frame, make_preview


def jpeg(path, w=1280, h=720, color=(10, 120, 200)):
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.full((h, w, 3), color, dtype=np.uint8))
    return path


def vid(name, role="peta"):
    return {"path": f"/data/uploads/{name}", "role": role}


def test_first_frame_belongs_to_the_first_map_video(tmp_path):
    jpeg(tmp_path / "aaa_00000.jpg")  # video lain yang urutan namanya lebih awal
    want = jpeg(tmp_path / "zzz_00000.jpg")
    jpeg(tmp_path / "zzz_00001.jpg")
    assert first_frame(tmp_path, [vid("zzz"), vid("aaa")]) == want


def test_query_videos_are_not_used(tmp_path):
    want = jpeg(tmp_path / "peta_00000.jpg")
    jpeg(tmp_path / "uji_00000.jpg")
    assert first_frame(tmp_path, [vid("uji", "uji"), vid("peta")]) == want


def test_stem_is_matched_exactly_not_as_a_prefix(tmp_path):
    jpeg(tmp_path / "a_b_00000.jpg")  # milik video "a_b", bukan "a"
    assert first_frame(tmp_path, [vid("a")]) == tmp_path / "a_b_00000.jpg"  # jatuh ke cadangan
    want = jpeg(tmp_path / "a_00000.jpg")
    assert first_frame(tmp_path, [vid("a")]) == want


def test_glob_characters_in_a_cli_file_name_are_literal(tmp_path):
    want = jpeg(tmp_path / "rekaman[1]_00000.jpg")
    jpeg(tmp_path / "rekaman1_00000.jpg")
    assert first_frame(tmp_path, [{"path": "/x/rekaman[1].mp4", "role": "peta"}]) == want


def test_falls_back_to_any_frame_and_none_when_empty(tmp_path):
    assert first_frame(tmp_path, [vid("x")]) is None
    want = jpeg(tmp_path / "lain_00003.jpg")
    assert first_frame(tmp_path, [vid("x")]) == want


def test_preview_is_downscaled_and_keeps_the_aspect_ratio(tmp_path):
    jpeg(tmp_path / "m" / "v_00000.jpg", 1920, 1080)
    out = tmp_path / "out" / "preview.jpg"
    out.parent.mkdir()
    assert make_preview(tmp_path / "m", [vid("v")], out) is True
    h, w = cv2.imread(str(out)).shape[:2]
    assert (w, h) == (WIDTH, 360)
    assert not (out.parent / "preview.tmp.jpg").exists()  # berkas sementara tidak tertinggal


def test_small_frames_are_not_enlarged(tmp_path):
    jpeg(tmp_path / "m" / "v_00000.jpg", 320, 240)
    out = tmp_path / "preview.jpg"
    assert make_preview(tmp_path / "m", [vid("v")], out) is True
    assert cv2.imread(str(out)).shape[:2] == (240, 320)


@pytest.mark.parametrize(
    "content", [b"jpg", b"", b"\xff\xd8\xff"], ids=["teks", "kosong", "terpotong"]
)
def test_unreadable_frame_gives_false_and_no_file(tmp_path, content):
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "v_00000.jpg").write_bytes(content)
    out = tmp_path / "preview.jpg"
    assert make_preview(tmp_path / "m", [vid("v")], out) is False
    assert not out.exists()


def test_missing_frames_folder_gives_false(tmp_path):
    assert make_preview(tmp_path / "tidak-ada", [vid("v")], tmp_path / "preview.jpg") is False


def test_existing_preview_is_replaced_atomically(tmp_path):
    jpeg(tmp_path / "m" / "v_00000.jpg", 800, 600)
    out = jpeg(tmp_path / "preview.jpg", 10, 10)
    assert make_preview(tmp_path / "m", [vid("v")], out) is True
    assert cv2.imread(str(out)).shape[1] == WIDTH
