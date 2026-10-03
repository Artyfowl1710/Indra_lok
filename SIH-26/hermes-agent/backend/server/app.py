"""
FastAPI application factory.
Single process, asyncio concurrency, --workers 1.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.api.routes import admin, generation, health, inference, models, rag, sandbox
from server.backends import llamaswap as ls_driver
from server.backends import vllm_driver, onnx_driver
from server.config import settings
from server.core.lifecycle import lifecycle
from server.db import init_db

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="AI Workbench Server", version="0.1.0", docs_url="/docs")

    # â”€â”€ startup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @app.on_event("startup")
    async def _startup():
        # Ensure DB schema exists
        init_db()

        # Register backend load/unload callbacks with lifecycle manager
        lifecycle.register_backend("llamaswap", ls_driver.load_model, ls_driver.unload_model)
        lifecycle.register_backend("vllm", vllm_driver.load_model, vllm_driver.unload_model)
        lifecycle.register_backend("onnxruntime", onnx_driver.load_model, onnx_driver.unload_model)
        # ComfyUI: single process, lifecycle callbacks are no-ops for per-model load
        from server.backends import comfyui_driver
        lifecycle.register_backend("comfyui", comfyui_driver.load_model, comfyui_driver.unload_model)        # Start llama-swap only if it is not already reachable.
        # llama-swap may be managed outside this Workbench process.
        try:
            if ls_driver.is_running():
                log.info(
                    "llama-swap already running on configured port; using existing process."
                )
            else:
                ls_driver.start()
        except FileNotFoundError:
            log.warning(
                "llama-swap binary missing at startup; it will not be started."
            )

        # Reconcile Workbench DB state with the actual llama-swap runtime.
        await lifecycle.reconcile_loaded_models()
# Start idle reaper background task
        asyncio.create_task(lifecycle.idle_reaper())

        log.info("Workbench server started")

    # â”€â”€ shutdown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @app.on_event("shutdown")
    async def _shutdown():
        ls_driver.stop()
        vllm_driver.stop_all()
        onnx_driver.stop_all()
        from server.backends import comfyui_driver
        comfyui_driver.stop()
        log.info("Workbench server stopped")

    # â”€â”€ routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    app.include_router(health.router)
    app.include_router(admin.router)
    app.include_router(models.router)
    app.include_router(inference.router)
    app.include_router(generation.router)
    app.include_router(rag.router)
    app.include_router(sandbox.router)

    # â”€â”€ static status page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from pathlib import Path
    ui_dir = Path(__file__).parent.parent / "ui"
    if ui_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    return app


app = create_app()

