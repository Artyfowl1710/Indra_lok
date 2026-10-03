"""
llama-swap backend driver.

llama-swap is an unmodified Go binary that:
  - reads a YAML config listing GGUF model paths + llama-server args
  - hot-reloads that config when it changes (--watch-config)
  - exposes an OpenAI-compatible HTTP API

Our job:
  - write / patch the YAML config when models are added/removed
  - manage the llama-swap process lifecycle (start/stop)
  - proxy /v1/chat/completions and /v1/embeddings to it
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
from pathlib import Path
from typing import Optional

import httpx
import yaml

from server.config import settings
from server.db import ModelRecord, SessionLocal

log = logging.getLogger(__name__)

_process: Optional[subprocess.Popen] = None
_client: Optional[httpx.AsyncClient] = None


import threading

_client_lock = threading.Lock()

def _base_url() -> str:
    return f"http://127.0.0.1:{settings.llamaswap_port}"


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        with _client_lock:
            if _client is None or _client.is_closed:
                _client = httpx.AsyncClient(base_url=_base_url(), timeout=300.0)
    return _client


# â”€â”€ config management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _read_config() -> dict:
    p = settings.llamaswap_config
    if p.exists():
        return yaml.safe_load(p.read_text()) or {}
    return {"models": {}}


def _write_config(cfg: dict) -> None:
    settings.llamaswap_config.parent.mkdir(parents=True, exist_ok=True)
    settings.llamaswap_config.write_text(yaml.dump(cfg, default_flow_style=False))


def add_model_to_config(model_id: str, local_path: str, extra_args: list[str] | None = None) -> None:
    cfg = _read_config()
    # Loading a registered model must retain its tuned server command.
    if cfg.get("models", {}).get(model_id, {}).get("cmd") and extra_args is None:
        return
    bin_dir = Path(settings.llamaswap_bin).resolve().parent
    server_candidate = bin_dir / ("llama-server.exe" if sys.platform == "win32" else "llama-server")
    server_bin = str(server_candidate) if server_candidate.exists() else ("llama-server.exe" if sys.platform == "win32" else "llama-server")
    cfg.setdefault("models", {})[model_id] = {
        "cmd": subprocess.list2cmdline([
            server_bin,
            "--host", "127.0.0.1", "--port", "${PORT}",
            "--model", local_path, *(extra_args or []),
        ]),
    }
    _write_config(cfg)
    log.info("llama-swap config updated: added %s", model_id)


def remove_model_from_config(model_id: str) -> None:
    cfg = _read_config()
    cfg.setdefault("models", {}).pop(model_id, None)
    _write_config(cfg)
    log.info("llama-swap config updated: removed %s", model_id)


# â”€â”€ process management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def start() -> None:
    global _process
    if _process and _process.poll() is None:
        return  # already running

    bin_path = settings.llamaswap_bin
    if not Path(bin_path).exists():
        log.error("llama-swap binary not found at %s; GGUF serving unavailable", bin_path)
        raise FileNotFoundError(f"llama-swap binary not found at {bin_path}")

    cmd = [
        str(bin_path),
        "--config", str(settings.llamaswap_config),
        "--listen", f"127.0.0.1:{settings.llamaswap_port}",
    ]
    if settings.llamaswap_watch_config:
        cmd.append("--watch-config")

    settings.llamaswap_config.parent.mkdir(parents=True, exist_ok=True)
    if not settings.llamaswap_config.exists():
        _write_config({"models": {}})

    _process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.info("llama-swap started (pid %d) on port %d", _process.pid, settings.llamaswap_port)


def stop() -> None:
    global _process
    if _process and _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _process.kill()
        log.info("llama-swap stopped")
    _process = None


def is_running() -> bool:
    """Return True if llama-swap is reachable on its configured port."""
    if _process is not None and _process.poll() is None:
        return True

    try:
        r = httpx.get(
            f"{_base_url()}/v1/models",
            timeout=2.0,
        )
        return r.status_code == 200
    except Exception:
        return False


async def get_loaded_models() -> set[str]:
    """Return model IDs currently reported as loaded by llama-swap."""
    try:
        r = await get_client().get("/v1/models")
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.warning("Could not query llama-swap model state: %s", exc)
        return set()

    loaded: set[str] = set()

    for item in data.get("data", []):
        model_id = item.get("id")
        status = item.get("status", {})

        if (
            model_id
            and isinstance(status, dict)
            and status.get("value") == "loaded"
        ):
            loaded.add(model_id)

    return loaded

# â”€â”€ lifecycle callbacks (injected into ModelLifecycleManager) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def load_model(model_id: str) -> None:
    """
    llama-swap handles loading lazily on first request after config update.
    We just ensure the config entry exists and the process is running.
    """
    with SessionLocal() as db:
        m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        if m and m.local_path:
            add_model_to_config(model_id, m.local_path)
    if not is_running():
        start()
    # Give llama-swap a moment to pick up the config change
    await asyncio.sleep(0.5)


async def unload_model(model_id: str) -> None:
    """Leave residency and idle eviction to llama-swap's configured TTL."""
    await asyncio.sleep(0)


# â”€â”€ proxy helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def proxy_chat(request_body: dict) -> httpx.Response:
    return await get_client().post("/v1/chat/completions", json=request_body)


async def proxy_embeddings(request_body: dict) -> httpx.Response:
    return await get_client().post("/v1/embeddings", json=request_body)

