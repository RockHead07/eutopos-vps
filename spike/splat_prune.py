from __future__ import annotations

import argparse
import io
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

DEFAULT_MIN_OPACITY = 0.02  # L1, keputusan Bagus 8 Nov 2026: alpha-byte <= 5 dibuang


class SogError(ValueError):
    """Galat saat validasi atau pemrosesan arsip SOG."""


def _resolve_texture_files(meta: dict, namelist: set[str]) -> tuple[dict[str, str], list[str]]:
    """Tentukan nama berkas tekstur di dalam arsip zip sesuai spesifikasi SOG v2."""
    roles: dict[str, str] = {}

    # means: harus ada 2 berkas (means_l dan means_u)
    means_files = meta.get("means", {}).get("files")
    if not means_files or len(means_files) < 2:
        # Cadangan bila tidak tertulis di meta
        means_files = ["means_l.webp", "means_u.webp"]
    roles["means_l"] = means_files[0]
    roles["means_u"] = means_files[1]

    # quats: 1 berkas
    quats_files = meta.get("quats", {}).get("files")
    if not quats_files:
        quats_files = ["quats.webp"]
    roles["quats"] = quats_files[0]

    # scales: 1 berkas
    scales_files = meta.get("scales", {}).get("files")
    if not scales_files:
        scales_files = ["scales.webp"]
    roles["scales"] = scales_files[0]

    # sh0: 1 berkas
    sh0_files = meta.get("sh0", {}).get("files")
    if not sh0_files:
        sh0_files = ["sh0.webp"]
    roles["sh0"] = sh0_files[0]

    all_files = [roles["means_l"], roles["means_u"], roles["quats"], roles["scales"], roles["sh0"]]
    for f in all_files:
        if f not in namelist:
            raise SogError(f"Tekstur wajib tidak ditemukan dalam arsip: {f}")

    return roles, all_files


