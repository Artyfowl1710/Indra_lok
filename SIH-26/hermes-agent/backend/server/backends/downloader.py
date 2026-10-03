"""
Artifactory + local_path + hf_id model download/resolution.

hf_id path is gated behind settings.allow_hf_download — False by default.
In air-gapped deployments this flag must never be True.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

import httpx

from server.config import settings
from server.core.schemas import ModelSource

log = logging.getLogger(__name__)


async def resolve_model(source: ModelSource, model_id: str) -> Path:
    """
    Download / locate the model and return its local path.
    Never makes outbound internet calls unless allow_hf_download is True.
    """
    dest = settings.models_dir / model_id
    dest.mkdir(parents=True, exist_ok=True)

    if source.type == "local_path":
        p = Path(source.path)
        if not p.exists():
            raise FileNotFoundError(f"Local path not found: {p}")
        return p

    if source.type == "artifactory":
        return await _download_artifactory(source.path, dest)

    if source.type == "hf_id":
        if not settings.allow_hf_download:
            raise PermissionError(
                "hf_id source is disabled in this deployment (allow_hf_download=False). "
                "Use artifactory or local_path instead."
            )
        return await _download_hf(source.hf_id, dest)

    raise ValueError(f"Unknown source type: {source.type}")


async def _download_artifactory(artifact_path: str, dest: Path) -> Path:
    if not settings.artifactory_url:
        raise RuntimeError("artifactory_url is not configured")

    url = f"{settings.artifactory_url.rstrip('/')}/{settings.artifactory_repo}/{artifact_path}"
    headers = {}
    if settings.artifactory_token:
        headers["Authorization"] = f"Bearer {settings.artifactory_token}"
    elif settings.artifactory_user:
        import base64
        creds = base64.b64encode(
            f"{settings.artifactory_user}:{settings.artifactory_token}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {creds}"

    log.info("Downloading from Artifactory: %s", url)
    async with httpx.AsyncClient(timeout=3600.0) as client:
        async with client.stream("GET", url, headers=headers) as r:
            r.raise_for_status()
            # Determine filename from Content-Disposition or URL
            filename = artifact_path.split("/")[-1]
            out_path = dest / filename
            with open(out_path, "wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)

    log.info("Downloaded to %s", out_path)
    return out_path


async def _download_hf(hf_id: str, dest: Path) -> Path:
    """
    Uses huggingface_hub snapshot_download.
    ONLY called when allow_hf_download=True (non-air-gapped environments).
    """
    log.warning(
        "Downloading from HuggingFace Hub (%s). "
        "This makes outbound internet calls — not for air-gapped deployments.",
        hf_id,
    )
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise RuntimeError("huggingface_hub is not installed; cannot use hf_id source")

    local = snapshot_download(repo_id=hf_id, local_dir=str(dest))
    return Path(local)
