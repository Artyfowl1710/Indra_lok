"""
SQLAlchemy models + session factory.
Single SQLite file; WAL mode for safe concurrent reads with one writer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, Integer, String, Text, create_engine, event
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from server.config import settings


# ── engine ────────────────────────────────────────────────────────────────────

def _make_engine():
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{settings.db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = _make_engine()
_SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def SessionLocal() -> Session:
    return _SessionLocal()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── base ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── tables ────────────────────────────────────────────────────────────────────

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)   # public identifier
    key_hash: Mapped[str] = mapped_column(String(256))                          # argon2 hash
    owner: Mapped[str] = mapped_column(String(128))
    scope: Mapped[str] = mapped_column(Enum("admin", "user", name="key_scope"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class ModelRecord(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)   # user-supplied name
    backend: Mapped[str] = mapped_column(String(32))                  # llamaswap|vllm|onnxruntime|comfyui
    model_type: Mapped[str] = mapped_column(String(32))               # text|coding|vlm|embedding|image-gen|…
    task_tags: Mapped[str] = mapped_column(Text)                      # JSON array stored as text
    source_type: Mapped[str] = mapped_column(String(32))              # artifactory|local_path|hf_id
    source_ref: Mapped[str] = mapped_column(Text)                     # path / hf repo id / artifactory path
    local_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # resolved after download
    status: Mapped[str] = mapped_column(
        String(16), default="cold"
    )  # cold|loading|idle|busy|unloading
    vram_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    base_vram_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    adapter_overhead_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    base_model_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # for LoRA adapters
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    ttl_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # None → use global default
    active_requests: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # backend-specific: port assigned to this model's process (vLLM / ONNX)
    process_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(128))
    job_type: Mapped[str] = mapped_column(String(16))   # image|video|audio
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed
    result_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
