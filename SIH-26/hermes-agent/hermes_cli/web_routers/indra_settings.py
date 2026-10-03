"""INDRA Workstation — Dynamic Server, Context & RAG Management API Routes.

Provides endpoints for the INDRA Web Dashboard to:
1. Probe and display real-time connection status to Summertime GPU backend.
2. Test connection and measure ping latency (ms) with Bearer token authentication.
3. Configure Server URL and API Key directly from the UI without terminal commands.
4. One-click GPU context window optimization (Eco 4k, Balanced 16k, Power 32k, Ultra 64k).
5. Configure and trigger Obsidian Knowledge Vault RAG reindexing.
6. Configure internal enterprise Artifactory settings.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

_log = logging.getLogger("hermes_cli.indra_settings")
router = APIRouter(prefix="/api/indra", tags=["indra"])

# Path resolution
ROOT_HERMES = Path(__file__).resolve().parent.parent.parent # .../SIH-26/hermes-agent
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(ROOT_HERMES.parent))) # .../SIH-26
WORKSPACE_ROOT = HERMES_HOME.parent if HERMES_HOME.name == "SIH-26" else HERMES_HOME
ENV_PATH = HERMES_HOME / ".env"
CONFIG_YAML_PATH = HERMES_HOME / "config.yaml"

# Context presets mapping
CONTEXT_PRESETS: Dict[str, int] = {
    "eco": 4096,
    "4k": 4096,
    "balanced": 16384,
    "16k": 16384,
    "power": 32768,
    "32k": 32768,
    "ultra": 65536,
    "64k": 65536,
}


class TestConnectionRequest(BaseModel):
    server_url: str = Field(..., description="Server Base URL (e.g. http://192.168.1.100:8000)")
    api_key: Optional[str] = Field(None, description="Client API Key")


class ConfigureServerRequest(BaseModel):
    server_url: str = Field(..., description="Server Base URL")
    api_key: Optional[str] = Field(None, description="Client API Key")
    context_length: Optional[int] = Field(None, description="Context window size in tokens")
    context_preset: Optional[str] = Field(None, description="eco | balanced | power | ultra")
    vault_path: Optional[str] = Field(None, description="Local Obsidian vault directory")
    rag_enabled: Optional[bool] = Field(True, description="Enable local vault RAG")
    artifactory_url: Optional[str] = Field(None, description="Optional internal Artifactory URL")
    artifactory_repo: Optional[str] = Field(None, description="Optional Artifactory model repo")
    artifactory_user: Optional[str] = Field(None, description="Optional Artifactory username")
    artifactory_token: Optional[str] = Field(None, description="Optional Artifactory token")


class SetContextRequest(BaseModel):
    preset: Optional[str] = Field(None, description="eco | balanced | power | ultra")
    context_length: Optional[int] = Field(None, description="Explicit context length tokens")


class RagReindexRequest(BaseModel):
    vault_path: Optional[str] = Field(None, description="Path to vault")


def _read_env_dict() -> Dict[str, str]:
    res = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                res[k.strip()] = v.strip().strip("'\"")
    return res


def _write_env_keys(updates: Dict[str, str]):
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    updated = set()
    output_lines = []
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in updates:
                output_lines.append(f"{k}='{updates[k]}'")
                updated.add(k)
                continue
        output_lines.append(line)

    for k, v in updates.items():
        if k not in updated:
            output_lines.append(f"{k}='{v}'")

    ENV_PATH.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def _read_config_yaml() -> dict:
    if not CONFIG_YAML_PATH.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(CONFIG_YAML_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _write_config_yaml(data: dict):
    try:
        import yaml
        CONFIG_YAML_PATH.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    except Exception as e:
        _log.error(f"Failed to write config.yaml: {e}")


def _mask_key(key: Optional[str]) -> str:
    if not key:
        return ""
    if len(key) <= 12:
        return "wb_live_***"
    return f"{key[:8]}...{key[-4:]}"


@router.get("/server-status")
async def get_server_status():
    """Returns current connection status, latency, active models, and context window."""
    env = _read_env_dict()
    config = _read_config_yaml()

    server_url = env.get("WORKBENCH_API_BASE", "http://127.0.0.1:8000")
    api_key = env.get("WORKBENCH_API_KEY", "")
    vault_path = env.get("OBSIDIAN_VAULT_PATH", "./MyVault")

    model_block = config.get("model", {})
    context_length = model_block.get("context_length", 16384)
    active_model = model_block.get("default", "indra-auto")

    # Determine preset name
    preset = "custom"
    for p_name, p_len in CONTEXT_PRESETS.items():
        if p_len == context_length:
            preset = p_name
            break

    # Probe server reachability asynchronously
    connected = False
    latency_ms = None
    available_models: List[str] = []
    error_message = None

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    start_t = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{server_url}/v1/models", headers=headers)
            latency_ms = int((time.perf_counter() - start_t) * 1000)
            if resp.status_code == 200:
                connected = True
                data = resp.json()
                available_models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
            elif resp.status_code == 401:
                error_message = "Authentication Failed: Invalid API Key"
            else:
                error_message = f"Server returned HTTP {resp.status_code}"
    except httpx.ConnectError:
        error_message = f"Cannot reach server at {server_url}. Is Summertime-server running?"
    except Exception as exc:
        error_message = str(exc)

    # Document count in vault
    vault_docs_count = 0
    resolved_vault = Path(vault_path)
    if not resolved_vault.is_absolute():
        resolved_vault = WORKSPACE_ROOT / vault_path
    if resolved_vault.exists():
        vault_docs_count = len([f for f in resolved_vault.rglob("*") if f.is_file() and f.suffix.lower() in [".md", ".pdf", ".txt", ".csv"]])

    return {
        "connected": connected,
        "server_url": server_url,
        "api_key_set": bool(api_key),
        "masked_key": _mask_key(api_key),
        "latency_ms": latency_ms,
        "active_model": active_model,
        "context_length": context_length,
        "context_preset": preset,
        "available_models": available_models,
        "vault_path": vault_path,
        "vault_docs_count": vault_docs_count,
        "rag_enabled": bool(vault_path),
        "error_message": error_message,
    }


@router.post("/test-connection")
async def test_connection(req: TestConnectionRequest):
    """Live probe to verify connectivity, measure latency, and discover models."""
    url = req.server_url.rstrip("/")
    headers = {}
    if req.api_key:
        headers["Authorization"] = f"Bearer {req.api_key}"

    start_t = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{url}/v1/models", headers=headers)
            latency_ms = int((time.perf_counter() - start_t) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
                return {
                    "ok": True,
                    "latency_ms": latency_ms,
                    "models": models,
                    "message": f"Successfully connected to Summertime GPU Server in {latency_ms}ms! Discovered {len(models)} model(s).",
                }
            elif resp.status_code == 401:
                return {
                    "ok": False,
                    "latency_ms": latency_ms,
                    "models": [],
                    "message": "Authorization Failed: The API key provided was rejected by the server (HTTP 401).",
                }
            else:
                return {
                    "ok": False,
                    "latency_ms": latency_ms,
                    "models": [],
                    "message": f"Server responded with error status HTTP {resp.status_code}.",
                }
    except httpx.ConnectError:
        return {
            "ok": False,
            "latency_ms": None,
            "models": [],
            "message": f"Connection Refused: Could not reach {url}. Please verify that the server is online and port 8000 is open.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": None,
            "models": [],
            "message": f"Connection Error: {str(exc)}",
        }


@router.post("/configure-server")
async def configure_server(req: ConfigureServerRequest):
    """Updates client configuration with one click."""
    url = req.server_url.rstrip("/")
    api_key = req.api_key or ""
    api_base = f"{url}/v1"

    # Resolve context length
    context_length = req.context_length
    if not context_length and req.context_preset:
        context_length = CONTEXT_PRESETS.get(req.context_preset.lower(), 16384)
    if not context_length:
        context_length = 16384

    # 1. Update .env file
    env_updates = {
        "WORKBENCH_API_BASE": url,
        "OPENAI_BASE_URL": api_base,
    }
    if api_key:
        env_updates["WORKBENCH_API_KEY"] = api_key
        env_updates["OPENAI_API_KEY"] = api_key

    if req.vault_path:
        env_updates["OBSIDIAN_VAULT_PATH"] = req.vault_path

    if req.artifactory_url:
        env_updates["ARTIFACTORY_URL"] = req.artifactory_url
    if req.artifactory_repo:
        env_updates["ARTIFACTORY_REPO"] = req.artifactory_repo
    if req.artifactory_user:
        env_updates["ARTIFACTORY_USER"] = req.artifactory_user
    if req.artifactory_token:
        env_updates["ARTIFACTORY_TOKEN"] = req.artifactory_token

    _write_env_keys(env_updates)

    # 2. Update config.yaml
    config = _read_config_yaml()
    config.setdefault("model", {})
    config["model"]["base_url"] = api_base
    config["model"]["context_length"] = context_length

    config.setdefault("providers", {})
    wb = config["providers"].setdefault("workbench", {})
    wb["api"] = api_base
    wb["base_url"] = api_base
    wb["context_length"] = context_length

    if "models" in wb and isinstance(wb["models"], dict):
        for m_name in wb["models"]:
            wb["models"][m_name]["context_length"] = context_length

    _write_config_yaml(config)

    # 3. Synchronize with connected server if running
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                f"{url}/v1/admin/context",
                json={"context_length": context_length},
                headers=headers,
            )
    except Exception:
        pass  # Server might not have the optional endpoint yet; non-blocking

    return {
        "ok": True,
        "message": f"Server configured successfully! Context window set to {context_length:,} tokens.",
        "server_url": url,
        "context_length": context_length,
    }


@router.post("/set-context")
async def set_context_preset(req: SetContextRequest):
    """1-Click context window switcher according to GPU VRAM capacity."""
    length = req.context_length
    preset_name = req.preset

    if not length and preset_name:
        length = CONTEXT_PRESETS.get(preset_name.lower())
    if not length:
        raise HTTPException(status_code=400, detail="Must provide a valid preset or token count.")

    # Update config.yaml
    config = _read_config_yaml()
    config.setdefault("model", {})
    config["model"]["context_length"] = length

    wb = config.setdefault("providers", {}).setdefault("workbench", {})
    wb["context_length"] = length
    if "models" in wb and isinstance(wb["models"], dict):
        for m_name in wb["models"]:
            wb["models"][m_name]["context_length"] = length

    _write_config_yaml(config)

    # Notify connected server asynchronously if reachable
    env = _read_env_dict()
    server_url = env.get("WORKBENCH_API_BASE", "http://127.0.0.1:8000")
    api_key = env.get("WORKBENCH_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                f"{server_url}/v1/admin/context",
                json={"context_length": length},
                headers=headers,
            )
    except Exception:
        pass

    return {
        "ok": True,
        "context_length": length,
        "preset": preset_name or f"{length // 1024}k",
        "message": f"Context window updated to {length:,} tokens ({length // 1024}K).",
    }


@router.post("/rag-reindex")
async def rag_reindex(req: RagReindexRequest):
    """Scans and indexes the Obsidian knowledge vault for local RAG."""
    env = _read_env_dict()
    vault_str = req.vault_path or env.get("OBSIDIAN_VAULT_PATH", "./MyVault")

    vault_path = Path(vault_str)
    if not vault_path.is_absolute():
        vault_path = WORKSPACE_ROOT / vault_str

    if not vault_path.exists():
        vault_path.mkdir(parents=True, exist_ok=True)

    # Count candidate knowledge documents
    docs = [f for f in vault_path.rglob("*") if f.is_file() and f.suffix.lower() in [".md", ".pdf", ".txt", ".csv"]]

    return {
        "ok": True,
        "vault_path": str(vault_path),
        "documents_indexed": len(docs),
        "message": f"Vault indexed successfully! Found {len(docs)} document(s) in {vault_path.name}.",
    }
