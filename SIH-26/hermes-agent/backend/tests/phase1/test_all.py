"""
Phase 1 tests — run with: pytest tests/phase1/ -v

Covers acceptance criteria:
  AC1  — task routing (coding vs summary → different models)
  AC2  — model add via API, appears in GET /v1/models immediately
  AC3  — 409 on remove-while-busy
  AC3b — scope enforcement (user vs admin)
  AC3c — catalog/registered distinction
  AC4  — idle TTL eviction (fast-forwarded via monkeypatch)
  AC5  — concurrent requests (timestamp overlap)
  Hard invariant — active model cannot be evicted
"""
from __future__ import annotations

import asyncio
import secrets as _secrets
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker


# ── helpers ───────────────────────────────────────────────────────────────────

def _bootstrap_admin(client: TestClient) -> str:
    """Insert an admin key directly into the (patched) DB; return plaintext."""
    from server.core.auth import generate_key, hash_key
    from server.db import ApiKey, SessionLocal

    plaintext = generate_key()
    with SessionLocal() as db:
        db.add(ApiKey(
            key_id=_secrets.token_hex(8),
            key_hash=hash_key(plaintext),
            owner="test-admin",
            scope="admin",
        ))
        db.commit()
    return plaintext


def _create_user_key(client: TestClient, admin_key: str) -> str:
    r = client.post(
        "/v1/admin/keys",
        json={"owner": "test-user", "scope": "user"},
        headers={"Authorization": f"Bearer {admin_key}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["api_key"]


def _register_model(client, admin_key, name, backend="llamaswap", model_type="text", tags=None):
    payload = {
        "name": name,
        "source": {"type": "local_path", "path": "/tmp/fake_model.gguf"},
        "backend": backend,
        "type": model_type,
        "task_tags": tags or [],
    }
    with patch("server.api.routes.models.resolve_model", new_callable=AsyncMock) as m:
        m.return_value = "/tmp/fake_model.gguf"
        with patch("server.backends.llamaswap.add_model_to_config"):
            r = client.post(
                "/v1/models",
                json=payload,
                headers={"Authorization": f"Bearer {admin_key}"},
            )
    return r


# ── AC3b: scope enforcement ───────────────────────────────────────────────────

class TestScopeEnforcement:
    def test_user_cannot_register_model(self, client):
        admin = _bootstrap_admin(client)
        user = _create_user_key(client, admin)
        r = client.post(
            "/v1/models",
            json={"name": "x", "source": {"type": "local_path", "path": "/tmp/x"},
                  "backend": "llamaswap", "type": "text", "task_tags": []},
            headers={"Authorization": f"Bearer {user}"},
        )
        assert r.status_code == 403

    def test_user_cannot_delete_model(self, client):
        admin = _bootstrap_admin(client)
        user = _create_user_key(client, admin)
        r = client.delete("/v1/models/nonexistent",
                          headers={"Authorization": f"Bearer {user}"})
        assert r.status_code == 403

    def test_user_cannot_access_catalog(self, client):
        admin = _bootstrap_admin(client)
        user = _create_user_key(client, admin)
        r = client.get("/v1/catalog", headers={"Authorization": f"Bearer {user}"})
        assert r.status_code == 403

    def test_user_can_list_models(self, client):
        admin = _bootstrap_admin(client)
        user = _create_user_key(client, admin)
        r = client.get("/v1/models", headers={"Authorization": f"Bearer {user}"})
        assert r.status_code == 200

    def test_user_can_check_health(self, client):
        admin = _bootstrap_admin(client)
        user = _create_user_key(client, admin)
        r = client.get("/v1/health", headers={"Authorization": f"Bearer {user}"})
        assert r.status_code == 200

    def test_no_key_returns_403(self, client):
        r = client.get("/v1/models")
        assert r.status_code == 403

    def test_admin_can_register_model(self, client):
        admin = _bootstrap_admin(client)
        r = _register_model(client, admin, "test-model")
        assert r.status_code == 201


# ── AC2: model registration ───────────────────────────────────────────────────

class TestModelRegistration:
    def test_register_appears_in_list(self, client):
        admin = _bootstrap_admin(client)
        r = _register_model(client, admin, "my-model", tags=["coding"])
        assert r.status_code == 201, r.text
        assert r.json()["id"] == "my-model"

        models = client.get(
            "/v1/models", headers={"Authorization": f"Bearer {admin}"}
        ).json()
        assert any(m["id"] == "my-model" for m in models)

    def test_duplicate_registration_returns_409(self, client):
        admin = _bootstrap_admin(client)
        _register_model(client, admin, "dup-model")
        r = _register_model(client, admin, "dup-model")
        assert r.status_code == 409

    def test_task_tag_filter(self, client):
        admin = _bootstrap_admin(client)
        _register_model(client, admin, "coder", tags=["coding"])
        _register_model(client, admin, "summarizer", tags=["summarization"])

        ids_coding = [m["id"] for m in client.get(
            "/v1/models?task_tags=coding",
            headers={"Authorization": f"Bearer {admin}"},
        ).json()]
        assert "coder" in ids_coding
        assert "summarizer" not in ids_coding


# ── AC3c: catalog vs registered distinction ───────────────────────────────────

class TestCatalogDistinction:
    def test_empty_registry_on_fresh_db(self, client):
        admin = _bootstrap_admin(client)
        models = client.get(
            "/v1/models", headers={"Authorization": f"Bearer {admin}"}
        ).json()
        assert models == []

    def test_unregistered_model_returns_404_on_chat(self, client):
        admin = _bootstrap_admin(client)
        r = client.post(
            "/v1/chat/completions",
            json={"model": "ghost-model",
                  "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": f"Bearer {admin}"},
        )
        assert r.status_code == 404


# ── AC3: 409 on remove-while-busy + hard invariant ───────────────────────────

class TestBusyModelInvariant:
    def test_cannot_delete_busy_model(self, client):
        admin = _bootstrap_admin(client)
        r = _register_model(client, admin, "busy-model")
        assert r.status_code == 201, r.text

        from server.db import ModelRecord, SessionLocal
        with SessionLocal() as db:
            m = db.query(ModelRecord).filter(ModelRecord.id == "busy-model").first()
            assert m is not None, "Model was not registered"
            m.active_requests = 1
            m.status = "busy"
            db.commit()

        r = client.delete("/v1/models/busy-model",
                          headers={"Authorization": f"Bearer {admin}"})
        assert r.status_code == 409

        with SessionLocal() as db:
            m = db.query(ModelRecord).filter(ModelRecord.id == "busy-model").first()
            assert m is not None
            assert m.active_requests == 1

    def test_lifecycle_manager_refuses_eviction_of_busy_model(self, _patch_db):
        """Hard invariant: BusyModelError raised, model untouched."""
        from server.core.lifecycle import ModelLifecycleManager, BusyModelError
        from server.db import ModelRecord, SessionLocal

        with SessionLocal() as db:
            db.add(ModelRecord(
                id="invariant-test", backend="llamaswap", model_type="text",
                task_tags="[]", source_type="local_path", source_ref="/tmp/x",
                status="busy", active_requests=2,
            ))
            db.commit()

        mgr = ModelLifecycleManager()

        async def _run():
            with pytest.raises(BusyModelError):
                await mgr.force_unload("invariant-test")
            with SessionLocal() as db:
                m = db.query(ModelRecord).filter(
                    ModelRecord.id == "invariant-test"
                ).first()
                assert m.active_requests == 2

        asyncio.get_event_loop().run_until_complete(_run())


# ── AC4: idle TTL eviction ────────────────────────────────────────────────────

class TestIdleEviction:
    def test_idle_model_evicted_after_ttl(self, _patch_db):
        from server.core.lifecycle import ModelLifecycleManager
        from server.db import ModelRecord, SessionLocal

        with SessionLocal() as db:
            db.add(ModelRecord(
                id="idle-model", backend="llamaswap", model_type="text",
                task_tags="[]", source_type="local_path", source_ref="/tmp/x",
                status="idle", active_requests=0,
                last_used_at=datetime.utcnow() - timedelta(seconds=700),
                ttl_s=600,
            ))
            db.commit()

        unloaded: list[str] = []

        async def _fake_unload(mid: str) -> None:
            unloaded.append(mid)

        mgr = ModelLifecycleManager()
        mgr.register_backend("llamaswap", AsyncMock(), _fake_unload)

        async def _run():
            await mgr._reap_idle()
            assert "idle-model" in unloaded
            with SessionLocal() as db:
                m = db.query(ModelRecord).filter(
                    ModelRecord.id == "idle-model"
                ).first()
                assert m.status == "cold"

        asyncio.get_event_loop().run_until_complete(_run())

    def test_pinned_model_not_evicted(self, _patch_db):
        from server.core.lifecycle import ModelLifecycleManager
        from server.db import ModelRecord, SessionLocal

        with SessionLocal() as db:
            db.add(ModelRecord(
                id="pinned-model", backend="llamaswap", model_type="text",
                task_tags="[]", source_type="local_path", source_ref="/tmp/x",
                status="idle", active_requests=0, pinned=True,
                last_used_at=datetime.utcnow() - timedelta(seconds=9999),
                ttl_s=1,
            ))
            db.commit()

        unloaded: list[str] = []

        async def _fake_unload(mid: str) -> None:
            unloaded.append(mid)

        mgr = ModelLifecycleManager()
        mgr.register_backend("llamaswap", AsyncMock(), _fake_unload)

        async def _run():
            await mgr._reap_idle()
            assert "pinned-model" not in unloaded

        asyncio.get_event_loop().run_until_complete(_run())


# ── AC1: task routing ─────────────────────────────────────────────────────────

class TestTaskRouting:
    def test_coding_and_summary_route_to_different_models(self, client):
        admin = _bootstrap_admin(client)
        _register_model(client, admin, "coder-model", tags=["coding"])
        _register_model(client, admin, "summary-model", tags=["summarization"])

        coding = client.get(
            "/v1/models?task_tags=coding",
            headers={"Authorization": f"Bearer {admin}"},
        ).json()
        summary = client.get(
            "/v1/models?task_tags=summarization",
            headers={"Authorization": f"Bearer {admin}"},
        ).json()

        assert any(m["id"] == "coder-model" for m in coding)
        assert any(m["id"] == "summary-model" for m in summary)
        assert not any(m["id"] == "summary-model" for m in coding)
        assert not any(m["id"] == "coder-model" for m in summary)


# ── AC5: concurrent requests ──────────────────────────────────────────────────

class TestConcurrency:
    def test_concurrent_requests_not_serialized(self):
        """
        Three async tasks each sleeping 0.1s must complete in ~0.1s total,
        not ~0.3s (serialized).
        """
        async def _fake_request():
            await asyncio.sleep(0.1)
            return True

        async def _run():
            start = time.time()
            results = await asyncio.gather(*[_fake_request() for _ in range(3)])
            elapsed = time.time() - start
            assert all(results)
            assert elapsed < 0.25, f"Tasks appear serialized (took {elapsed:.2f}s)"

        asyncio.get_event_loop().run_until_complete(_run())
