"""Catatan tiap permintaan /localize: bukti latensi dan penolakan koreksi (roadmap M1-6).

Yang dicatat: hasil, kode HTTP, inlier, waktu per tahap, ukuran foto, area dan versi peta.
Yang TIDAK dicatat: gambar, pose atau posisi pengguna, alamat IP, identitas. Posisi hanya sah
selama sesi AR aktif (ADR-007, ADR-011); log operasi tidak boleh menjadi jejak lokasi.

Mencatat tidak boleh merusak lokalisasi: tanpa DATABASE_URL tidak ada yang dicatat, dan galat
database hanya masuk log proses.
"""

import logging
import os
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import delete
from sqlmodel import Session, create_engine, select

from server import uploads
from server.db import LocalizeRequest

# ponytail: batas jumlah baris, bukan umur. Naikkan KEEP bila perlu riwayat lebih lama.
KEEP = 50_000
PRUNE_EVERY = 1000  # pangkas tiap kelipatan ini, bukan di tiap permintaan

router = APIRouter()
log = logging.getLogger("eutopos")


@lru_cache
def _engine(url: str):
    return create_engine(url)


def record(entry: dict) -> None:
    """Simpan satu baris. Tidak pernah melempar."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return
    try:
        with Session(_engine(url)) as s:
            row = LocalizeRequest(**entry)
            s.add(row)
            s.commit()
            if row.id % PRUNE_EVERY == 0:
                s.exec(delete(LocalizeRequest).where(LocalizeRequest.id <= row.id - KEEP))
                s.commit()
    except Exception:
        log.exception("gagal mencatat permintaan /localize")


@router.get("/api/localize-log")
def list_log(
    user: uploads.User,
    s: uploads.DB,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[LocalizeRequest]:
    stmt = select(LocalizeRequest).order_by(LocalizeRequest.id.desc()).limit(limit)
    return list(s.exec(stmt))
