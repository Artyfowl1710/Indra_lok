"""
ComfyUI backend driver.

ComfyUI runs as a single process in --listen mode.
We submit jobs via its /prompt endpoint and poll /history/{prompt_id}.
Workflow templates live in config/workflows/{image,video,audio}.json
and are parameterized with {prompt, model_checkpoint, **params}.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import subprocess
import sys
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

import httpx

from server.config import settings

log = logging.getLogger(__name__)

_process: Optional[subprocess.Popen] = None
_client: Optional[httpx.AsyncClient] = None


def _base_url() -> str:
    return f"http://{settings.comfyui_host}:{settings.comfyui_port}"


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=_base_url(), timeout=600.0)
    return _client


# ── process management ────────────────────────────────────────────────────────

def start(comfyui_dir: str) -> None:
    global _process
    if _process and _process.poll() is None:
        return
    cmd = [
        sys.executable,
        "main.py",
        "--listen", settings.comfyui_host,
        "--port", str(settings.comfyui_port),
        "--output-directory", str(settings.comfyui_models_dir / "output"),
        "--disable-auto-launch",
    ]
    _process = subprocess.Popen(cmd, cwd=comfyui_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.info("ComfyUI started (pid %d) on port %d", _process.pid, settings.comfyui_port)


def stop() -> None:
    global _process
    if _process and _process.poll() is None:
        _process.send_signal(signal.SIGTERM)
        try:
            _process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            _process.kill()
    _process = None


def is_running() -> bool:
    return _process is not None and _process.poll() is None


# ── workflow templating ───────────────────────────────────────────────────────

def _load_template(job_type: str) -> dict:
    path = settings.comfyui_workflows_dir / f"{job_type}.json"
    if not path.exists():
        raise FileNotFoundError(f"Workflow template not found: {path}")
    return json.loads(path.read_text())


def _fill_template(template: dict, prompt: str, checkpoint: str, params: dict[str, Any]) -> dict:
    """
    Walk the workflow graph and substitute sentinel values:
      __PROMPT__       → prompt text
      __CHECKPOINT__   → model checkpoint filename
      __SEED__         → random seed (from params or generated)
      any key in params that matches a node input name
    """
    wf = deepcopy(template)
    seed = params.pop("seed", None) or (uuid.uuid4().int % (2**32))

    def _sub(obj):
        if isinstance(obj, str):
            return (
                obj.replace("__PROMPT__", prompt)
                   .replace("__CHECKPOINT__", checkpoint)
                   .replace("__SEED__", str(seed))
            )
        if isinstance(obj, dict):
            return {k: _sub(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sub(i) for i in obj]
        return obj

    wf = _sub(wf)

    # Apply remaining params as node-level overrides: params = {"node_id.input_name": value}
    for key, value in params.items():
        if "." in key:
            node_id, input_name = key.split(".", 1)
            if node_id in wf and "inputs" in wf[node_id]:
                wf[node_id]["inputs"][input_name] = value

    return wf


# ── job submission ────────────────────────────────────────────────────────────

async def submit_job(job_type: str, prompt: str, checkpoint: str, params: dict) -> str:
    """Submit a generation job. Returns ComfyUI prompt_id."""
    template = _load_template(job_type)
    workflow = _fill_template(template, prompt, checkpoint, params)
    client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}
    r = await get_client().post("/prompt", json=payload)
    r.raise_for_status()
    return r.json()["prompt_id"]


async def poll_job(prompt_id: str) -> dict:
    """Returns ComfyUI history entry for prompt_id, or {} if not done."""
    r = await get_client().get(f"/history/{prompt_id}")
    if r.status_code == 200:
        data = r.json()
        return data.get(prompt_id, {})
    return {}


async def wait_for_job(prompt_id: str, poll_interval: float = 2.0, timeout: float = 600.0) -> dict:
    elapsed = 0.0
    while elapsed < timeout:
        result = await poll_job(prompt_id)
        if result:
            return result
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError(f"ComfyUI job {prompt_id} timed out after {timeout}s")


# ── lifecycle callbacks ───────────────────────────────────────────────────────

async def load_model(model_id: str) -> None:
    """ComfyUI manages its own checkpoint loading; we just ensure the process is up."""
    if not is_running():
        comfyui_dir = settings.comfyui_models_dir.parent / "ComfyUI"
        start(str(comfyui_dir))
        # Wait for ComfyUI to be ready
        for _ in range(60):
            await asyncio.sleep(2)
            try:
                r = await get_client().get("/system_stats")
                if r.status_code == 200:
                    return
            except httpx.ConnectError:
                pass
        raise RuntimeError("ComfyUI did not start in time")


async def unload_model(model_id: str) -> None:
    """ComfyUI handles its own memory; we don't kill the process per-model."""
    pass
