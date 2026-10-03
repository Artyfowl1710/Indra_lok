#!/usr/bin/env python3
"""
INDRA AI Workstation — Remote Server Configuration & Pairing Utility.

Allows client machines to dynamically connect to a remote Summertime AI Workbench
GPU compute node without hardcoding credentials or manually editing YAML files.

Usage:
    python configure_remote_server.py --url http://192.168.1.100:8000 --key wb_live_...
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
    parser = argparse.ArgumentParser(description="Pair INDRA Client with Remote GPU Server")
    parser.add_argument("--url", help="Remote Server Base URL (e.g. http://192.168.1.100:8000)")
    parser.add_argument("--key", help="Dynamic Client API Key (wb_live_...)")
    parser.add_argument("--skip-test", action="store_true", help="Skip live inference verification")
    return parser.parse_args()


def update_env_file(server_url: str, api_key: str):
    """Updates or adds WORKBENCH_API_BASE and WORKBENCH_API_KEY in SIH-26/.env."""
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    new_keys = {
        "WORKBENCH_API_BASE": server_url,
        "WORKBENCH_API_KEY": f"'{api_key}'",
        "OPENAI_API_KEY": f"'{api_key}'",
        "OPENAI_BASE_URL": f"'{server_url}/v1'",
    }

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


def update_config_yaml(server_url: str, api_base: str, available_models: list[str]):
    """Updates config.yaml with remote provider URL and dynamic models."""
    if not CONFIG_YAML_PATH.exists():
        print(f"  [!] Warning: {CONFIG_YAML_PATH} not found.")
        return

    content = CONFIG_YAML_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(content) or {}

    # Update top-level model block
    data.setdefault("model", {})
    data["model"]["base_url"] = api_base
    data["model"]["provider"] = "workbench"
    data["model"]["key_env"] = "WORKBENCH_API_KEY"

    # Update providers.workbench block
    data.setdefault("providers", {})
    wb = data["providers"].setdefault("workbench", {})
    wb["api"] = api_base
    wb["base_url"] = api_base
    wb["key_env"] = "WORKBENCH_API_KEY"
    wb["transport"] = "chat_completions"

    # Update models dictionary if models were discovered
    if available_models:
        models_dict = wb.setdefault("models", {})
        for m in available_models:
            models_dict.setdefault(m, {"context_length": 65536})

    CONFIG_YAML_PATH.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print(f"  [OK] Updated client model configuration: {CONFIG_YAML_PATH.relative_to(ROOT_DIR)}")


def main():
    args = parse_args()

    print("=" * 65)
    print("   INDRA CLIENT — DYNAMIC SERVER PAIRING & CONFIGURATION")
    print("=" * 65)

    server_url = args.url
    api_key = args.key

    # Interactive prompt if arguments omitted
    if not server_url:
        print("\nEnter the remote Summertime / AI Workbench server address.")
        server_url = input("Server Base URL [http://127.0.0.1:8000]: ").strip() or "http://127.0.0.1:8000"

    server_url = server_url.rstrip("/")

    if not api_key:
        api_key = input("Dynamic API Key (wb_live_...): ").strip()
        if not api_key:
            print("[ERROR] API Key is required to pair with the server.")
            sys.exit(1)

    api_base = f"{server_url}/v1"

    print(f"\nTargeting Server : {server_url}")
    print(f"API Base URL     : {api_base}")
    print(f"Client API Key   : {api_key[:12]}...")

    # Step 1: Health & Connectivity Check
    print("\n[Step 1/3] Verifying server connectivity and authentication...")
    client = httpx.Client(base_url=server_url, timeout=15.0, verify=False)
    headers = {"Authorization": f"Bearer {api_key}"}

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
            print("  Please obtain a valid key from your server administrator.")
            sys.exit(1)
        elif r.status_code == 403:
            print("  [FAIL] 403 Forbidden: Insufficient permissions for this key.")
            sys.exit(1)
        else:
            print(f"  [FAIL] Server returned HTTP {r.status_code}: {r.text}")
            sys.exit(1)
    except Exception as e:
        print(f"  [ERROR] Connection failed: {e}")
        print(f"  Could not reach {server_url}. Please verify IP/domain and firewall settings.")
        sys.exit(1)

    # Step 2: Apply Client Configurations
    print("\n[Step 2/3] Writing client environment and routing configurations...")
    update_env_file(server_url, api_key)
    update_config_yaml(server_url, api_base, model_ids)

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
            else:
                print(f"  [WARNING] Inference returned HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"  [WARNING] Test inference turn timed out or failed: {e}")

    print("\n" + "=" * 65)
    print("   CLIENT SUCCESSFULLY PAIRED WITH REMOTE GPU SERVER!")
    print("=" * 65)
    print("You can now launch the INDRA dashboard with:")
    print("    indra dashboard")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
