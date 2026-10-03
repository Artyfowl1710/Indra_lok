"""
workbench CLI — primary interface for setup and administration.

Commands:
  workbench up [--launcher docker|bare] [--profile small|medium|large|auto]
  workbench down
  workbench status
  workbench models list
  workbench models add <name> --source ... --backend ... --type ... --task ...
  workbench models remove <id>
  workbench models sync -f models.yaml
  workbench admin bootstrap
  workbench admin keys create --owner <name> --scope user|admin
  workbench admin keys revoke <id>
"""
from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
from pathlib import Path

import httpx
import typer
import yaml
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(help="AI Workbench server management CLI", no_args_is_help=True)
models_app = typer.Typer(help="Model management", no_args_is_help=True)
admin_app = typer.Typer(help="Admin operations", no_args_is_help=True)
keys_app = typer.Typer(help="API key management", no_args_is_help=True)

app.add_typer(models_app, name="models")
app.add_typer(admin_app, name="admin")
admin_app.add_typer(keys_app, name="keys")


# ── helpers ───────────────────────────────────────────────────────────────────

def _api_base() -> str:
    return os.environ.get("WORKBENCH_API_BASE", "https://localhost:8000")


def _api_key() -> str:
    key = os.environ.get("WORKBENCH_API_KEY", "")
    if not key:
        console.print("[red]WORKBENCH_API_KEY env var not set[/red]")
        raise typer.Exit(1)
    return key


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=_api_base(),
        headers={"Authorization": f"Bearer {_api_key()}"},
        verify=False,   # self-signed cert on laptop/Kaggle
        timeout=30.0,
    )


