"""Register every locally configured GGUF model with Workbench."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("indra_auto_configure", ROOT / "auto-configure-models.py")
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

key = dotenv_values(ROOT / ".env").get("WORKBENCH_API_KEY") or os.environ.get("WORKBENCH_API_KEY")
if not key:
    raise RuntimeError("WORKBENCH_API_KEY is missing; run setup_local_admin.py first")

with httpx.Client(
    base_url="http://127.0.0.1:8000",
    headers={"Authorization": f"Bearer {key}"},
    timeout=30,
) as client:
    existing = {item["id"] for item in client.get("/v1/models").raise_for_status().json()["data"]}
    for model in module.scan_models():
        model_id = model["alias"]
        if model_id in existing:
            print(f"Registered {model_id}: already present")
            continue
        payload = {
            "name": model_id,
            "source": {"type": "local_path", "path": model["path"]},
            "backend": "llamaswap",
            "type": "vlm" if model["is_vlm"] else "text",
            "task_tags": ["vision", "ocr"] if model["is_vlm"] else ["chat"],
            "pinned": model_id == "qwen3.5-4b",
        }
        response = client.post("/v1/models", json=payload)
        response.raise_for_status()
        print(f"Registered {model_id}: created")
