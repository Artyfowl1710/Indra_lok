"""
Central configuration — every value has an env-var override.
No value here makes a network call at import time.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    # ── server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1  # single-process; see architecture decision in spec
    log_level: str = "info"

    # ── TLS (nginx handles termination; these paths are for the self-signed
    #         cert generator that runs on first `workbench up`) ───────────────
    tls_cert_path: Path = Path("certs/server.crt")
    tls_key_path: Path = Path("certs/server.key")
    tls_self_signed: bool = True  # flipped to False when a real CA cert is provided

    # ── database ──────────────────────────────────────────────────────────────
    db_path: Path = Path("data/workbench.db")

    # ── model storage ─────────────────────────────────────────────────────────
    models_dir: Path = Path("models")

    # ── llama-swap ────────────────────────────────────────────────────────────
    llamaswap_bin: Path = Path("bin/llama-swap")
    llamaswap_config: Path = Path("config/llama-swap.yaml")
    llamaswap_port: int = 8100
    llamaswap_watch_config: bool = True

    # ── vLLM ──────────────────────────────────────────────────────────────────
    vllm_base_port: int = 8200          # each vLLM process gets base_port + index
    vllm_max_port: int = 8299
    vllm_host: str = "127.0.0.1"

    # ── ONNX Runtime ──────────────────────────────────────────────────────────
    onnx_base_port: int = 8300
    onnx_host: str = "127.0.0.1"

    # ── ComfyUI ───────────────────────────────────────────────────────────────
    comfyui_port: int = 8400
    comfyui_host: str = "127.0.0.1"
    comfyui_models_dir: Path = Path("models/comfyui")
    comfyui_workflows_dir: Path = Path("config/workflows")

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333
    qdrant_collection: str = "workbench_rag"

    # ── RAG ───────────────────────────────────────────────────────────────────
    rag_embedding_model_id: str = ""    # must be set before /v1/rag/* is usable
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64

    # ── lifecycle manager ─────────────────────────────────────────────────────
    lifecycle_poll_interval_s: int = 60
    model_default_ttl_s: int = 600      # 10 minutes idle → unload

    # ── profile-level concurrency cap (see Kaggle note in spec) ───────────────
    max_concurrent_vllm_processes: int = 0   # 0 = unbounded (VRAM-limited only)

    # ── Artifactory ───────────────────────────────────────────────────────────
    artifactory_url: str = ""           # e.g. http://artifactory.internal/artifactory
    artifactory_repo: str = "models"
    artifactory_user: str = ""
    artifactory_token: str = ""

    # ── feature flags ─────────────────────────────────────────────────────────
    allow_hf_download: bool = False     # MUST stay False in air-gapped deployments
    allow_raw_workflow: bool = False    # POST /v1/generate/raw_workflow (admin only)

    # ── sandbox ───────────────────────────────────────────────────────────────
    sandbox_output_dir: Path = Path("data/sandbox_output")
    sandbox_default_timeout_s: int = 30
    sandbox_memory_mb: int = 512
    sandbox_cpu_count: int = 1
    sandbox_gvisor_runtime: str = "runsc"

    # ── client-config endpoint (what Hermes reads on startup) ─────────────────
    # These are derived at runtime; kept here so they can be overridden via env.
    public_api_base: str = ""           # e.g. https://workbench.internal:8443

    @field_validator("db_path", "models_dir", "sandbox_output_dir", mode="before")
    @classmethod
    def _make_path(cls, v: str | Path) -> Path:
        return Path(v)


settings = Settings()
