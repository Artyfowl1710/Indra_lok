"""
ONNX Runtime backend driver.

Thin FastAPI sub-process per model, wrapping onnxruntime.InferenceSession.
Supports text/embedding/VLM models exported to ONNX format.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx

from server.config import settings
from server.db import ModelRecord, SessionLocal

log = logging.getLogger(__name__)

_processes: dict[str, subprocess.Popen] = {}
_clients: dict[int, httpx.AsyncClient] = {}


def _client_for(port: int) -> httpx.AsyncClient:
    if port not in _clients or _clients[port].is_closed:
        _clients[port] = httpx.AsyncClient(
            base_url=f"http://{settings.onnx_host}:{port}", timeout=120.0
        )
    return _clients[port]


def _next_free_port() -> int:
    used = set()
    with SessionLocal() as db:
        for m in db.query(ModelRecord).filter(ModelRecord.backend == "onnxruntime").all():
            if m.process_port:
                used.add(m.process_port)
    for p in range(settings.onnx_base_port, settings.onnx_base_port + 99):
        if p not in used:
            return p
    raise RuntimeError("No free ONNX ports")


async def load_model(model_id: str) -> None:
    if model_id in _processes and _processes[model_id].poll() is None:
        return

    with SessionLocal() as db:
        m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        if m is None:
            raise KeyError(model_id)
        local_path = m.local_path or m.source_ref
        port = m.process_port or _next_free_port()
        m.process_port = port
        db.commit()

    # Launch the ONNX worker (server/backends/onnx_worker.py)
    worker = Path(__file__).parent / "onnx_worker.py"
    cmd = [sys.executable, str(worker), "--model-path", local_path, "--port", str(port)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    _processes[model_id] = proc
    log.info("ONNX worker started for %s on port %d", model_id, port)

    client = _client_for(port)
    for _ in range(60):
        await asyncio.sleep(1)
        try:
            r = await client.get("/health")
            if r.status_code == 200:
                return
        except httpx.ConnectError:
            pass
    raise RuntimeError(f"ONNX worker for {model_id} did not start in time")


async def unload_model(model_id: str) -> None:
    proc = _processes.pop(model_id, None)
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    with SessionLocal() as db:
        m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        if m and m.process_port and m.process_port in _clients:
            await _clients.pop(m.process_port).aclose()


async def proxy_infer(model_id: str, body: dict) -> httpx.Response:
    with SessionLocal() as db:
        m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        port = m.process_port if m else None
    if port is None:
        raise RuntimeError(f"No port for ONNX model {model_id}")
    return await _client_for(port).post("/infer", json=body)


async def proxy_chat(model_id: str, body: dict) -> httpx.Response:
    with SessionLocal() as db:
        m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        port = m.process_port if m else None
    if port is None:
        raise RuntimeError(f"No port for ONNX model {model_id}")
    return await _client_for(port).post("/v1/chat/completions", json=body)


async def proxy_embeddings(model_id: str, body: dict) -> httpx.Response:
    with SessionLocal() as db:
        m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
        port = m.process_port if m else None
    if port is None:
        raise RuntimeError(f"No port for ONNX model {model_id}")
    return await _client_for(port).post("/v1/embeddings", json=body)


def stop_all() -> None:
    for proc in _processes.values():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    _processes.clear()
