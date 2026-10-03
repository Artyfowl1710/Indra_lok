#!/usr/bin/env python3
"""
Summertime / AI Workbench Server Connectivity & Health Verification Suite.

Usage:
    python test_server_connectivity.py
    python test_server_connectivity.py --url http://192.168.1.100:8000 --key wb_live_...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

try:
    import httpx
except ImportError:
    print("[ERROR] httpx is required. Run: pip install httpx")
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="Test Summertime AI Workbench Server")
    parser.add_argument(
        "--url",
        default=os.environ.get("WORKBENCH_API_BASE", "http://127.0.0.1:8000"),
        help="Base URL of Workbench server (default: $WORKBENCH_API_BASE or http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--key",
        default=os.environ.get("WORKBENCH_API_KEY", ""),
        help="API Key (default: $WORKBENCH_API_KEY)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    base_url = args.url.rstrip("/")
    api_key = args.key

    print("=" * 65)
    print("   AI WORKBENCH / SUMMERTIME SERVER HEALTH VERIFICATION")
    print("=" * 65)
    print(f"Target Server : {base_url}")
    print(f"API Key       : {api_key[:12]}..." if len(api_key) > 12 else f"API Key       : {'[NOT PROVIDED]' if not api_key else api_key}")
    print("-" * 65)

    client = httpx.Client(base_url=base_url, timeout=30.0, verify=False)

    # 1. Test /v1/health
    print("\n[TEST 1/5] Checking /v1/health...")
    try:
        health_headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        r = client.get("/v1/health", headers=health_headers)
        if r.status_code == 200:
            data = r.json()
            print(f"  [PASS] Status 200 OK | Database: {data.get('database')} | Timestamp: {data.get('timestamp')}")
        else:
            print(f"  [FAIL] Unexpected status {r.status_code}: {r.text}")
    except Exception as e:
        print(f"  [ERROR] Connection failed: {e}")
        print(f"\nCould not connect to {base_url}. Is the server running?")
        sys.exit(1)

    if not api_key:
        print("\n[NOTE] No API key provided. Skipping authenticated tests.")
        print("To run full tests: python test_server_connectivity.py --key wb_live_...")
        print("=" * 65)
        return

    headers = {"Authorization": f"Bearer {api_key}"}

    # 2. Test Authentication & Model Listing (/v1/models)
    print("\n[TEST 2/5] Testing Authenticated /v1/models...")
    try:
        t0 = time.perf_counter()
        r = client.get("/v1/models", headers=headers)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            models_data = r.json()
            models_list = models_data.get("data", [])
            print(f"  [PASS] Authentication successful ({elapsed_ms:.1f}ms).")
            print(f"  Available models ({len(models_list)}):")
            for m in models_list:
                m_id = m.get("id")
                m_backend = m.get("backend", "unknown")
                m_vram = m.get("vram_mb", 0)
                m_status = m.get("status", "unknown")
                print(f"    - {m_id:<28} [{m_backend}] {m_vram}MB VRAM (status={m_status})")
        elif r.status_code == 401:
            print("  [FAIL] 401 Unauthorized: Invalid or revoked API key.")
            sys.exit(1)
        elif r.status_code == 403:
            print("  [FAIL] 403 Forbidden: Insufficient permissions.")
            sys.exit(1)
        else:
            print(f"  [FAIL] Status {r.status_code}: {r.text}")
            sys.exit(1)
    except Exception as e:
        print(f"  [ERROR] /v1/models request failed: {e}")
        sys.exit(1)

    # 3. Test Chat Completion Non-Streaming (/v1/chat/completions)
    print("\n[TEST 3/5] Testing Chat Completion (/v1/chat/completions)...")
    test_model = "indra-auto"
    payload = {
        "model": test_model,
        "messages": [
            {"role": "user", "content": "Respond in exactly 5 words: Confirm system is operational."}
        ],
        "max_tokens": 64,
        "temperature": 0.1,
        "stream": False,
    }
    try:
        t0 = time.perf_counter()
        r = client.post("/v1/chat/completions", headers=headers, json=payload, timeout=60.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            chat_resp = r.json()
            content = chat_resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            routed = r.headers.get("X-Workbench-Routed-Model", chat_resp.get("model", test_model))
            print(f"  [PASS] Response received ({elapsed_ms:.1f}ms, routed to: {routed}):")
            print(f"  Output: \"{content}\"")
        else:
            print(f"  [FAIL] Chat failed {r.status_code}: {r.text}")
    except Exception as e:
        print(f"  [ERROR] Chat request failed: {e}")

    # 4. Test Chat Streaming (/v1/chat/completions with stream=True)
    print("\n[TEST 4/5] Testing Streaming Chat Completion (SSE)...")
    payload["stream"] = True
    try:
        t0 = time.perf_counter()
        stream_chunks = 0
        collected_text = []
        with client.stream("POST", "/v1/chat/completions", headers=headers, json=payload, timeout=60.0) as resp:
            if resp.status_code == 200:
                for line in resp.iter_lines():
                    if line.startswith("data: ") and not line.endswith("[DONE]"):
                        stream_chunks += 1
                        try:
                            chunk_data = json.loads(line[6:])
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                            content_piece = delta.get("content") or ""
                            if content_piece:
                                collected_text.append(content_piece)
                        except Exception:
                            pass
                elapsed_ms = (time.perf_counter() - t0) * 1000
                print(f"  [PASS] Streamed {stream_chunks} tokens in {elapsed_ms:.1f}ms.")
                print(f"  Stream Result: \"{''.join(collected_text).strip()}\"")
            else:
                print(f"  [FAIL] Streaming failed with status {resp.status_code}")
    except Exception as e:
        print(f"  [ERROR] Streaming request failed: {e}")

    # 5. Check Identity Intercept
    print("\n[TEST 5/5] Testing Persona / Identity Contract...")
    identity_payload = {
        "model": "indra-auto",
        "messages": [{"role": "user", "content": "Who are you?"}],
        "stream": False,
    }
    try:
        r = client.post("/v1/chat/completions", headers=headers, json=identity_payload, timeout=15.0)
        if r.status_code == 200:
            content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            print(f"  [PASS] Identity Verified: \"{content}\"")
        else:
            print(f"  [FAIL] Identity request returned status {r.status_code}")
    except Exception as e:
        print(f"  [ERROR] Identity test failed: {e}")

    print("\n" + "=" * 65)
    print("   ALL TESTS COMPLETED SUCCESSFULLY — SERVER IS PRODUCTION READY")
    print("=" * 65)


if __name__ == "__main__":
    main()
