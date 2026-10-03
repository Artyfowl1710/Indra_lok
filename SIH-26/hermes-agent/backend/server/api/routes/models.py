"""
Model registry endpoints.
GET  /v1/catalog
POST /v1/models
GET  /v1/models
DELETE /v1/models/{id}
GET  /v1/models/{id}/status
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from server.backends.downloader import resolve_model
from server.backends import llamaswap as ls_driver
from server.config import settings
from server.core.auth import require_admin
from server.core.lifecycle import BusyModelError, lifecycle
from server.core.model_routing import (
    PUBLIC_MODEL_ALIASES,
    alias_for,
    alias_target,
)
from server.core.schemas import (
    ModelRegisterRequest, ModelResponse, ModelStatusResponse,
    ManifestEntry, SyncReport,
)
from server.db import ApiKey, ModelRecord, get_db

log = logging.getLogger(__name__)
router = APIRouter(tags=["models"])

# Keep these aligned with backend/config/llama-swap.yaml. The client uses this
# metadata to decide when to compact; reporting 16K for a 32K server caused
# premature compaction and repeated summary failures on document tasks.
_CONTEXT_LENGTH_BY_MODEL = {
    "gemma-2-2b-it": 32768,
    "qwen3.5-4b": 32768,
    "qwen2-vl-ocr-2b-instruct": 32768,
}


def _model_context_length(model_id: str) -> int:
    return _CONTEXT_LENGTH_BY_MODEL.get(model_id, 16384)


# ── helpers ───────────────────────────────────────────────────────────────────

def _row_to_response(m: ModelRecord) -> ModelResponse:
    return ModelResponse(
        id=m.id,
        backend=m.backend,
        type=m.model_type,
        task_tags=json.loads(m.task_tags or "[]"),
        status=m.status,
        vram_mb=m.vram_mb,
        pinned=m.pinned,
    )


def _openai_model_payload(m: ModelRecord) -> dict:
    r = _row_to_response(m)
    return {
        **r.model_dump(),
        "context_length": _model_context_length(m.id),
        "object": "model",
        "created": 0,
        "owned_by": "workbench",
    }


def _alias_payload(alias, target: ModelRecord, *, exposed_id: str | None = None) -> dict:
    return {
        "id": exposed_id or alias.id,
        "backend": target.backend,
        "type": alias.model_type,
        "task_tags": list(alias.task_tags),
        "status": target.status,
        "vram_mb": target.vram_mb,
        "pinned": False,
        "context_length": _model_context_length(target.id),
        "object": "model",
        "created": 0,
        "owned_by": "workbench-router",
        "display_name": alias.display_name,
        "description": alias.description,
        "alias_for": alias.target_model or "automatic",
    }


async def _register_one(req: ModelRegisterRequest, db: Session) -> ModelRecord:
    existing = db.query(ModelRecord).filter(ModelRecord.id == req.name).first()
    if existing:
        raise HTTPException(409, f"Model {req.name!r} already registered")

    local_path = await resolve_model(req.source, req.name)

    row = ModelRecord(
        id=req.name,
        backend=req.backend,
        model_type=req.type,
        task_tags=json.dumps(req.task_tags),
        source_type=req.source.type,
        source_ref=req.source.path or req.source.hf_id or "",
        local_path=str(local_path),
        status="cold",
        vram_mb=req.vram_mb,
        pinned=req.pinned,
        ttl_s=req.ttl_s,
        base_model_id=req.base_model_id,
        registered_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # For llamaswap: write config entry immediately so it's ready on first request
    if req.backend == "llamaswap":
        ls_driver.add_model_to_config(req.name, str(local_path))

    # Pin the RAG embedding model against eviction
    if settings.rag_embedding_model_id and req.name == settings.rag_embedding_model_id:
        row.pinned = True
        db.commit()

    log.info("Registered model %s (backend=%s)", req.name, req.backend)
    return row


_catalog_cache: dict[str, tuple[float, dict]] = {}
_CATALOG_TTL_S = 30.0


@router.get("/v1/catalog")
async def get_catalog(_: ApiKey = Depends(require_admin)):
    """
    Returns everything available in Artifactory (not just registered models).
    Requires a configured Artifactory URL. Caches responses for 30s.
    """
    if not settings.artifactory_url:
        return {"items": [], "note": "Artifactory not configured"}

    now = datetime.utcnow().timestamp()
    cache_key = f"{settings.artifactory_url}:{settings.artifactory_repo}"
    if cache_key in _catalog_cache:
        ts, cached_data = _catalog_cache[cache_key]
        if now - ts < _CATALOG_TTL_S:
            return cached_data

    url = f"{settings.artifactory_url.rstrip('/')}/api/storage/{settings.artifactory_repo}?deep=1"
    headers = {}
    if settings.artifactory_token:
        headers["Authorization"] = f"Bearer {settings.artifactory_token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
            _catalog_cache[cache_key] = (now, data)
            return data
    except Exception as exc:
        raise HTTPException(502, f"Artifactory unreachable: {exc}")


# ── register ──────────────────────────────────────────────────────────────────

@router.post("/v1/models", status_code=201, response_model=ModelResponse)
async def register_model(
    req: ModelRegisterRequest,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    row = await _register_one(req, db)
    return _row_to_response(row)


# ── list ──────────────────────────────────────────────────────────────────────

@router.get("/v1/models")
def list_models(
    task_tags: str | None = None,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    q = db.query(ModelRecord)
    rows = q.all()
    rows_by_id = {m.id: m for m in rows}
    result = [_openai_model_payload(m) for m in rows]
    result.extend(
        _alias_payload(alias, rows_by_id[alias_target(alias)])
        for alias in PUBLIC_MODEL_ALIASES
        if alias_target(alias) in rows_by_id
    )
    if task_tags:
        wanted = {t.strip() for t in task_tags.split(",")}
        result = [r for r in result if wanted & set(r["task_tags"])]
    return {"object": "list", "data": result}


@router.get("/v1/models/{model_id}")
def get_model(
    model_id: str,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    """OpenAI-compatible single-model lookup used by client capability probes."""
    m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if m is not None:
        return _openai_model_payload(m)

    alias = alias_for(model_id)
    if alias is None:
        raise HTTPException(404, "Model not found")
    target = db.query(ModelRecord).filter(ModelRecord.id == alias_target(alias)).first()
    if target is None:
        raise HTTPException(404, "Alias target is not registered")
    return _alias_payload(alias, target, exposed_id=model_id)


# ── status ────────────────────────────────────────────────────────────────────

@router.get("/v1/models/{model_id}/status", response_model=ModelStatusResponse)
def model_status(
    model_id: str,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if m is None:
        alias = alias_for(model_id)
        if alias is not None:
            m = db.query(ModelRecord).filter(ModelRecord.id == alias_target(alias)).first()
    if m is None:
        raise HTTPException(404, "Model not found")
    return ModelStatusResponse(id=model_id, status=m.status)


# ── delete ────────────────────────────────────────────────────────────────────

@router.delete("/v1/models/{model_id}", status_code=204)
async def delete_model(
    model_id: str,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if m is None:
        raise HTTPException(404, "Model not found")
    try:
        await lifecycle.force_unload(model_id)
    except BusyModelError as exc:
        raise HTTPException(409, str(exc))

    if m.backend == "llamaswap":
        ls_driver.remove_model_from_config(model_id)

    db.delete(m)
    db.commit()
    log.info("Deregistered model %s", model_id)


# ── sync (declarative manifest) ───────────────────────────────────────────────

@router.post("/v1/models/sync", response_model=SyncReport)
async def sync_models(
    entries: list[ManifestEntry],
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    desired = {e.name: e for e in entries}
    current = {m.id: m for m in db.query(ModelRecord).all()}

    report = SyncReport(registered=[], removed=[], skipped_busy=[], unchanged=[])

    # Register new
    for name, entry in desired.items():
        if name not in current:
            req = ModelRegisterRequest(
                name=entry.name,
                source=entry.source,
                backend=entry.backend,
                type=entry.type,
                task_tags=entry.task_tags,
                pinned=entry.pinned,
                ttl_s=entry.ttl_s,
                vram_mb=entry.vram_mb,
                base_model_id=entry.base_model_id,
            )
            await _register_one(req, db)
            report.registered.append(name)
        else:
            report.unchanged.append(name)

    # Remove stale
    for name, row in current.items():
        if name not in desired:
            if row.active_requests > 0:
                report.skipped_busy.append(name)
                log.warning("sync: cannot remove busy model %s; skipping", name)
                continue
            try:
                await lifecycle.force_unload(name)
            except BusyModelError:
                report.skipped_busy.append(name)
                continue
            if row.backend == "llamaswap":
                ls_driver.remove_model_from_config(name)
            db.delete(row)
            db.commit()
            report.removed.append(name)

    return report
