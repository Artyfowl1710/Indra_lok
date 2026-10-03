"""
Pydantic v2 schemas — single source of truth for every API shape.
No bare dicts cross module boundaries.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ── enums (as Literal unions so Pydantic validates them) ──────────────────────

Backend = Literal["llamaswap", "vllm", "onnxruntime", "comfyui"]
ModelType = Literal[
    "text",
    "coding",
    "vlm",
    "embedding",
    "image-gen",
    "video-gen",
    "audio-gen",
]
SourceType = Literal["artifactory", "local_path", "hf_id"]
ModelStatus = Literal["cold", "loading", "idle", "busy", "unloading"]
KeyScope = Literal["admin", "user"]
JobType = Literal["image", "video", "audio"]
JobStatus = Literal["queued", "running", "done", "failed"]
Language = Literal["python", "javascript", "bash", "r"]


# ── model source ─────────────────────────────────────────────────────────────

class ModelSource(BaseModel):
    type: SourceType
    path: Optional[str] = None
    hf_id: Optional[str] = None

    @model_validator(mode="after")
    def _check_ref(self) -> "ModelSource":
        if self.type == "hf_id" and not self.hf_id:
            raise ValueError("hf_id source requires hf_id field")
        if self.type in ("artifactory", "local_path") and not self.path:
            raise ValueError(f"{self.type} source requires path field")
        return self


# ── model registration ──────────────────────────────────────────────────────

class ModelRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    source: ModelSource
    backend: Backend
    type: ModelType
    task_tags: list[str] = Field(default_factory=list)
    pinned: bool = False
    ttl_s: Optional[int] = None
    vram_mb: Optional[int] = None
    base_model_id: Optional[str] = None


class ModelResponse(BaseModel):
    id: str
    backend: Backend
    type: ModelType
    task_tags: list[str]
    status: ModelStatus
    vram_mb: Optional[int]
    pinned: bool


class ModelStatusResponse(BaseModel):
    id: str
    status: ModelStatus


# ── chat / completions (OpenAI-compatible) ───────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None

    # OpenAI-compatible tool calling fields
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False

    # Preserve additional OpenAI-compatible fields, including:
    # tools, tool_choice, response_format, extra_body, etc.
    model_config = {"extra": "allow"}


# ── embeddings ───────────────────────────────────────────────────────────────

class EmbeddingRequest(BaseModel):
    model: str
    input: str | list[str]
    encoding_format: Literal["float", "base64"] = "float"


# ── generation jobs ──────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    model_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    model_config = {"protected_namespaces": ()}


class JobResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    result_url: Optional[str] = None
    error: Optional[str] = None


# ── RAG ──────────────────────────────────────────────────────────────────────

class RagQueryRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=100)


class RagChunk(BaseModel):
    text: str
    score: float
    source: str


class RagQueryResponse(BaseModel):
    chunks: list[RagChunk]


class RagIngestRequest(BaseModel):
    source_path: str


class RagIngestResponse(BaseModel):
    chunks_indexed: int


# ── sandbox ──────────────────────────────────────────────────────────────────

class SandboxRequest(BaseModel):
    code: str
    language: Language = "python"
    timeout_s: int = Field(default=30, ge=1, le=300)


class SandboxResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


# ── health ───────────────────────────────────────────────────────────────────

class GpuInfo(BaseModel):
    id: int
    used_mb: int
    total_mb: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    gpu: list[GpuInfo]
    models_loaded: list[str]


# ── admin keys ───────────────────────────────────────────────────────────────

class KeyCreateRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=128)
    scope: KeyScope


class KeyCreateResponse(BaseModel):
    api_key: str


class KeyListItem(BaseModel):
    id: str
    owner: str
    scope: KeyScope
    created_at: datetime
    last_used_at: Optional[datetime]
    revoked: bool


# ── client config ────────────────────────────────────────────────────────────

class ClientConfig(BaseModel):
    api_base: str
    qdrant_url: str
    qdrant_collection: str
    rag_embedding_model_id: str
    supported_backends: list[Backend]
    server_version: str
    model_config = {"protected_namespaces": ()}


# ── models.yaml manifest ─────────────────────────────────────────────────────

class ManifestEntry(BaseModel):
    name: str
    backend: Backend
    type: ModelType
    source: ModelSource
    task_tags: list[str] = Field(default_factory=list)
    pinned: bool = False
    ttl_s: Optional[int] = None
    vram_mb: Optional[int] = None
    base_model_id: Optional[str] = None


class ModelsManifest(BaseModel):
    models: list[ManifestEntry]


class SyncReport(BaseModel):
    registered: list[str]
    removed: list[str]
    skipped_busy: list[str]
    unchanged: list[str]