"""Uji klien tus: potongan, offset, dan metadata, dengan _request palsu (tanpa tusd)."""

import base64
from contextlib import contextmanager

from server import upload_client


class Resp:
    def __init__(self, headers):
        self.headers = headers


def test_upload_sends_chunks_with_matching_offsets(tmp_path, monkeypatch):
    video = tmp_path / "loop.mp4"
    video.write_bytes(b"x" * 25)
    calls = []

    @contextmanager
    def fake_request(method, url, headers, data=None):
        calls.append((method, url, headers, data))
        if method == "POST":
            yield Resp({"Location": "/files/job1-v0-abc"})
        else:
            yield Resp({"Upload-Offset": str(int(headers["Upload-Offset"]) + len(data))})

    monkeypatch.setattr(upload_client, "_request", fake_request)
    upload_client.upload(video, "http://tusd:8080/files/", job_id=1, chunk=10)

    post, *patches = calls
    assert post[2]["Upload-Length"] == "25"
    meta = dict(item.split(" ") for item in post[2]["Upload-Metadata"].split(","))
    assert {k: base64.b64decode(v).decode() for k, v in meta.items()} == {
        "job_id": "1",
        "name": "loop.mp4",
    }
    assert [p[1] for p in patches] == ["http://tusd:8080/files/job1-v0-abc"] * 3
    assert [p[2]["Upload-Offset"] for p in patches] == ["0", "10", "20"]
    assert [len(p[3]) for p in patches] == [10, 10, 5]


def test_upload_resends_from_server_offset(tmp_path, monkeypatch):
    video = tmp_path / "loop.mp4"
    video.write_bytes(bytes(range(20)))
    sent = []

    @contextmanager
    def fake_request(method, url, headers, data=None):
        if method == "POST":
            yield Resp({"Location": "/files/x"})
            return
        sent.append((int(headers["Upload-Offset"]), data))
        acked = 3 if len(sent) == 1 else len(data)  # server hanya menerima 3 byte pertama
        yield Resp({"Upload-Offset": str(int(headers["Upload-Offset"]) + acked)})

    monkeypatch.setattr(upload_client, "_request", fake_request)
    upload_client.upload(video, "http://tusd:8080/files/", job_id=1, chunk=10)
    assert sent[1][0] == 3 and sent[1][1] == bytes(range(3, 13))  # dilanjutkan dari offset server
