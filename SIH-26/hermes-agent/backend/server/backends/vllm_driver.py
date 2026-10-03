"""
vLLM backend driver.

One vLLM process per base model (or standalone model).
LoRA adapters share a base process via vLLM's multi-LoRA serving.

Port allocation: settings.vllm_base_port + index (tracked in ModelRecord.process_port).
"""
from __future__ import annotations

import asyncio
import logging
import signal
import subprocess
from typing import Optional

import httpx

from server.config import settings
from server.db import ModelRecord, SessionLocal

log = logging.getLogger(__name__)

# model_id → Popen
_processes: dict[str, subprocess.Popen] = {}
_clients: dict[int, httpx.AsyncClient] = {}   # port → client


def _client_for(port: int) -> httpx.AsyncClient:
    if port not in _clients or _clients[port].is_closed:
        _clients[port] = httpx.AsyncClient(
            base_url=f"http://{settings.vllm_host}:{port}", timeout=600.0
        )
    return _clients[port]


def _next_free_port() -> int:
    used = set()
    with SessionLocal() as db:
        for m in db.query(ModelRecord).filter(ModelRecord.backend == "vllm").all():
            if m.process_port:
                used.add(m.process_port)
    for p in range(settings.vllm_base_port, settings.vllm_max_port + 1):
        if p not in used:
            return p
    raise RuntimeError("No free vLLM ports available")


# ── process management ────────────────────────────────────────────────────────

async def load_model(model_id: str) -> None:
    if model_id in _processes and _processes[model_id].poll() is None:
        return  # already running

    with SessionLocal() as db:
        m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        if m is None:
            raise KeyError(model_id)

        local_path = m.local_path or m.source_ref
        base_model_id = m.base_model_id

        # LoRA adapter: load onto existing base process
        if base_model_id:
            base = db.query(ModelRecord).filter(ModelRecord.id == base_model_id).first()
            if base and base.process_port:
                await _load_lora(base.process_port, model_id, local_path)
                return

        # Standalone or base model: start new process
        port = m.process_port or _next_free_port()
        m.process_port = port
        db.commit()

    await _start_process(model_id, local_path, port)


async def _start_process(model_id: str, model_path: str, port: int) -> None:
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", model_path,
        "--port", str(port),
        "--host", settings.vllm_host,
        "--trust-remote-code",
        "--disable-log-requests",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    _processes[model_id] = proc
    log.info("vLLM process started for %s on port %d (pid %d)", model_id, port, proc.pid)

    # Wait for the server to become ready (up to 120s)
    client = _client_for(port)
    for _ in range(120):
        await asyncio.sleep(1)
        try:
            r = await client.get("/health")
            if r.status_code == 200:
                log.info("vLLM %s ready", model_id)
                return
        except httpx.ConnectError:
            pass
    raise RuntimeError(f"vLLM process for {model_id} did not become ready in time")


async def _load_lora(base_port: int, adapter_id: str, adapter_path: str) -> None:
    client = _client_for(base_port)
    r = await client.post(
        "/v1/load_lora_adapter",
        json={"lora_name": adapter_id, "lora_path": adapter_path},
    )
    r.raise_for_status()
    log.info("LoRA adapter %s loaded onto base port %d", adapter_id, base_port)


async def unload_model(model_id: str) -> None:
    with SessionLocal() as db:
        m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        if m is None:
            return
        base_model_id = m.base_model_id
        port = m.process_port

    # LoRA adapter: unload from base process, keep base alive
    if base_model_id:
        with SessionLocal() as db:
            base = db.query(ModelRecord).filter(ModelRecord.id == base_model_id).first()
            if base and base.process_port:
                client = _client_for(base.process_port)
                try:
                    await client.post(
                        "/v1/unload_lora_adapter",
                        json={"lora_name": model_id},
                    )
                except Exception as exc:
                    log.warning("Failed to unload LoRA %s: %s", model_id, exc)
        return

    # Standalone: kill process
    proc = _processes.pop(model_id, None)
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.info("vLLM process for %s stopped", model_id)

    if port and port in _clients:
        await _clients.pop(port).aclose()


def get_port(model_id: str) -> Optional[int]:
    with SessionLocal() as db:
        m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        return m.process_port if m else None


async def proxy_chat(model_id: str, body: dict) -> httpx.Response:
    port = get_port(model_id)
    if port is None:
        raise RuntimeError(f"No port for vLLM model {model_id}")
    return await _client_for(port).post("/v1/chat/completions", json=body)


async def proxy_embeddings(model_id: str, body: dict) -> httpx.Response:
    port = get_port(model_id)
    if port is None:
        raise RuntimeError(f"No port for vLLM model {model_id}")
    return await _client_for(port).post("/v1/embeddings", json=body)


def stop_all() -> None:
    for model_id, proc in list(_processes.items()):
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    _processes.clear()
    log.info("All vLLM processes stopped")
