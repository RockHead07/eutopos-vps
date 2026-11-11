"""Sequential splat worker; map builds take priority and only training holds the GPU.

Run with ``python -m server.splat_worker``. External tools run through worker.run;
pruning stays in this process and needs only the lightweight SOG dependencies.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlmodel import select

from server import splat_jobs, splat_pipeline
from server.db import MapJob, MapVersion, SplatJob, engine_from_env
from server.gpu_lock import gpu_lock
from server.jobs import ERROR_MAX
from server.worker import (
    DATA,
    MAPS,
    MIN_FREE_BYTES,
    POLL_S,
    StageError,
    log_tail,
    run,
    worker_session,
)
from spike.splat_prune import prune_sog

# Pelatih memakai ±2,0 GiB di atas keadaan awal pada 401 frame (Task 8 B7, 10 Nov 2026: total
# 3.397 MiB dengan lokalisasi produksi 1.375 MiB; torch melaporkan puncak 1,5 GiB). Ambang dua
# kali angka itu. Lantai besar belum diukur: naikkan bila terukur lebih besar.
MIN_FREE_VRAM_MIB = 4096


def free_vram_mib(timeout: float = 120.0) -> int | None:
    """VRAM bebas (MiB) menurut torch di lingkungan pelatih; None bila tidak terukur."""
    code = "import torch; print(torch.cuda.mem_get_info()[0] // 2**20)"
    try:
        done = subprocess.run(
            [splat_pipeline.TRAIN_PYTHON, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if done.returncode != 0:
            return None
        value = int(done.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None
    return value if value >= 0 else None


def _number(value) -> float | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if ok else None


def train_metrics(result: Path, steps: int) -> dict | None:
    """Metrik evaluasi langkah terakhir dari statistik pelatih; None bila tidak terbaca.

    Hanya pelengkap laporan: tidak pernah melempar dan tidak boleh menggagalkan pekerjaan.
    """
    stats = result / "stats"

    def read(name):
        try:
            data = json.loads((stats / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    val = read(f"val_step{steps - 1}.json")
    if val is None:
        return None
    psnr, ssim, lpips = (_number(val.get(k)) for k in ("psnr", "ssim", "lpips"))
    if None in (psnr, ssim, lpips):
        return None
    train = read(f"train_step{steps - 1}_rank0.json") or {}
    mem = _number(train.get("mem"))
    return {
        "psnr": round(psnr, 3),
        "ssim": round(ssim, 4),
        "lpips": round(lpips, 4),
        "peak_mem_gb": None if mem is None else round(mem, 3),
    }


def process(
    session,
    job: SplatJob,
    data: Path,
    maps: Path,
    runner=run,
    lock=None,
    free_bytes=lambda p: shutil.disk_usage(p).free,
    clock=time.monotonic,
    free_vram=free_vram_mib,
) -> None:
    log = None
    stage_seconds = {}
    current_stage, started = None, None

    def stage(name):
        nonlocal current_stage, started
        now = clock()
        if current_stage is not None:
            stage_seconds[current_stage] = now - started
        current_stage, started = name, now
        splat_jobs.set_stage(session, job, name)

    try:
        stage("inputs")
        lock = (lambda: gpu_lock(session.get_bind())) if lock is None else lock
        version_id = session.exec(
            select(MapVersion.id).where(MapVersion.id == job.map_version_id)
        ).first()
        if version_id is None:
            raise StageError("map version no longer exists")
        map_job = session.exec(select(MapJob).where(MapJob.map_version_id == version_id)).first()
        if map_job is None:
            raise StageError(
                "this map version has no build job, so there are no frames to train on"
            )
        map_dir = Path(
            session.exec(select(MapVersion.path).where(MapVersion.id == version_id)).one()
        )
        root, resolved = maps.resolve(), map_dir.resolve()
        if resolved == root or not resolved.is_relative_to(root):
            raise StageError(f"refusing to write outside the maps folder: {map_dir}")
        dataset = splat_pipeline.dataset_dir(data, map_job.id)
        mapping = dataset / "mapping"
        if not mapping.is_dir() or not any(p.is_file() for p in mapping.iterdir()):
            raise StageError(f"frames for this map are gone: {mapping}")
        sfm = splat_pipeline.sfm_dir(map_dir)
        if not sfm.is_dir():
            raise StageError(f"sfm model for this map is missing: {sfm}")
        if min(free_bytes(data), free_bytes(maps)) < MIN_FREE_BYTES:
            raise StageError("less than 20 GB of free disk; job not started")

        work = splat_pipeline.work_dir(data, map_job.id)
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        log = work / "log.txt"
        prepared, result = work / "prepared", work / "result"
        steps, min_opacity = job.params["steps"], job.params["min_opacity"]

        stage("prepare")
        runner(splat_pipeline.prepare_command(sfm, dataset, prepared), log)
        stage("gpu_wait")
        with lock():
            # Tidak terukur (None) tidak memblokir: pelatih sendiri akan gagal dengan galat jelas.
            vram_free = free_vram()
            if vram_free is not None and vram_free < MIN_FREE_VRAM_MIB:
                raise StageError(
                    f"not enough free GPU memory: {vram_free} MiB free, "
                    f"{MIN_FREE_VRAM_MIB} MiB needed; the GPU is busy, rebuild later"
                )
            stage("train")
            runner(splat_pipeline.train_command(prepared, result, steps), log)
            metrics = train_metrics(result, steps)
        stage("check")
        ply = splat_pipeline.ply_path(result, steps)
        runner(splat_pipeline.check_command(ply, sfm), log)
        ratios = re.findall(
            r"Ratio \(distance / box_width\): ([0-9.eE+-]+)",
            log.read_text(encoding="utf-8", errors="replace") if log.exists() else "",
        )
        check_ratio = float(ratios[-1]) if ratios else None
        stage("convert")
        scene, pruned = work / "scene.sog", work / "scene-pruned.sog"
        runner(splat_pipeline.convert_command(ply, scene), log)
        if not scene.is_file():
            raise StageError("convert produced no scene.sog")
        stage("prune")
        pruning = prune_sog(scene, pruned, min_opacity=min_opacity)

        stage("place")
        exists = session.exec(select(MapVersion.id).where(MapVersion.id == version_id)).first()
        if exists is None or not map_dir.is_dir():
            raise StageError("map folder is gone; nothing was placed")
        splat = map_dir / "splat"
        splat.mkdir(exist_ok=True)
        scene_tmp = splat / f".scene.sog.tmp.{uuid4().hex}"
        report_tmp = splat / f".report.json.tmp.{uuid4().hex}"
        try:
            shutil.copyfile(pruned, scene_tmp)
            # Capture place through the copy, before serialization/publication: the
            # report cannot include timings for its own future atomic replacements.
            stage_seconds["place"] = clock() - started
            summary = {
                "steps": steps,
                "min_opacity": min_opacity,
                "check_ratio": check_ratio,
                "gaussians_before": pruning["in_count"],
                "gaussians_after": pruning["out_count"],
                "bytes_before": pruning["in_bytes"],
                "bytes_after": pruning["out_bytes"],
                "stage_seconds": stage_seconds,
                "built_at": datetime.now(UTC).isoformat(),
                "metrics": metrics,
                "vram_free_mib": vram_free,
            }
            report_tmp.write_text(json.dumps(summary), encoding="utf-8")
            os.replace(report_tmp, splat / "report.json")
            # scene.sog is the availability flag; its report must already be present.
            os.replace(scene_tmp, splat / "scene.sog")
        finally:
            scene_tmp.unlink(missing_ok=True)
            report_tmp.unlink(missing_ok=True)
        splat_jobs.finish(session, job, summary)
        try:
            shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass  # Cleanup is best effort after the successful database commit.
    except Exception as exc:
        try:
            session.rollback()
            msg = str(exc)[: ERROR_MAX // 2]
            try:
                tail = log_tail(log) if log is not None else ""
            except Exception:
                tail = ""
            tail = tail[-(ERROR_MAX - len(msg) - 1) :]
            splat_jobs.fail(session, job, f"{msg}\n{tail}".strip())
        except Exception as failure:
            # A deleted version may have CASCADE-deleted this job during training.
            try:
                session.rollback()
            except Exception:
                pass
            detail = " ".join(str(failure).splitlines())
            print(
                f"warning: could not mark splat job failed: {detail}", file=sys.stderr, flush=True
            )


def map_work_pending(session) -> bool:
    return (
        session.exec(select(MapJob.id).where(MapJob.status.in_(["queued", "running"]))).first()
        is not None
    )


def claim_when_idle(session) -> SplatJob | None:
    # A map queue that never empties can starve splats; accepted for v1.
    if map_work_pending(session):
        return None
    return splat_jobs.claim_next(session)


def main() -> None:
    engine = engine_from_env()
    with worker_session(engine) as session:
        count = splat_jobs.recover_stale(session)
        print(f"{count} splat jobs recovered as failed", flush=True)
    print("splat-worker siap", flush=True)
    while True:
        with worker_session(engine) as session:
            job = claim_when_idle(session)
            if job is None:
                time.sleep(POLL_S)
                continue
            job_id = job.id
            print(f"splat job {job_id} started", flush=True)
            process(session, job, DATA, MAPS)
            status = session.exec(select(SplatJob.status).where(SplatJob.id == job_id)).first()
            print(f"splat job {job_id}: {status if status is not None else 'deleted'}", flush=True)


if __name__ == "__main__":
    main()
