"""Pasang align.json (per versi peta) dan navgraph.json (per area) dengan pemeriksaan.

align.json ditulis spike/eval_meter.py di folder hasil uji, tetapi layanan membacanya dari folder
peta aktif (server/localizer.py). Semua berkas diperiksa dulu; berkas rusak berarti tidak ada yang
disalin. Penulisan lewat berkas sementara lalu os.replace, jadi layanan tidak pernah membaca
setengah.
"""

import json
import logging
import math
import os
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from server import navgraph
from server.db import Alignment, MapVersion
from server.navgraph import _number
from server.pipeline import run_dir

log = logging.getLogger("eutopos")


MIN_ARCORE_FRAMES = 10


def validate_align(data) -> dict:
    m = data.get("meter_from_model") if isinstance(data, dict) else None
    if not isinstance(m, dict):
        raise ValueError("meter_from_model tidak ada")
    scale, q, t = m.get("scale"), m.get("rotation_xyzw"), m.get("translation")
    if not _number(scale) or scale <= 0:
        raise ValueError("scale harus angka positif")
    if not (isinstance(q, list) and len(q) == 4 and all(_number(v) for v in q)):
        raise ValueError("rotation_xyzw harus 4 angka")
    if abs(math.hypot(*q) - 1.0) > 1e-3:
        raise ValueError("rotation_xyzw harus kuaternion satuan")
    if not (isinstance(t, list) and len(t) == 3 and all(_number(v) for v in t)):
        raise ValueError("translation harus 3 angka")
    method = data.get("method", "survey")
    if method == "survey":
        rp = data.get("reference_points")
        if not isinstance(rp, int) or isinstance(rp, bool) or rp < 4:
            raise ValueError("reference_points harus bilangan bulat >= 4")
        if not _number(data.get("residual_median_m")):
            raise ValueError("residual_median_m tidak ada")
    elif method == "arcore_pose":
        matched = data.get("matched_frames")
        if not isinstance(matched, int) or isinstance(matched, bool) or matched < MIN_ARCORE_FRAMES:
            raise ValueError(f"matched_frames harus bilangan bulat >= {MIN_ARCORE_FRAMES}")
        for field in ("residual_median_m", "residual_max_m"):
            if not _number(data.get(field)):
                raise ValueError(f"{field} harus angka berhingga")
    elif method == "known_distance":
        _validate_known_distances(data)
    else:
        raise ValueError(f"method penyelarasan tidak dikenal: {method!r}")
    return data


def _validate_known_distances(data: dict) -> None:
    pairs = data.get("known_distances")
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 2:
        raise ValueError("known_distances harus daftar 1 atau 2 pasangan")
    for pair in pairs:
        if not isinstance(pair, dict):
            raise ValueError("entri known_distances harus objek JSON")
        for field in ("frame_a", "frame_b"):
            if not isinstance(pair.get(field), str) or not pair[field].strip():
                raise ValueError(f"{field} harus nama frame")
        for field in ("distance_m", "model_distance"):
            distance = pair.get(field)
            if not _number(distance) or distance <= 0:
                raise ValueError(f"{field} harus angka positif berhingga")
    if not _number(data.get("gravity_spread_deg")):
        raise ValueError("gravity_spread_deg harus angka berhingga")
    if len(pairs) == 2 and not _number(data.get("scale_spread_percent")):
        raise ValueError("scale_spread_percent harus angka berhingga untuk dua pasangan")


class AlignFile:
    """align.json versi peta, dibaca ulang saat berkasnya berganti (manage align menulis atomik).

    Diperiksa dengan stat di setiap permintaan, jadi align.json yang dipasang untuk versi aktif
    langsung berlaku tanpa memuat ulang layanan. Berkas rusak tidak menggantikan penyelarasan
    terakhir yang sah; berkas yang dihapus berarti belum diselaraskan.
    """

    def __init__(self, path: Path):
        self.path = path
        self._stamp = self._data = None

    def get(self) -> dict | None:
        try:
            st = self.path.stat()
        except FileNotFoundError:
            self._stamp = self._data = None
            return None
        stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
        if stamp != self._stamp:
            self._stamp = stamp  # berkas rusak tidak dicoba lagi sampai berkasnya berganti
            try:
                self._data = validate_align(_read(self.path))
            except ValueError as e:
                log.warning("align.json diabaikan, penyelarasan sebelumnya tetap dipakai: %s", e)
        return self._data


class DbAlign:
    """Penyelarasan yang diterapkan lewat dashboard, dibaca dari tabel alignment (satu per versi).

    Database adalah pemiliknya: kontainer api memasang /maps hanya-baca, jadi dashboard tidak
    menulis align.json. Dicek di setiap permintaan lewat satu kueri id (berindeks); isinya hanya
    dibaca ulang saat id yang berlaku berganti, jadi penerapan baru langsung berlaku tanpa restart.
    Database yang gagal tidak menggantikan penyelarasan terakhir yang sah. Tanpa baris applied,
    hasilnya None dan Localizer memakai align.json (manage align).
    """

    def __init__(self, engine, version_id: int):
        self.engine, self.version_id = engine, version_id
        self._id = self._data = None

    def get(self) -> dict | None:
        try:
            with Session(self.engine) as s:
                row_id = s.exec(
                    select(Alignment.id).where(
                        Alignment.map_version_id == self.version_id, Alignment.status == "applied"
                    )
                ).first()
                if row_id is None:
                    self._id = self._data = None
                elif row_id != self._id:
                    self._data = validate_align(s.get(Alignment, row_id).params)
                    self._id = row_id
        except (SQLAlchemyError, ValueError, RuntimeError) as e:
            log.warning("penyelarasan dari database diabaikan, yang terakhir tetap dipakai: %s", e)
        return self._data


def version_alignment(session: Session, version: MapVersion, maps_root: Path) -> dict | None:
    """Ambil penyelarasan versi dari database atau berkas di bawah akar peta."""
    db_align = DbAlign(session.get_bind(), version.id).get()
    if db_align is not None:
        return db_align
    # Satu pemilik jalur: sama dengan Localizer (<versi>/kp*-r*/align.json), bukan folder job.
    p = (run_dir(Path(version.path)) / "align.json").resolve()
    if p.is_relative_to(maps_root.resolve()) and p.is_file():
        return AlignFile(p).get()
    return None


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{path}: {e}") from e


def _write_atomic(dst: Path, data: dict) -> None:
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, dst)


def install(
    map_dir: Path,
    run_name: str,
    area_dir: Path,
    align_src: Path | None,
    navgraph_src: Path | None,
) -> tuple[list[Path], list[str]]:
    if align_src is None and navgraph_src is None:
        raise ValueError("tidak ada yang dipasang: beri --align dan/atau --navgraph")
    run_dir = map_dir / run_name
    plan, warnings = [], []
    if align_src is not None:
        if not run_dir.is_dir():
            raise ValueError(f"folder run tidak ada: {run_dir}")
        plan.append((run_dir / "align.json", validate_align(_read(align_src))))
    if navgraph_src is not None:
        graph = navgraph.validate(_read(navgraph_src))
        if lost := navgraph.disconnected_nodes(graph):
            first = graph["nodes"][0]["id"]
            warnings.append(f"simpul tidak terhubung ke {first}: {', '.join(lost)}")
        plan.append((area_dir / navgraph.FILE_NAME, graph))
    area_dir.mkdir(parents=True, exist_ok=True)
    for dst, data in plan:  # baru menulis setelah semua masukan lolos pemeriksaan
        _write_atomic(dst, data)
    return [dst for dst, _ in plan], warnings
