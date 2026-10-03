"""
Environment detection — called once at startup.
No network calls.
"""
from __future__ import annotations

import os
import socket
from pathlib import Path


def is_kaggle() -> bool:
    return (
        os.environ.get("KAGGLE_KERNEL_RUN_TYPE") is not None
        or Path("/kaggle").exists()
    )


def is_docker_available() -> bool:
    if is_kaggle():
        return False
    # Check for Docker socket on POSIX or named pipe on Windows
    for sock_path in ("/var/run/docker.sock", "/run/docker.sock", r"\\.\pipe\docker_engine"):
        if Path(sock_path).exists():
            return True
    return False


def detect_launcher(explicit: str | None = None) -> str:
    """Returns 'docker' or 'bare'."""
    if explicit in ("docker", "bare"):
        return explicit
    return "docker" if is_docker_available() else "bare"
