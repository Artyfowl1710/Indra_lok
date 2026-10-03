"""
Profile-based configuration: small / medium / large / auto.
Probes nvidia-smi for 'auto'.
"""
from __future__ import annotations

import logging
from typing import Literal

from server.core.gpu import query_gpus

log = logging.getLogger(__name__)

Profile = Literal["small", "medium", "large", "auto"]

_PROFILE_VLLM_CAP = {
    "small": 1,
    "medium": 2,
    "large": 0,   # unbounded
}


def resolve_profile(profile: Profile) -> str:
    if profile != "auto":
        return profile
    gpus = query_gpus()
    if not gpus:
        log.info("No GPU detected; using 'small' profile")
        return "small"
    total_vram = sum(g.total_mb for g in gpus)
    if total_vram >= 40_000:
        return "large"
    if total_vram >= 16_000:
        return "medium"
    return "small"


def apply_profile(profile: str) -> None:
    from server.config import settings
    cap = _PROFILE_VLLM_CAP.get(profile, 0)
    settings.max_concurrent_vllm_processes = cap
    log.info("Profile '%s' applied: max_concurrent_vllm_processes=%d", profile, cap)
