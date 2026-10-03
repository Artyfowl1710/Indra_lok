"""
GPU VRAM accounting — reads nvidia-smi, no network calls.
Falls back gracefully when no GPU is present (CPU-only / CI).
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class GpuStats:
    id: int
    used_mb: int
    total_mb: int

    @property
    def free_mb(self) -> int:
        return self.total_mb - self.used_mb


def query_gpus() -> list[GpuStats]:
    """Return per-GPU stats. Returns empty list if nvidia-smi is unavailable."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            timeout=5,
            stderr=subprocess.DEVNULL,
        ).decode()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []

    gpus: list[GpuStats] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            gpus.append(GpuStats(id=int(parts[0]), used_mb=int(parts[1]), total_mb=int(parts[2])))
    return gpus


def total_free_vram_mb() -> int:
    return sum(g.free_mb for g in query_gpus())


async def probe_vram_delta_mb(fn: Callable[[], Any]) -> int | None:
    """
    Call fn() (which loads a model), measure nvidia-smi delta.
    Supports both sync and async callables.
    Returns delta in MB, or None if measurement is unreliable.
    """
    before = {g.id: g.used_mb for g in query_gpus()}
    
    if inspect.iscoroutinefunction(fn) or asyncio.iscoroutinefunction(fn):
        res = await fn()
    else:
        res = fn()
        if inspect.isawaitable(res):
            await res

    if not before:
        return None

    after = {g.id: g.used_mb for g in query_gpus()}
    delta = sum(after.get(gid, 0) - used for gid, used in before.items())
    return max(delta, 0) if delta >= 0 else None


def estimate_vram_heuristic(local_path: str | Path | None) -> int:
    """
    Fallback VRAM estimation based on model file size or defaults.
    Returns estimated VRAM in MB with a logged warning.
    """
    if local_path and Path(local_path).exists():
        size_bytes = Path(local_path).stat().st_size
        size_mb = int(size_bytes / (1024 * 1024))
        est_mb = max(size_mb, int(size_mb * 1.2))
        log.warning(
            "nvidia-smi unavailable; estimating VRAM footprint as %d MB from model file %s",
            est_mb,
            local_path,
        )
        return est_mb

    log.warning("nvidia-smi unavailable; defaulting estimated VRAM footprint to 4096 MB")
    return 4096
