"""Pasang align.json (per versi peta) dan navgraph.json (per area) dengan pemeriksaan.

align.json ditulis spike/eval_meter.py di folder hasil uji, tetapi layanan membacanya dari folder
peta aktif (server/localizer.py). Semua berkas diperiksa dulu; berkas rusak berarti tidak ada yang
disalin. Penulisan lewat berkas sementara lalu os.replace, jadi layanan tidak pernah membaca
setengah.
"""

import json
import math
import os
from pathlib import Path

from server import navgraph
from server.navgraph import _number


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
    rp = data.get("reference_points")
    if not isinstance(rp, int) or isinstance(rp, bool) or rp < 4:
        raise ValueError("reference_points harus bilangan bulat >= 4")
    if not _number(data.get("residual_median_m")):
        raise ValueError("residual_median_m tidak ada")
    return data


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
