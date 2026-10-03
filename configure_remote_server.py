#!/usr/bin/env python3
"""
INDRA AI Workstation — Remote Server Configuration & Context Optimizer.

Allows client machines to dynamically connect to a remote Summertime AI Workbench
GPU compute node without hardcoding credentials, and one-click optimize context
window size according to GPU VRAM capacity.

Usage:
    python configure_remote_server.py --url http://192.168.1.100:8000 --key wb_live_...
    python configure_remote_server.py --set-context balanced
    python configure_remote_server.py --set-context 32k
    python configure_remote_server.py  (Interactive mode)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
ENV_PATH = ROOT_DIR / "SIH-26" / ".env"
CONFIG_YAML_PATH = ROOT_DIR / "SIH-26" / "config.yaml"

CONTEXT_PRESETS = {
    "eco": 4096,
    "4k": 4096,
    "balanced": 16384,
    "16k": 16384,
    "power": 32768,
    "32k": 32768,
    "ultra": 65536,
    "64k": 65536,
}

try:
    import httpx
except ImportError:
    print("[!] Installing httpx...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "httpx"], check=True)
    import httpx

try:
    import yaml
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml"], check=True)
    import yaml


def parse_args():
    parser = argparse.ArgumentParser(description="Pair INDRA Client with Remote GPU Server & Optimize Context")
    parser.add_argument("--url", help="Remote Server Base URL (e.g. http://192.168.1.100:8000)")
    parser.add_argument("--key", help="Dynamic Client API Key (wb_live_...)")
    parser.add_argument("--ctx", "--preset", dest="ctx", help="Context Window Preset: eco (4k), balanced (16k), power (32k), ultra (64k)")
    parser.add_argument("--set-context", dest="set_context_only", help="One-click switch context window preset (eco|balanced|power|ultra|<tokens>)")
    parser.add_argument("--vault", help="Obsidian Knowledge Vault directory path (defaults to ./MyVault)")
    parser.add_argument("--skip-test", action="store_true", help="Skip live inference verification")
    return parser.parse_args()


def resolve_tokens(preset_or_val: str | int | None) -> int:
    if not preset_or_val:
        return 16384
    s = str(preset_or_val).strip().lower()
    if s in CONTEXT_PRESETS:
        return CONTEXT_PRESETS[s]
    if s.endswith("k") and s[:-1].isdigit():
        return int(s[:-1]) * 1024
    if s.isdigit():
        return int(s)
    return 16384


def apply_context_length(tokens: int):
    """Updates config.yaml with the specified context window across all models."""
    if not CONFIG_YAML_PATH.exists():
        print(f"  [!] Warning: {CONFIG_YAML_PATH} not found.")
        return

    content = CONFIG_YAML_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(content) or {}

    data.setdefault("model", {})
    data["model"]["context_length"] = tokens

    wb = data.setdefault("providers", {}).setdefault("workbench", {})
    wb["context_length"] = tokens

    if "models" in wb and isinstance(wb["models"], dict):
        for m in wb["models"]:
            wb["models"][m]["context_length"] = tokens

    CONFIG_YAML_PATH.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print(f"  [OK] Context window set to {tokens:,} tokens ({tokens // 1024}K) in config.yaml")


def update_env_file(server_url: str, api_key: str, vault_path: str | None = None):
    """Updates or adds WORKBENCH_API_BASE, WORKBENCH_API_KEY, and OBSIDIAN_VAULT_PATH."""
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    new_keys = {
        "WORKBENCH_API_BASE": server_url,
        "WORKBENCH_API_KEY": f"'{api_key}'",
        "OPENAI_API_KEY": f"'{api_key}'",
        "OPENAI_BASE_URL": f"'{server_url}/v1'",
    }
    if vault_path:
        new_keys["OBSIDIAN_VAULT_PATH"] = vault_path

    updated = set()
    output_lines = []
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in new_keys:
                output_lines.append(f"{k}={new_keys[k]}")
                updated.add(k)
                continue
        output_lines.append(line)

    for k, v in new_keys.items():
        if k not in updated:
            output_lines.append(f"{k}={v}")

    ENV_PATH.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    print(f"  [OK] Updated environment file: {ENV_PATH.relative_to(ROOT_DIR)}")


def update_config_yaml(server_url: str, api_base: str, available_models: list[str], tokens: int = 16384):
    """Updates config.yaml with remote provider URL, dynamic models, and context length."""
    if not CONFIG_YAML_PATH.exists():
        print(f"  [!] Warning: {CONFIG_YAML_PATH} not found.")
        return

    content = CONFIG_YAML_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(content) or {}

    data.setdefault("model", {})
    data["model"]["base_url"] = api_base
    data["model"]["provider"] = "workbench"
    data["model"]["key_env"] = "WORKBENCH_API_KEY"
    data["model"]["context_length"] = tokens

    data.setdefault("providers", {})
    wb = data["providers"].setdefault("workbench", {})
    wb["api"] = api_base
    wb["base_url"] = api_base
    wb["key_env"] = "WORKBENCH_API_KEY"
    wb["transport"] = "chat_completions"
    wb["context_length"] = tokens

    # Ensure discovered models exist in models block
    models_block = wb.setdefault("models", {})
    for m in available_models:
        if m and m not in models_block:
            models_block[m] = {
                "context_length": tokens,
                "supports_vision": "vision" in m.lower() or "vl" in m.lower(),
            }
        elif m in models_block:
            models_block[m]["context_length"] = tokens

    CONFIG_YAML_PATH.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print(f"  [OK] Updated configuration: {CONFIG_YAML_PATH.relative_to(ROOT_DIR)} (Context: {tokens:,} tokens)")


def main():
    args = parse_args()

    # Standalone context switcher
    if args.set_context_only:
        tokens = resolve_tokens(args.set_context_only)
        print("\n" + "=" * 65)
        print("          INDRA ONE-CLICK CONTEXT WINDOW OPTIMIZER")
        print("=" * 65)
        apply_context_length(tokens)
        print("=" * 65 + "\n")
        return

    print("\n" + "=" * 65)
    print("      INDRA AI Workstation — Remote Server Pairing Utility")
    print("=" * 65)

    server_url = args.url
    api_key = args.key
    tokens = resolve_tokens(args.ctx)

    if not server_url:
        print("\nEnter Remote Summertime Server Base URL")
        print("Example: http://192.168.1.100:8000 or http://localhost:8000")
        server_url = input("Server URL: ").strip()

    if not api_key:
        print("\nEnter Client API Key (generated via 'workbench admin export-client' on server)")
        api_key = input("API Key: ").strip()

    server_url = server_url.rstrip("/")
    api_base = f"{server_url}/v1"

    print("\n[Step 1/3] Testing connectivity and discovering server models...")
    headers = {"Authorization": f"Bearer {api_key}"}
    client = httpx.Client(base_url=server_url, timeout=10.0)

    try:
        t0 = time.perf_counter()
        r = client.get("/v1/models", headers=headers)
        latency = (time.perf_counter() - t0) * 1000

        if r.status_code == 200:
            models_data = r.json().get("data", [])
            model_ids = [m.get("id") for m in models_data]
            print(f"  [PASS] Successfully connected to server ({latency:.1f}ms latency).")
            print(f"  Discovered {len(model_ids)} server model(s): {', '.join(model_ids[:5])}{'...' if len(model_ids)>5 else ''}")
        elif r.status_code == 401:
            print("  [FAIL] 401 Unauthorized: Invalid or revoked API key.")
            sys.exit(1)
        else:
            print(f"  [FAIL] Server returned HTTP {r.status_code}: {r.text}")
            sys.exit(1)
    except Exception as e:
        print(f"  [ERROR] Connection failed: {e}")
        sys.exit(1)

    # Step 2: Apply Client Configurations
    print("\n[Step 2/3] Writing client environment and routing configurations...")
    update_env_file(server_url, api_key, vault_path=args.vault)
    update_config_yaml(server_url, api_base, model_ids, tokens=tokens)

    # Step 3: End-to-End Chat Test
    if not args.skip_test:
        print("\n[Step 3/3] Performing live end-to-end inference verification...")
        test_payload = {
            "model": "indra-auto",
            "messages": [{"role": "user", "content": "Respond in 5 words: Confirm client connection successful."}],
            "max_tokens": 30,
            "temperature": 0.1,
        }
        try:
            t0 = time.perf_counter()
            resp = client.post("/v1/chat/completions", headers=headers, json=test_payload, timeout=30.0)
            latency = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                answer = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                print(f"  [PASS] Inference verified in {latency:.1f}ms!")
                print(f"  Server response: \"{answer}\"")
        except Exception as e:
            print(f"  [WARNING] Test inference turn timed out: {e}")

    print("\n" + "=" * 65)
    print("   CLIENT SUCCESSFULLY PAIRED WITH REMOTE GPU SERVER!")
    print(f"   Active Context Window: {tokens:,} tokens ({tokens // 1024}K)")
    print("=" * 65)
    print("Launch the INDRA dashboard with:")
    print("    indra dashboard")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
