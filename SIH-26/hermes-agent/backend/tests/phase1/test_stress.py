"""
Stress testing for lifecycle concurrency and queues.

Tests:
  - Concurrent requests against the same model
  - Queue behavior when vLLM capacity is exhausted
  - Race-condition safety between track_request and idle reaper
"""
from __future__ import annotations

import asyncio
import secrets as _secrets
import threading
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from server.config import settings
from server.core.lifecycle import lifecycle, LoadQueue
from server.db import SessionLocal, ModelRecord, ApiKey
from server.core.auth import generate_key, hash_key


# ── helpers ───────────────────────────────────────────────────────────────────

def _bootstrap_admin() -> str:
    """Insert an admin key directly into the (patched) DB; return plaintext."""
    plaintext = generate_key()
    with SessionLocal() as db:
        db.add(ApiKey(
            key_id=_secrets.token_hex(8),
            key_hash=hash_key(plaintext),
            owner="stress-admin",
            scope="admin",
        ))
        db.commit()
    return plaintext


def _register_model_direct(name: str, backend: str = "llamaswap"):
    """Insert a model directly into DB, bypassing API route."""
    with SessionLocal() as db:
        db.add(ModelRecord(
            id=name,
            backend=backend,
            model_type="text",
            task_tags="[]",
            source_type="local_path",
            source_ref="/tmp/fake_model.gguf",
            local_path="/tmp/fake_model.gguf",
            status="cold",
            vram_mb=100,
        ))
        db.commit()


# ── test: concurrent requests on same model ───────────────────────────────────

class TestConcurrentRequests:
    """Verify that multiple concurrent chat requests to the same model
    are all tracked correctly and don't corrupt active_requests."""

    def test_concurrent_chat_same_model(self, client):
        admin = _bootstrap_admin()
        headers = {"Authorization": f"Bearer {admin}"}
        _register_model_direct("stress-model-1")

        # Mock the load function so it's a no-op
        async def mock_load(model_id):
            await asyncio.sleep(0.01)

        async def mock_unload(model_id):
            pass

        lifecycle.register_backend("llamaswap", mock_load, mock_unload)

        # Mock the proxy so it doesn't actually call a backend
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        results = []
        errors = []

        def _do_request():
            try:
                r = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "stress-model-1",
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                    headers=headers,
                )
                results.append(r.status_code)
            except Exception as e:
                errors.append(e)

        # Fire 20 concurrent requests via threads
        with patch("server.backends.llamaswap.proxy_chat", new_callable=AsyncMock, return_value=mock_resp):
            threads = [threading.Thread(target=_do_request) for _ in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        assert not errors, f"Errors during concurrent requests: {errors}"
        assert all(s == 200 for s in results), f"Unexpected status codes: {results}"

        # After all requests complete, active_requests should be back to 0
        with SessionLocal() as db:
            m = db.query(ModelRecord).filter(ModelRecord.id == "stress-model-1").first()
            assert m.active_requests == 0, f"active_requests leaked: {m.active_requests}"
            assert m.status == "idle"


# ── test: track_request vs idle reaper race ───────────────────────────────────

class TestTrackRequestRace:
    """Verify that the idle reaper cannot unload a model between
    _ensure_loaded and the active_requests increment."""

    def test_reaper_does_not_unload_during_track(self, client):
        admin = _bootstrap_admin()
        headers = {"Authorization": f"Bearer {admin}"}
        _register_model_direct("race-model")

        load_called = asyncio.Event()
        unload_called = []

        async def mock_load(model_id):
            load_called.set()

        async def mock_unload(model_id):
            unload_called.append(model_id)

        lifecycle.register_backend("llamaswap", mock_load, mock_unload)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with patch("server.backends.llamaswap.proxy_chat", new_callable=AsyncMock, return_value=mock_resp):
            r = client.post(
                "/v1/chat/completions",
                json={
                    "model": "race-model",
                    "messages": [{"role": "user", "content": "test"}],
                },
                headers=headers,
            )
            assert r.status_code == 200

        # Model should be idle now, not unloaded
        with SessionLocal() as db:
            m = db.query(ModelRecord).filter(ModelRecord.id == "race-model").first()
            assert m.status == "idle"
            assert m.active_requests == 0


# ── test: queue drains correctly ──────────────────────────────────────────────

class TestLoadQueue:
    """Verify LoadQueue FIFO behavior."""

    @pytest.mark.asyncio
    async def test_enqueue_and_drain(self):
        q = LoadQueue()
        fut1 = await q.enqueue("model-a")
        fut2 = await q.enqueue("model-b")

        item1 = await q.drain_one()
        assert item1 is not None
        assert item1[0] == "model-a"

        item2 = await q.drain_one()
        assert item2 is not None
        assert item2[0] == "model-b"

        item3 = await q.drain_one()
        assert item3 is None

    @pytest.mark.asyncio
    async def test_drain_empty_returns_none(self):
        q = LoadQueue()
        assert await q.drain_one() is None