def _check(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        console.print(f"[red]Error {r.status_code}:[/red] {r.text}")
        raise typer.Exit(1)
    return r.json()


# ── up / down / status ────────────────────────────────────────────────────────

@app.command()
def up(
    launcher: str = typer.Option(None, "--launcher", help="docker or bare (auto-detected if omitted)"),
    profile: str = typer.Option("auto", "--profile", help="small|medium|large|auto"),
):
    """Start the workbench server stack."""
    from server.launcher import detect_launcher, resolve_profile, apply_profile, ensure_tls_cert
    from server.config import settings

    launcher = detect_launcher(launcher)
    resolved = resolve_profile(profile)
    apply_profile(resolved)
    console.print(f"Launcher: [bold]{launcher}[/bold]  Profile: [bold]{resolved}[/bold]")

    ensure_tls_cert(settings.tls_cert_path, settings.tls_key_path)

    if launcher == "docker":
        _up_docker(resolved)
    else:
        _up_bare(resolved)


def _up_docker(profile: str):
    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        console.print("[red]docker-compose.yml not found[/red]")
        raise typer.Exit(1)
    env = {**os.environ, "WORKBENCH_PROFILE": profile}
    subprocess.run(["docker", "compose", "up", "-d"], env=env, check=True)
    console.print("[green]Stack started via Docker Compose[/green]")


def _up_bare(profile: str):
    """Start all services as plain OS processes (Kaggle / no-Docker path)."""
    from server.launcher.detect import is_kaggle
    if is_kaggle():
        console.print("[yellow]Kaggle environment detected — bare-process mode[/yellow]")

    # Start Qdrant
    _start_bare_service(
        name="qdrant",
        cmd=["qdrant", "--config-path", "config/qdrant.yaml"],
        pid_file="data/qdrant.pid",
    )

    # Start gateway (uvicorn, single worker)
    _start_bare_service(
        name="gateway",
        cmd=[
            sys.executable, "-m", "uvicorn",
            "server.app:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--workers", "1",
            "--log-level", "info",
        ],
        pid_file="data/gateway.pid",
    )
    console.print("[green]Bare-process stack started[/green]")


def _start_bare_service(name: str, cmd: list[str], pid_file: str):
    Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    Path(pid_file).write_text(str(proc.pid))
    console.print(f"  [cyan]{name}[/cyan] started (pid {proc.pid})")


@app.command()
def down():
    """Stop the workbench server stack."""
    from server.launcher.detect import is_docker_available
    if is_docker_available() and Path("docker-compose.yml").exists():
        subprocess.run(["docker", "compose", "down"], check=True)
        console.print("[green]Stack stopped[/green]")
    else:
        for pid_file in Path("data").glob("*.pid"):
            try:
                pid = int(pid_file.read_text())
                os.kill(pid, signal.SIGTERM)
                pid_file.unlink()
                console.print(f"  Stopped pid {pid} ({pid_file.stem})")
            except (ProcessLookupError, ValueError):
                pid_file.unlink(missing_ok=True)


@app.command()
def status():
    """Show server health and loaded models."""
    with _client() as c:
        data = _check(c.get("/v1/health"))
    console.print(f"Status: [bold green]{data['status']}[/bold green]")
    t = Table("GPU", "Used MB", "Total MB")
    for g in data.get("gpu", []):
        t.add_row(str(g["id"]), str(g["used_mb"]), str(g["total_mb"]))
    console.print(t)
    console.print("Loaded models:", data.get("models_loaded", []))


# ── models ────────────────────────────────────────────────────────────────────

@models_app.command("list")
def models_list():
    with _client() as c:
        rows = _check(c.get("/v1/models"))["data"]
    t = Table("ID", "Backend", "Type", "Status", "VRAM MB", "Tags", "Pinned")
    for m in rows:
        t.add_row(
            m["id"], m["backend"], m["type"], m["status"],
            str(m.get("vram_mb") or ""), ",".join(m.get("task_tags", [])),
            "yes" if m.get("pinned") else "",
        )
    console.print(t)


@models_app.command("add")
def models_add(
    name: str = typer.Argument(...),
    source: str = typer.Option(..., "--source"),
    backend: str = typer.Option(..., "--backend"),
    model_type: str = typer.Option(..., "--type"),
    task: list[str] = typer.Option([], "--task"),
    pinned: bool = typer.Option(False, "--pinned"),
    vram_mb: int = typer.Option(None, "--vram-mb"),
):
    """Register a model. --source can be a local path, artifactory path, or hf:<repo_id>."""
    if source.startswith("hf:"):
        src = {"type": "hf_id", "hf_id": source[3:]}
    elif source.startswith("http") or "/" in source and not Path(source).exists():
        src = {"type": "artifactory", "path": source}
    else:
        src = {"type": "local_path", "path": source}

    payload = {
        "name": name,
        "source": src,
        "backend": backend,
        "type": model_type,
        "task_tags": task,
        "pinned": pinned,
    }
    if vram_mb:
        payload["vram_mb"] = vram_mb

    with _client() as c:
        data = _check(c.post("/v1/models", json=payload))
    console.print(f"[green]Registered:[/green] {data['id']} (status={data['status']})")


@models_app.command("remove")
def models_remove(model_id: str = typer.Argument(...)):
    with _client() as c:
        r = c.delete(f"/v1/models/{model_id}")
    if r.status_code == 409:
        console.print(f"[red]409 Conflict:[/red] {r.json().get('detail')}")
        raise typer.Exit(1)
    if r.status_code == 204:
        console.print(f"[green]Removed:[/green] {model_id}")
    else:
        _check(r)


@models_app.command("sync")
def models_sync(
    file: Path = typer.Option(..., "-f", "--file", exists=True),
):
    """Reconcile models.yaml against the live server."""
    manifest = yaml.safe_load(file.read_text())
    entries = manifest.get("models", [])
    with _client() as c:
        data = _check(c.post("/v1/models/sync", json=entries))
    console.print(f"Registered: {data['registered']}")
    console.print(f"Removed:    {data['removed']}")
    console.print(f"Unchanged:  {data['unchanged']}")
    if data["skipped_busy"]:
        console.print(f"[yellow]Skipped (busy):[/yellow] {data['skipped_busy']}")


# ── admin ─────────────────────────────────────────────────────────────────────

@admin_app.command("bootstrap")
def admin_bootstrap():
    """
    One-time: generate the first superuser API key.
    Prints the key to stdout — never stored in plaintext, never repeatable.
    """
    from server.core.auth import generate_key, hash_key
    from server.db import ApiKey, init_db, SessionLocal
    import secrets as _secrets

    init_db()
    with SessionLocal() as db:
        existing = db.query(ApiKey).filter(ApiKey.scope == "admin", ApiKey.revoked == False).first()  # noqa
        if existing:
            console.print("[red]An admin key already exists. Use the API to create additional keys.[/red]")
            raise typer.Exit(1)

        plaintext = generate_key()
        key_id = _secrets.token_hex(8)
        row = ApiKey(
            key_id=key_id,
            key_hash=hash_key(plaintext),
            owner="bootstrap",
            scope="admin",
        )
        db.add(row)
        db.commit()

    console.print("\n[bold green]Bootstrap admin key (shown once — save it now):[/bold green]")
    console.print(f"\n  [bold yellow]{plaintext}[/bold yellow]\n")
    console.print("Set WORKBENCH_API_KEY in your environment or Hermes config.")


@keys_app.command("create")
def keys_create(
    owner: str = typer.Option(..., "--owner"),
    scope: str = typer.Option(..., "--scope"),
):
    with _client() as c:
        data = _check(c.post("/v1/admin/keys", json={"owner": owner, "scope": scope}))
    console.print(f"\n[bold green]New API key (shown once):[/bold green]\n  [bold yellow]{data['api_key']}[/bold yellow]\n")


@keys_app.command("revoke")
def keys_revoke(key_id: str = typer.Argument(...)):
    with _client() as c:
        r = c.delete(f"/v1/admin/keys/{key_id}")
    if r.status_code == 204:
        console.print(f"[green]Revoked:[/green] {key_id}")
    else:
        _check(r)


@admin_app.command("export-client")
def admin_export_client(
    owner: str = typer.Option(..., "--owner", help="Client identifier or machine name (e.g. laptop-analyst-1)"),
    server_url: str = typer.Option(None, "--server-url", help="Public/LAN base URL of this server (e.g. http://192.168.1.100:8000)"),
    scope: str = typer.Option("user", "--scope", help="Key scope: user or admin"),
):
    """
    Generate a dynamic client API key and print ready-to-use configuration blocks
    for INDRA, Hermes Agent, Codex, OpenAI SDK, Cursor, and Continue.
    """
    base_url = (server_url or _api_base()).rstrip("/")
    with _client() as c:
        data = _check(c.post("/v1/admin/keys", json={"owner": owner, "scope": scope}))
    api_key = data["api_key"]

    console.print("\n" + "=" * 65)
    console.print(f"[bold cyan]DYNAMIC CLIENT ONBOARDING PACKET FOR: {owner}[/bold cyan]")
    console.print("=" * 65)
    console.print(f"Generated Key (shown once): [bold yellow]{api_key}[/bold yellow]")
    console.print(f"Server Base URL:            [bold green]{base_url}[/bold green]\n")

    console.print("[bold]1. Single-Command Client Pairing (INDRA / Hermes CLI):[/bold]")
    console.print(f"  [cyan]indra set-server --url {base_url} --key {api_key}[/cyan]\n")

    console.print("[bold]2. Client .env Configuration Block:[/bold]")
    console.print(f"  WORKBENCH_API_BASE={base_url}")
    console.print(f"  WORKBENCH_API_KEY={api_key}")
    console.print(f"  OPENAI_API_KEY={api_key}")
    console.print(f"  OPENAI_BASE_URL={base_url}/v1\n")

    console.print("[bold]3. Health & Connectivity Verification (cURL):[/bold]")
    console.print(f"  curl -s -H \"Authorization: Bearer {api_key}\" {base_url}/v1/models\n")

    console.print("[bold]4. OpenAI Python SDK Integration:[/bold]")
    console.print("  from openai import OpenAI")
    console.print(f"  client = OpenAI(base_url=\"{base_url}/v1\", api_key=\"{api_key}\")")
    console.print("  response = client.chat.completions.create(")
    console.print("      model=\"indra-auto\",")
    console.print("      messages=[{\"role\": \"user\", \"content\": \"Hello!\"}]")
    console.print("  )")
    console.print("  print(response.choices[0].message.content)")
    console.print("=" * 65 + "\n")


# ── rag ───────────────────────────────────────────────────────────────────────

rag_app = typer.Typer(help="RAG operations", no_args_is_help=True)
app.add_typer(rag_app, name="rag")


@rag_app.command("reindex")
def rag_reindex():
    """
    Warn that changing the embedding model requires a full reindex.
    Does not automatically reindex — operator must confirm.
    """
    console.print(
        "[bold red]WARNING:[/bold red] Reindexing will delete all existing vectors. "
        "All prior RAG data will be incompatible with a new embedding model. "
        "Run workbench rag reindex --confirm to proceed."
    )


if __name__ == "__main__":
    app()