def prune_sog(
    src: Path | str,
    dst: Path | str,
    *,
    min_opacity: float = DEFAULT_MIN_OPACITY,
    drop_zero: bool = False,
    max_scale: float | None = None,
) -> dict:
    """Pangkas Gaussian dari arsip SOG v2 tanpa kuantisasi ulang.

    Menghasilkan berkas SOG baru di dst secara atomik.
    """
    src_path = Path(src)
    dst_path = Path(dst)

    if not (0.0 <= min_opacity < 1.0):
        raise SogError(f"min_opacity harus dalam rentang [0, 1), didapat {min_opacity}")

    if not src_path.exists():
        raise SogError(f"Berkas masukan tidak ditemukan: {src_path}")

    # Bandingkan jalur absolut untuk mencegah menimpa berkas sumber
    try:
        if src_path.resolve() == dst_path.resolve():
            raise SogError("Tujuan (dst) tidak boleh sama dengan sumber (src)")
    except OSError:
        pass

    if not zipfile.is_zipfile(src_path):
        raise SogError(f"Berkas bukan arsip zip yang valid: {src_path}")

    try:
        with zipfile.ZipFile(src_path, "r") as z_in:
            namelist = set(z_in.namelist())
            if "meta.json" not in namelist:
                raise SogError("meta.json tidak ditemukan dalam arsip SOG")

            try:
                meta = json.loads(z_in.read("meta.json").decode("utf-8"))
            except Exception as e:
                raise SogError(f"Gagal membaca meta.json: {e}") from e

            if "shN" in meta:
                raise SogError("SOG dengan pita SH (shN) belum didukung")

            count = meta.get("count")
            if type(count) is not int or count <= 0:
                raise SogError(f"meta.json memiliki count tidak valid: {count}")

            roles, file_list = _resolve_texture_files(meta, namelist)

            # Muat semua tekstur
            raw_imgs: dict[str, np.ndarray] = {}
            width: int | None = None
            height: int | None = None

            for fname in file_list:
                img_data = z_in.read(fname)
                try:
                    pil_img = Image.open(io.BytesIO(img_data)).convert("RGBA")
                except (OSError, ValueError) as e:  # UnidentifiedImageError turunan OSError
                    raise SogError(f"Tekstur {fname} tidak bisa dibaca: {e}") from e
                w, h = pil_img.size
                if width is None:
                    width, height = w, h
                elif (w, h) != (width, height):
                    raise SogError(
                        f"Dimensi tekstur {fname} ({w}x{h}) tidak cocok "
                        f"dengan tekstur lain ({width}x{height})"
                    )
                raw_imgs[fname] = np.asarray(pil_img)

    except zipfile.BadZipFile as e:
        raise SogError(f"Arsip zip rusak: {e}") from e

    assert width is not None and height is not None
    if count > width * height:
        raise SogError(f"count ({count}) melebihi dimensi tekstur ({width}x{height})")

    # Bentuk larik datar
    flat_imgs = {k: v.reshape(-1, 4)[:count] for k, v in raw_imgs.items()}

    # Hitung masker Gaussian yang dipertahankan
    sh0_file = roles["sh0"]
    alpha = flat_imgs[sh0_file][:, 3]
    keep = np.ones(count, dtype=bool)

    if drop_zero:
        keep &= alpha > 0

    if min_opacity > 0.0:
        keep &= (alpha / 255.0) >= min_opacity

    if max_scale is not None:
        codebook_raw = meta.get("scales", {}).get("codebook")
        if not codebook_raw:
            raise SogError("Codebook skala tidak ditemukan dalam meta.json")
        codebook = np.asarray(codebook_raw, dtype=np.float32)
        scales_file = roles["scales"]
        scale_indices = flat_imgs[scales_file][:, :3]
        smax = np.exp(codebook[scale_indices]).max(axis=1)
        keep &= smax <= max_scale

    n2 = int(keep.sum())
    if n2 == 0:
        raise SogError("Hasil pemangkasan nol Gaussian; tidak ada yang tersisa")

    # Hitung tinggi baru
    h2 = max(1, -(-n2 // width))  # pembagian pembulatan ke atas: ceil(n2 / width)

    # Susun ulang tekstur
    out_imgs: dict[str, np.ndarray] = {}
    for fname, flat_arr in flat_imgs.items():
        packed = np.zeros((width * h2, 4), dtype=np.uint8)
        packed[:n2] = flat_arr[keep]
        out_imgs[fname] = packed.reshape(h2, width, 4)

    meta_out = json.loads(json.dumps(meta))
    meta_out["count"] = n2

    # Penulisan atomik: tulis ke berkas sementara di folder tujuan, lalu os.replace
    dst_dir = dst_path.parent
    dst_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = dst_dir / f".{dst_path.name}.tmp.{uuid.uuid4().hex}"

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_STORED) as z_out:
            z_out.writestr("meta.json", json.dumps(meta_out))
            for fname, arr in out_imgs.items():
                buf = io.BytesIO()
                pil_out = Image.fromarray(arr, "RGBA")
                if fname.lower().endswith(".png"):
                    pil_out.save(buf, "PNG")
                else:
                    pil_out.save(buf, "WEBP", lossless=True, exact=True, method=6)
                z_out.writestr(fname, buf.getvalue())

        os.replace(tmp_path, dst_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    in_bytes = os.path.getsize(src_path)
    out_bytes = os.path.getsize(dst_path)
    removed = count - n2
    removed_pct = round(100.0 * removed / count, 3)

    return {
        "in_count": count,
        "out_count": n2,
        "removed": removed,
        "removed_pct": removed_pct,
        "in_bytes": in_bytes,
        "out_bytes": out_bytes,
        "rules": {
            "min_opacity": min_opacity,
            "drop_zero": drop_zero,
            "max_scale": max_scale,
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Antarmuka baris perintah (CLI) untuk pemangkas SOG."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="Pangkas Gaussian dari arsip SOG v2 tanpa kuantisasi ulang."
    )
    parser.add_argument("src", type=Path, help="Berkas SOG masukan")
    parser.add_argument("dst", type=Path, help="Berkas SOG keluaran")
    parser.add_argument(
        "--min-opacity",
        type=float,
        default=DEFAULT_MIN_OPACITY,
        help=f"Ambang batas opasitas minimum (bawaan: {DEFAULT_MIN_OPACITY})",
    )
    parser.add_argument(
        "--drop-zero",
        action="store_true",
        help="Buang Gaussian dengan alpha == 0",
    )
    parser.add_argument(
        "--max-scale",
        type=float,
        default=None,
        help="Ambang batas skala maksimum dalam satuan model",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Jalur berkas keluaran laporan JSON",
    )

    args = parser.parse_args(argv)

    try:
        rep = prune_sog(
            args.src,
            args.dst,
            min_opacity=args.min_opacity,
            drop_zero=args.drop_zero,
            max_scale=args.max_scale,
        )
    except SogError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    rep_json = json.dumps(rep)
    print(rep_json)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
