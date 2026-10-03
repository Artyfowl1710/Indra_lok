"""
Shared test fixtures for phase1 tests.
"""
from __future__ import annotations

import asyncio
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ── in-memory DB fixture ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _patch_db(monkeypatch, tmp_path):
    """
    Each test gets its own SQLite file in a temp directory.
    File-based SQLite is visible to all threads without StaticPool tricks.
    """
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False, "timeout": 15},
        pool_size=30,
        max_overflow=30,
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    import server.db.models
    import server.db
    import server.core.lifecycle  # noqa

    lc_mod  = sys.modules["server.core.lifecycle"]
    db_mod  = sys.modules["server.db.models"]
    db_pkg  = sys.modules["server.db"]

    original_get_db = db_pkg.get_db

    db_mod.Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(db_mod, "_SessionLocal", Session)
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_pkg, "engine", engine)

    yield engine, Session


@pytest.fixture
def app(_patch_db):
    engine, Session = _patch_db

    # Reset the shared lifecycle singleton's internal state so each test
    # starts clean. Route handlers hold a reference to the singleton object
    # itself (not the module attribute), so we mutate it in place.
    import server.core.lifecycle as lc_mod
    lc = lc_mod.lifecycle
    lc._load_fns.clear()
    lc._unload_fns.clear()
    lc._queue = lc_mod.LoadQueue()
    lc._lock = asyncio.Lock()

    from server.app import create_app
    application = create_app()
    return application


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
