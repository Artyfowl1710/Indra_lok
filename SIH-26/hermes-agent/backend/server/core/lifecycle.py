"""
ModelLifecycleManager â€” GPU-aware load/evict/queue with hard invariants.

Hard invariants (enforced, tested):
  1. A model with active_requests > 0 is NEVER evicted or unloaded.
  2. A pinned model is NEVER idle-evicted (can still be manually removed if idle).
  3. Load requests that can't fit are queued and return 202, never hard-failed.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator, Callable, Coroutine

from sqlalchemy.orm import Session

from server.config import settings
from server.core.gpu import (
    query_gpus, total_free_vram_mb, probe_vram_delta_mb, estimate_vram_heuristic
)
from server.db import ModelRecord, SessionLocal

log = logging.getLogger(__name__)


class BusyModelError(Exception):
    """Raised when an operation is attempted on a model with active requests."""


class LoadQueue:
    """Simple FIFO queue for deferred model loads when VRAM is exhausted."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, asyncio.Future]] = asyncio.Queue()

    async def enqueue(self, model_id: str) -> asyncio.Future:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        await self._queue.put((model_id, fut))
        return fut

    async def drain_one(self) -> tuple[str, asyncio.Future] | None:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


class ModelLifecycleManager:
    """
    Owns model status transitions and VRAM budget.

    Backend-specific load/unload mechanics are injected as async callables
    so this class stays backend-agnostic.
    """

    def __init__(self) -> None:
        self._load_fns: dict[str, Callable[[str], Coroutine]] = {}
        self._unload_fns: dict[str, Callable[[str], Coroutine]] = {}
        self._queue = LoadQueue()
        self._lock = asyncio.Lock()   # serialises status transitions; not held during I/O

    # â”€â”€ backend registration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def register_backend(
        self,
        backend: str,
        load_fn: Callable[[str], Coroutine],
        unload_fn: Callable[[str], Coroutine],
    ) -> None:
        self._load_fns[backend] = load_fn
        self._unload_fns[backend] = unload_fn


    async def reconcile_loaded_models(self) -> None:
        """
        Reconcile Workbench DB state with models actually loaded by llama-swap.

        llama-swap can survive independently of the Workbench process, so
        the DB may incorrectly say "cold" after a Workbench restart.
        """
        try:
            from server.backends import llamaswap as ls_driver

            loaded = await ls_driver.get_loaded_models()
        except Exception as exc:
            log.warning("Could not reconcile llama-swap state: %s", exc)
            return

        now = datetime.utcnow()

        with SessionLocal() as db:
            # active_requests belongs to this gateway process.  If Workbench
            # was restarted while a request was in flight, the old busy count
            # is stale and would permanently pin every model as busy.  Clear
            # those orphaned counters before reconciling llama-swap's state.
            stale = (
                db.query(ModelRecord)
                .filter(ModelRecord.backend == "llamaswap", ModelRecord.active_requests > 0)
                .all()
            )
            for m in stale:
                m.active_requests = 0
                if m.status == "busy":
                    m.status = "cold"

            if not loaded:
                db.commit()
                log.info("llama-swap reconciliation: no loaded models reported")
                return

            models = (
                db.query(ModelRecord)
                .filter(
                    ModelRecord.backend == "llamaswap",
                    ModelRecord.id.in_(loaded),
                )
                .all()
            )

            for m in models:
                if m.active_requests == 0:
                    m.status = "idle"
                    m.last_used_at = now

                    log.info(
                        "Reconciled llama-swap model %s: loaded -> idle",
                        m.id,
                    )

            db.commit()
    # â”€â”€ request tracking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @asynccontextmanager
    async def track_request(self, model_id: str) -> AsyncIterator[None]:
        """
        Context manager: increments active_requests on enter, decrements on exit.
        Ensures the model is loaded before yielding.
        """
        while True:
            await self._ensure_loaded(model_id)
            async with self._lock:
                with SessionLocal() as db:
                    m = _get_model(db, model_id)
                    if m.status in ("idle", "busy"):
                        m.active_requests += 1
                        m.last_used_at = datetime.utcnow()
                        m.status = "busy"
                        db.commit()
                        break
        try:
            yield
        finally:
            self._decrement(model_id)

    def _decrement(self, model_id: str) -> None:
        with SessionLocal() as db:
            m = _get_model(db, model_id)
            m.active_requests = max(0, m.active_requests - 1)
            if m.active_requests == 0:
                m.status = "idle"
            db.commit()

    # â”€â”€ load / unload â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _ensure_loaded(self, model_id: str) -> None:
        # An external llama-swap may have loaded the model after gateway startup.
        # Reconcile before budgeting VRAM so its allocation is not counted twice.
        await self.reconcile_loaded_models()
        with SessionLocal() as db:
            m = _get_model(db, model_id)
            if m.status in ("idle", "busy"):
                return
            backend = m.backend

        # Enforce profile-level concurrency cap for vLLM processes
        if backend == "vllm" and self.vllm_at_capacity():
            log.warning(
                "vLLM backend at process capacity (%d max); queuing load request for %s",
                settings.max_concurrent_vllm_processes,
                model_id,
            )
            fut = await self._queue.enqueue(model_id)
            await fut
            return

        if await self._needs_eviction(model_id):
            await self._make_room(model_id)

        async with self._lock:
            with SessionLocal() as db:
                m = _get_model(db, model_id)
                if m.status in ("idle", "busy"):
                    return
                m.status = "loading"
                db.commit()

        try:
            load_fn = self._load_fns.get(backend)
            if load_fn:
                with SessionLocal() as db:
                    m = _get_model(db, model_id)
                    existing_vram = m.vram_mb
                    local_path = m.local_path

                if existing_vram is None:
                    async def _do_load():
                        await load_fn(model_id)

                    measured = await probe_vram_delta_mb(_do_load)
                    if measured is None or measured == 0:
                        measured = estimate_vram_heuristic(local_path)

                    with SessionLocal() as db:
                        m = _get_model(db, model_id)
                        m.vram_mb = measured
                        db.commit()
                else:
                    await load_fn(model_id)

            with SessionLocal() as db:
                m = _get_model(db, model_id)
                m.status = "idle"
                db.commit()
            log.info("model %s loaded", model_id)
        except Exception:
            with SessionLocal() as db:
                m = _get_model(db, model_id)
                m.status = "cold"
                db.commit()
            raise

    async def _needs_eviction(self, model_id: str) -> bool:
        with SessionLocal() as db:
            m = _get_model(db, model_id)
            # llama-swap owns GGUF residency and switches models itself. Its
            # currently loaded process is already included in free-VRAM data,
            # so applying Workbench's generic budget here double-counts it.
            if m.backend == "llamaswap":
                return False
            needed = m.vram_mb or 0
        if needed == 0:
            return False
        return total_free_vram_mb() < needed

    async def _make_room(self, model_id: str) -> None:
        """LRU-evict idle models until there's room. Queue if impossible."""
        with SessionLocal() as db:
            needed = (_get_model(db, model_id).vram_mb or 0)
            candidates = (
                db.query(ModelRecord)
                .filter(
                    ModelRecord.status == "idle",
                    ModelRecord.active_requests == 0,
                    ModelRecord.pinned == False,  # noqa: E712
                    ModelRecord.id != model_id,
                )
                .order_by(ModelRecord.last_used_at.asc())
                .all()
            )
            to_evict = [c.id for c in candidates]

        for mid in to_evict:
            if total_free_vram_mb() >= needed:
                break
            await self._unload(mid)

        if needed > 0 and total_free_vram_mb() < needed:
            log.warning(
                "Cannot free enough VRAM for %s (%d MB needed); all eligible models busy. "
                "Request queued.",
                model_id,
                needed,
            )
            fut = await self._queue.enqueue(model_id)
            await fut   # caller blocks here until space is available

    async def _unload(self, model_id: str) -> None:
        """Unload a model. HARD INVARIANT: never called when active_requests > 0."""
        async with self._lock:
            with SessionLocal() as db:
                m = _get_model(db, model_id)
                # â”€â”€ HARD INVARIANT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if m.active_requests > 0:
                    raise BusyModelError(
                        f"Attempted to unload {model_id} with {m.active_requests} active requests"
                    )
                m.status = "unloading"
                db.commit()

        backend = self._backend_for(model_id)
        unload_fn = self._unload_fns.get(backend)
        if unload_fn:
            await unload_fn(model_id)

        with SessionLocal() as db:
            m = _get_model(db, model_id)
            m.status = "cold"
            db.commit()
        log.info("model %s unloaded", model_id)

    async def force_unload(self, model_id: str) -> None:
        """
        Called by DELETE /v1/models/{id}.
        Raises BusyModelError (â†’ 409) if model has active requests.
        """
        with SessionLocal() as db:
            m = _get_model(db, model_id)
            if m.active_requests > 0:
                raise BusyModelError(f"{model_id} has {m.active_requests} active requests")
        await self._unload(model_id)

    # â”€â”€ idle reaper (background task) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def idle_reaper(self) -> None:
        """Runs forever; call as asyncio.create_task()."""
        while True:
            await asyncio.sleep(settings.lifecycle_poll_interval_s)
            await self._reap_idle()
            await self._drain_queue()

    async def _reap_idle(self) -> None:
        now = datetime.utcnow()
        with SessionLocal() as db:
            candidates = (
                db.query(ModelRecord)
                .filter(
                    ModelRecord.status == "idle",
                    ModelRecord.active_requests == 0,
                    ModelRecord.pinned == False,  # noqa: E712
                )
                .all()
            )
            to_unload = []
            for m in candidates:
                ttl = m.ttl_s if m.ttl_s is not None else settings.model_default_ttl_s
                if m.last_used_at and (now - m.last_used_at).total_seconds() > ttl:
                    to_unload.append(m.id)

        for mid in to_unload:
            try:
                await self._unload(mid)
            except BusyModelError:
                pass  # raced with a new request; skip

    async def _drain_queue(self) -> None:
        """After each reap cycle, try to satisfy queued load requests."""
        item = await self._queue.drain_one()
        if item is None:
            return
        model_id, fut = item
        if not fut.done():
            try:
                await self._ensure_loaded(model_id)
                fut.set_result(None)
            except Exception as exc:
                fut.set_exception(exc)

    # â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _backend_for(self, model_id: str) -> str:
        with SessionLocal() as db:
            return _get_model(db, model_id).backend

    # â”€â”€ max_concurrent_vllm_processes enforcement â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _vllm_process_count(self) -> int:
        with SessionLocal() as db:
            return (
                db.query(ModelRecord)
                .filter(
                    ModelRecord.backend == "vllm",
                    ModelRecord.status.in_(["idle", "busy", "loading"]),
                )
                .count()
            )

    def vllm_at_capacity(self) -> bool:
        cap = settings.max_concurrent_vllm_processes
        if cap == 0:
            return False
        return self._vllm_process_count() >= cap


def _get_model(db: Session, model_id: str) -> ModelRecord:
    m = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if m is None:
        raise KeyError(f"Model {model_id!r} not found in registry")
    return m


# â”€â”€ singleton â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
lifecycle = ModelLifecycleManager()

