"""
Sandbox execution endpoint.
POST /v1/sandbox/execute

Docker path: gVisor (runsc) runtime, --network none, resource limits.
Bare path: restricted subprocess with rlimits. Logs a loud warning.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from server.config import settings
from server.core.auth import require_auth
from server.core.schemas import SandboxRequest, SandboxResponse
from server.db import ApiKey
from server.launcher.detect import is_docker_available

_IS_POSIX = sys.platform != "win32"

log = logging.getLogger(__name__)
router = APIRouter(tags=["sandbox"])

_LANG_IMAGE = {
    "python": "python:3.11-slim",
    "javascript": "node:20-slim",
    "bash": "bash:5",
    "r": "r-base:4.3",
}

_LANG_CMD = {
    "python": ["python", "/sandbox/code.py"],
    "javascript": ["node", "/sandbox/code.js"],
    "bash": ["bash", "/sandbox/code.sh"],
    "r": ["Rscript", "/sandbox/code.r"],
}

_LANG_EXT = {
    "python": "py",
    "javascript": "js",
    "bash": "sh",
    "r": "r",
}


@router.post("/v1/sandbox/execute", response_model=SandboxResponse)
async def execute(
    req: SandboxRequest,
    _: ApiKey = Depends(require_auth),
):
    if is_docker_available():
        return await _run_docker(req)
    else:
        return await _run_bare(req)


# ── Docker + gVisor path ──────────────────────────────────────────────────────

async def _run_docker(req: SandboxRequest) -> SandboxResponse:
    with tempfile.TemporaryDirectory() as tmpdir:
        ext = _LANG_EXT[req.language]
        code_file = Path(tmpdir) / f"code.{ext}"
        code_file.write_text(req.code)

        output_dir = settings.sandbox_output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "docker", "run",
            "--rm",
            "--runtime", settings.sandbox_gvisor_runtime,
            "--network", "none",
            "--memory", f"{settings.sandbox_memory_mb}m",
            "--cpus", str(settings.sandbox_cpu_count),
            "--read-only",
            "--tmpfs", "/tmp:size=64m",
            "-v", f"{tmpdir}:/sandbox:ro",
            "-v", f"{output_dir}:/output:rw",
            _LANG_IMAGE[req.language],
        ] + _LANG_CMD[req.language]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=req.timeout_s
            )
            return SandboxResponse(
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return SandboxResponse(stdout="", stderr="Execution timed out", exit_code=124)


# ── Bare subprocess path (Kaggle / no Docker) ─────────────────────────────────

async def _run_bare(req: SandboxRequest) -> SandboxResponse:
    log.warning(
        "SECURITY WARNING: Running sandbox in bare-subprocess mode (no Docker/gVisor). "
        "This provides REDUCED isolation — suitable for demo/Kaggle only, "
        "NOT for production deployments."
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        ext = _LANG_EXT[req.language]
        code_file = Path(tmpdir) / f"code.{ext}"
        code_file.write_text(req.code)

        python_bin = sys.executable if not _IS_POSIX else "python3"
        lang_bin = {"python": python_bin, "javascript": "node", "bash": "bash", "r": "Rscript"}
        cmd = [lang_bin[req.language], str(code_file)]

        def _set_limits():
            try:
                import resource  # POSIX only — not available on Windows
                resource.setrlimit(resource.RLIMIT_CPU, (req.timeout_s, req.timeout_s + 5))
                mem_bytes = settings.sandbox_memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
            except ImportError:
                pass  # Windows: rlimits unavailable; timeout enforced by asyncio.wait_for

        env = {"PATH": "/usr/bin:/bin", "HOME": tmpdir} if _IS_POSIX else None

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=_set_limits if _IS_POSIX else None,
                env=env,
                cwd=tmpdir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=req.timeout_s + 2
            )
            return SandboxResponse(
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return SandboxResponse(stdout="", stderr="Execution timed out", exit_code=124)
