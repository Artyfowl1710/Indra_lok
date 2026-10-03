"""
RAG endpoints: /v1/rag/query and /v1/rag/ingest
Backed by Qdrant. Embedding model is pinned at startup via rag_embedding_model_id.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.backends import vllm_driver, llamaswap as ls_driver
from server.config import settings
from server.core.auth import require_auth
from server.core.lifecycle import lifecycle
from server.core.schemas import RagChunk, RagIngestRequest, RagIngestResponse, RagQueryRequest, RagQueryResponse
from server.db import ApiKey, ModelRecord, get_db

log = logging.getLogger(__name__)
router = APIRouter(tags=["rag"])

# Lazy imports — qdrant_client is only needed at runtime, not at import time
_qdrant = None


def _get_qdrant():
    global _qdrant
    if _qdrant is None:
        from qdrant_client import QdrantClient
        _qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _qdrant


def _ensure_collection():
    client = _get_qdrant()
    from qdrant_client.models import Distance, VectorParams
    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        # Vector size depends on embedding model; default 1536 (common for many models)
        # Will be updated on first ingest if different
        client.create_collection(
            settings.qdrant_collection,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )


async def _embed(texts: list[str]) -> list[list[float]]:
    """Get embeddings from the pinned RAG embedding model."""
    if not settings.rag_embedding_model_id:
        raise HTTPException(503, "rag_embedding_model_id not configured")

    from server.db import SessionLocal
    with SessionLocal() as db:
        m = db.query(ModelRecord).filter(ModelRecord.id == settings.rag_embedding_model_id).first()
        if m is None:
            raise HTTPException(503, f"Embedding model {settings.rag_embedding_model_id!r} not registered")
        backend = m.backend

    async with lifecycle.track_request(settings.rag_embedding_model_id):
        body = {"model": settings.rag_embedding_model_id, "input": texts}
        if backend == "vllm":
            resp = await vllm_driver.proxy_embeddings(settings.rag_embedding_model_id, body)
        elif backend == "llamaswap":
            resp = await ls_driver.proxy_embeddings(body)
        else:
            raise HTTPException(400, f"Backend {backend!r} does not support embeddings")

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)

        data = resp.json()
        return [item["embedding"] for item in data["data"]]


def _chunk_text(text: str) -> list[str]:
    size = settings.rag_chunk_size
    overlap = settings.rag_chunk_overlap
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunk = " ".join(words[i : i + size])
        chunks.append(chunk)
        i += size - overlap
    return chunks


# ── ingest ────────────────────────────────────────────────────────────────────

@router.post("/v1/rag/ingest", response_model=RagIngestResponse)
async def ingest(
    req: RagIngestRequest,
    _: ApiKey = Depends(require_auth),
):
    path = Path(req.source_path)
    if not path.exists():
        raise HTTPException(404, f"File not found: {req.source_path}")

    text = path.read_text(errors="replace")
    chunks = _chunk_text(text)
    if not chunks:
        return RagIngestResponse(chunks_indexed=0)

    embeddings = await _embed(chunks)
    _ensure_collection()

    from qdrant_client.models import PointStruct
    client = _get_qdrant()
    points = [
        PointStruct(
            id=int(hashlib.md5(f"{req.source_path}:{i}".encode()).hexdigest(), 16) % (2**63),
            vector=emb,
            payload={"text": chunk, "source": req.source_path, "chunk_index": i},
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)
    log.info("Ingested %d chunks from %s", len(points), req.source_path)
    return RagIngestResponse(chunks_indexed=len(points))


# ── query ─────────────────────────────────────────────────────────────────────

@router.post("/v1/rag/query", response_model=RagQueryResponse)
async def query(
    req: RagQueryRequest,
    _: ApiKey = Depends(require_auth),
):
    embeddings = await _embed([req.query])
    query_vec = embeddings[0]

    _ensure_collection()
    client = _get_qdrant()
    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vec,
        limit=req.top_k,
    )
    chunks = [
        RagChunk(
            text=r.payload.get("text", ""),
            score=r.score,
            source=r.payload.get("source", ""),
        )
        for r in results
    ]
    return RagQueryResponse(chunks=chunks)
