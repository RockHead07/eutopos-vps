import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spike"))
from run import add_sequential_pairs


def test_pairs_stay_within_one_video_and_keep_retrieval_pairs(tmp_path):
    pairs = tmp_path / "pairs-sfm.txt"
    pairs.write_text("mapping/a_00000.jpg mapping/b_00001.jpg", encoding="utf-8")  # tanpa \n akhir
    refs = [f"mapping/a_{i:05d}.jpg" for i in range(3)] + ["mapping/b_00000.jpg"]

    add_sequential_pairs(pairs, refs, 2)

    lines = pairs.read_text(encoding="utf-8").split("\n")
    assert lines == [
        "mapping/a_00000.jpg mapping/b_00001.jpg",
        "mapping/a_00000.jpg mapping/a_00001.jpg",
        "mapping/a_00000.jpg mapping/a_00002.jpg",
        "mapping/a_00001.jpg mapping/a_00002.jpg",
    ]
