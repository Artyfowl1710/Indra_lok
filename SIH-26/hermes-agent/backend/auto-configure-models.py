#!/usr/bin/env python3
"""
Auto-configure llama-swap.yaml from whatever GGUF models exist in backend/models/.

Run this script whenever you add or remove models:
    python auto-configure-models.py

It scans the models/ directory, identifies model types, and generates
config/llama-swap.yaml with correct paths and tuned parameters for 6GB VRAM.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Resolve paths relative to this script (which lives in backend/)
BACKEND_ROOT = Path(__file__).resolve().parent
MODELS_DIR = BACKEND_ROOT / "models"
def resolve_executable(name: str) -> Path:
    """Resolve bundled Windows executables with or without an .exe suffix."""
    bin_dir = BACKEND_ROOT / "bin"
    candidates = (bin_dir / f"{name}.exe", bin_dir / name)
    return next((path for path in candidates if path.is_file()), candidates[0])


LLAMA_SERVER = resolve_executable("llama-server")
CONFIG_OUT = BACKEND_ROOT / "config" / "llama-swap.yaml"

# Stop command template (PowerShell on Windows, kill on Linux/macOS)
if sys.platform == "win32":
    CMD_STOP = (
        'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe '
        '-NoProfile -Command "Stop-Process -Id ${PID} -Force -ErrorAction SilentlyContinue"'
    )
else:
    CMD_STOP = "kill -9 ${PID} 2>/dev/null || true"

# ── Model identification patterns ────────────────────────────────────────────

# Patterns that identify vision/VLM models (need --mmproj)
VLM_PATTERNS = re.compile(r"(vl|vlm|vision|ocr|qwen2-vl)", re.IGNORECASE)
# Patterns that identify multimodal projector files
MMPROJ_PATTERN = re.compile(r"mmproj", re.IGNORECASE)

# Known model profiles: maps a filename substring to tuned parameters
# Format: (alias, ctx_size, batch_size, ubatch_size, predict, extra_flags)
MODEL_PROFILES: dict[str, dict] = {
    "qwen3.5-4b":       {"alias": "qwen3.5-4b",              "ctx": 65536, "batch": 512, "ubatch": 256, "predict": 4096, "layers": 99, "extra": "--reasoning-budget 0 --reasoning off"},
    "qwen_qwen3.5-4b":  {"alias": "qwen3.5-4b",              "ctx": 65536, "batch": 512, "ubatch": 256, "predict": 4096, "layers": 99, "extra": "--reasoning-budget 0 --reasoning off"},
    "gemma-2-2b":        {"alias": "gemma-2-2b-it",           "ctx": 8192,  "batch": 512, "ubatch": 256, "predict": 2048, "layers": 99, "extra": "--reasoning off"},
    "hermes-3-llama":    {"alias": "hermes-3-llama-8b",       "ctx": 32768, "batch": 256, "ubatch": 128, "predict": 4096, "layers": 99, "extra": "--reasoning off"},
    "qwen2-vl-ocr":      {"alias": "qwen2-vl-ocr-2b-instruct","ctx": 16384, "batch": 128, "ubatch": 64,  "predict": 512,  "layers": 99, "extra": "--reasoning off"},
    "phi-4-mini":        {"alias": "phi-4-mini-instruct",     "ctx": 16384, "batch": 256, "ubatch": 128, "predict": 256,  "layers": 99, "extra": "--reasoning off"},
}

# Default profile for unknown models
DEFAULT_PROFILE = {"ctx": 8192, "batch": 128, "ubatch": 64, "predict": 1024, "layers": 99, "extra": "--reasoning off"}


def find_profile(filename: str) -> dict:
    """Match a GGUF filename to a known model profile."""
    name_lower = filename.lower()
    for pattern, profile in MODEL_PROFILES.items():
        if pattern.lower() in name_lower:
            return profile
    return DEFAULT_PROFILE.copy()


def derive_alias(filename: str) -> str:
    """Create a reasonable alias from a GGUF filename."""
    # Remove extension and quantization suffixes
    name = re.sub(r"[-_.]Q\d+_K.*\.gguf$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"\.gguf$", "", name, flags=re.IGNORECASE)
    # Normalize separators
    name = name.replace("_", "-").replace(" ", "-").lower()
    # Remove duplicate dashes
    name = re.sub(r"-+", "-", name).strip("-")
    return name


def scan_models() -> list[dict]:
    """Scan models/ directory and return model configurations."""
    if not MODELS_DIR.exists():
        print(f"[ERROR] Models directory not found: {MODELS_DIR}")
        sys.exit(1)

    gguf_files = sorted(MODELS_DIR.glob("*.gguf"))
    mmproj_files = [f for f in gguf_files if MMPROJ_PATTERN.search(f.name)]
    model_files = [f for f in gguf_files if not MMPROJ_PATTERN.search(f.name)]

    if not model_files:
        print("[WARN] No .gguf model files found in models/")
        return []

    models = []
    seen_aliases: set[str] = set()
    for model_path in model_files:
        profile = find_profile(model_path.name)
        alias = profile.get("alias") or derive_alias(model_path.name)

        # Skip duplicate aliases (e.g. hardlinked model files that map to the
        # same profile). llama-swap's strict YAML parser rejects duplicate keys.
        if alias in seen_aliases:
            continue
        seen_aliases.add(alias)

        is_vlm = bool(VLM_PATTERNS.search(model_path.name))

        # Find matching mmproj for VLM models
        mmproj_path = None
        if is_vlm and mmproj_files:
            # Try to match by model name similarity
            model_stem = model_path.stem.lower()
            for mp in mmproj_files:
                mmproj_path = mp
                break  # Use first available mmproj

        entry = {
            "alias": alias,
            "path": str(model_path).replace("\\", "/"),
            "is_vlm": is_vlm,
            "mmproj": str(mmproj_path).replace("\\", "/") if mmproj_path else None,
            "ctx": profile.get("ctx", DEFAULT_PROFILE["ctx"]),
            "batch": profile.get("batch", DEFAULT_PROFILE["batch"]),
            "ubatch": profile.get("ubatch", DEFAULT_PROFILE["ubatch"]),
            "predict": profile.get("predict", DEFAULT_PROFILE["predict"]),
            "layers": profile.get("layers", DEFAULT_PROFILE["layers"]),
            "extra": profile.get("extra", DEFAULT_PROFILE["extra"]),
        }
        models.append(entry)

    return models


def generate_yaml(models: list[dict]) -> str:
    """Generate llama-swap.yaml content."""
    llama_server = str(LLAMA_SERVER).replace("\\", "/")

    lines = ["healthCheckTimeout: 180", "models:"]

    for m in models:
        lines.append(f"  {m['alias']}:")
        lines.append(f"    cmdStop: '{CMD_STOP}'")

        cmd_parts = [
            f'"{llama_server}"',
            "--host 127.0.0.1 --port ${PORT}",
            f'--model "{m["path"]}"',
            f'--alias {m["alias"]}',
            f'--n-gpu-layers {m["layers"]} --ctx-size {m["ctx"]} --parallel 1',
            f'--batch-size {m["batch"]} --ubatch-size {m["ubatch"]} --threads 8',
            "--flash-attn on --cache-type-k q4_0 --cache-type-v q4_0",
        ]

        if m["is_vlm"] and m["mmproj"]:
            cmd_parts.append(f'--mmproj "{m["mmproj"]}" --mmproj-device none')

        cmd_parts.append("--jinja")
        if m["extra"]:
            cmd_parts.append(m["extra"])
        cmd_parts.append(f'--predict {m["predict"]}')

        cmd_str = " ".join(cmd_parts)
        lines.append(f"    cmd: >-")
        lines.append(f"      {cmd_str}")
        lines.append(f"    ttl: 300")

    return "\n".join(lines) + "\n"


def main():
    print(f"[auto-configure] Scanning: {MODELS_DIR}")
    if not LLAMA_SERVER.is_file():
        print(f"[ERROR] llama-server is missing: {LLAMA_SERVER}")
        print("[ERROR] Run install-indra.ps1 before starting Indra.")
        sys.exit(1)
    models = scan_models()

    if not models:
        print("[auto-configure] No models found. Exiting.")
        return

    print(f"[auto-configure] Found {len(models)} model(s):")
    for m in models:
        vlm_tag = " [VLM]" if m["is_vlm"] else ""
        mmproj_tag = f" (mmproj: {Path(m['mmproj']).name})" if m["mmproj"] else ""
        print(f"  - {m['alias']}: {Path(m['path']).name}{vlm_tag}{mmproj_tag}")

    yaml_content = generate_yaml(models)

    CONFIG_OUT.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_OUT.write_text(yaml_content, encoding="utf-8")
    print(f"[auto-configure] Written: {CONFIG_OUT}")
    print("[auto-configure] Done. llama-swap will hot-reload if --watch-config is enabled.")


if __name__ == "__main__":
    main()
