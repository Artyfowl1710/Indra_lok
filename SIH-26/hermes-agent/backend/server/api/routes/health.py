"""
Health + client-config endpoints.
GET /v1/health
GET /v1/client-config
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from server.config import settings
from server.core.auth import require_auth
from server.core.gpu import query_gpus
from server.core.schemas import ClientConfig, GpuInfo, HealthResponse
from server.db import ApiKey, ModelRecord, get_db

router = APIRouter(tags=["health"])


@router.get("/v1/health", response_model=HealthResponse)
def health(
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_auth),
):
    gpus = [GpuInfo(id=g.id, used_mb=g.used_mb, total_mb=g.total_mb) for g in query_gpus()]
    loaded = [
        m.id
        for m in db.query(ModelRecord).filter(ModelRecord.status.in_(["idle", "busy"])).all()
    ]
    return HealthResponse(status="ok", gpu=gpus, models_loaded=loaded)


@router.get("/v1/client-config", response_model=ClientConfig)
def client_config(_: ApiKey = Depends(require_auth)):
    """
    Hermes reads this on startup to auto-configure itself.
    All org-wide references are grounded here — clients need only the server URL + API key.
    """
    return ClientConfig(
        api_base=settings.public_api_base or f"https://{settings.host}:{settings.port}",
        qdrant_url=f"http://{settings.qdrant_host}:{settings.qdrant_port}",
        qdrant_collection=settings.qdrant_collection,
        rag_embedding_model_id=settings.rag_embedding_model_id,
        supported_backends=["llamaswap", "vllm", "onnxruntime", "comfyui"],
        server_version="0.1.0",
    )
