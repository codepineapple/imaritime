#!/usr/bin/env python3
"""Development environment bootstrap for the iMaritime backend.

NOTE: despite living at the project root, this is an *orchestration*
script, not a packaging one (no `setuptools.setup()` here -- packaging
metadata lives in `pyproject.toml`, managed by `uv`). Its job is to
bring up every moving part needed to run the backend locally in one
command:

    uv run python init.py

What it does, in order:
  1. Preflight checks (required directories).
  2. Runs `docker compose up -d` (see `compose.yaml`) to start Redis,
     Qdrant, and PostgreSQL -- all three, the same way, with the same
     persistent-volume story. This replaces the previous inconsistent
     setup where Redis expected you to have it running yourself while
     Qdrant was started automatically; now nothing is special-cased.
     Waits for each service's port to actually be reachable before
     continuing (see `--skip-docker` to opt out entirely, e.g. if you
     manage these services some other way).
  3. Runs `alembic upgrade head` so the PostgreSQL schema is current.
  4. Starts a Celery worker as a background process.
  5. Starts the FastAPI app (uvicorn) in the foreground.

Ctrl+C stops the Celery worker and uvicorn cleanly. The Docker Compose
services are deliberately left running -- they're persistent
infrastructure with persistent volumes, so there's no data-loss risk in
leaving them up, and it makes the next `init.py` run instant. Run
`docker compose down` yourself if you want to fully stop them.

Every subprocess is launched via `uv run ...` so the correct
project-managed virtual environment is used regardless of whether this
script itself is run via `uv run` or an already-activated `.venv`.

Flags:
    --skip-docker             Don't run `docker compose up -d` at all.
    --skip-migrate            Don't run `alembic upgrade head`.
    --skip-celery             Don't start a Celery worker.
    --host HOST               Uvicorn bind host (default 127.0.0.1).
    --port PORT               Uvicorn bind port (default 8000).
    --reload                  Uvicorn autoreload (development only).
    --celery-pool POOL        Celery worker --pool (default: "solo" on
                              Windows, "prefork" everywhere else --
                              Windows' prefork support is broken enough
                              that --concurrency silently does nothing;
                              solo sidesteps that entirely).
    --celery-concurrency N    Celery worker --concurrency (default 2).
                              Ignored (with a warning) when the pool is
                              "solo", which is inherently single-process
                              and doesn't take a concurrency value.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent
CHILD_PROCESSES: list[subprocess.Popen] = []


def _log(msg: str) -> None:
    """Prints a timestamped, prefixed log line.

    Args:
        msg: The message to print.
    """
    print(f"[init] {msg}", flush=True)


def _port_is_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Checks whether a TCP port is currently accepting connections.

    Args:
        host: Hostname or IP to check.
        port: Port number to check.
        timeout: Connection attempt timeout, in seconds.

    Returns:
        True if a connection succeeded.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ensure_directories(settings) -> None:
    """Creates the upload storage directory if missing.

    Args:
        settings: The application `Settings` instance.
    """
    Path(settings.UPLOAD_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    _log("Data directories ready (uploads/).")


def _docker_compose_command() -> list[str]:
    """Resolves the right Docker Compose invocation for this machine.

    Returns:
        `["docker", "compose"]` (the modern plugin form) if available,
        otherwise `["docker-compose"]` (the legacy standalone binary).

    Raises:
        SystemExit: If neither is available.
    """
    if shutil.which("docker"):
        probe = subprocess.run(["docker", "compose", "version"], capture_output=True)
        if probe.returncode == 0:
            return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    _log(
        "Docker Compose was not found (tried `docker compose` and `docker-compose`).\n"
        "  Install Docker Desktop (Windows/Mac) or Docker Engine + the compose "
        "plugin (Linux), then re-run this script, or pass --skip-docker and start "
        "Redis, Qdrant, and PostgreSQL yourself."
    )
    raise SystemExit(1)


def _start_docker_services(settings) -> None:
    """Starts Redis, Qdrant, and PostgreSQL via `docker compose up -d`.

    Idempotent: safe to run against services that are already up (compose
    only (re)creates what's missing/changed). Waits for each service's
    port to be reachable before returning.

    Args:
        settings: The application `Settings` instance (used to read
            which host/port to wait on for PostgreSQL).

    Raises:
        SystemExit: If `docker compose up -d` fails, or a service
            doesn't become reachable within a reasonable time.
    """
    compose_cmd = _docker_compose_command()
    compose_file = PROJECT_ROOT / "compose.yaml"

    _log("Starting Redis, Qdrant, and PostgreSQL via Docker Compose ...")
    result = subprocess.run(
        [*compose_cmd, "-f", str(compose_file), "up", "-d"], cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        raise SystemExit("`docker compose up -d` failed -- see output above.")

    services_to_check = [
        ("Redis", "localhost", 6379),
        ("Qdrant", "localhost", 6333),
        ("PostgreSQL", settings.POSTGRES_HOST, settings.POSTGRES_PORT),
    ]
    for name, host, port in services_to_check:
        for _ in range(60):
            if _port_is_open(host, port):
                _log(f"{name} is up.")
                break
            time.sleep(0.5)
        else:
            raise SystemExit(
                f"{name} did not become reachable at {host}:{port} within 30 seconds."
            )


def _run_migrations() -> None:
    """Runs `alembic upgrade head` via `uv run`.

    Raises:
        SystemExit: If the migration command exits non-zero.
    """
    _log("Applying database migrations (alembic upgrade head) ...")
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"], cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        raise SystemExit("Alembic migration failed -- see output above.")
    _log("Migrations applied.")


def _default_celery_pool() -> str:
    """Picks a sensible default Celery worker pool for the current OS.

    Returns:
        "solo" on Windows (prefork is unreliable there, and
        `--concurrency` is silently ignored under it), "prefork" everywhere else.
    """
    return "solo" if platform.system() == "Windows" else "prefork"


def _start_celery(pool: str, concurrency: int) -> None:
    """Starts a Celery worker as a background process, via `uv run`.

    Args:
        pool: Worker pool implementation (e.g. "prefork", "solo", "threads").
        concurrency: Worker `--concurrency` value. Ignored (with a
            logged warning) if `pool == "solo"`, which is inherently
            single-process and has no concurrency setting.
    """
    cmd = [
        "uv",
        "run",
        "celery",
        "-A",
        "app.tasks.celery_app",
        "worker",
        "--loglevel=info",
        f"--pool={pool}",
    ]
    if pool == "solo":
        if concurrency != 2:  # only warn if the user actually asked for something
            _log(
                f"--celery-concurrency={concurrency} ignored: the 'solo' pool doesn't take a concurrency value."
            )
    else:
        cmd.append(f"--concurrency={concurrency}")

    _log(
        f"Starting Celery worker (pool={pool}"
        + ("" if pool == "solo" else f", concurrency={concurrency}")
        + ") ..."
    )
    proc = subprocess.Popen(cmd, cwd=PROJECT_ROOT)
    CHILD_PROCESSES.append(proc)


def _stop_children() -> None:
    """Terminates every tracked background process, escalating to kill if needed.

    Does not touch the Docker Compose services -- see the module
    docstring for why they're intentionally left running.
    """
    for proc in CHILD_PROCESSES:
        if proc.poll() is None:
            _log(f"Stopping process pid={proc.pid} ...")
            proc.terminate()
    for proc in CHILD_PROCESSES:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    """Parses CLI flags and runs the full dev-environment bootstrap sequence."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument("--skip-migrate", action="store_true")
    parser.add_argument("--skip-celery", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--celery-pool",
        default=None,
        help="Default: solo on Windows, prefork elsewhere.",
    )
    parser.add_argument("--celery-concurrency", type=int, default=2)
    args = parser.parse_args()

    sys.path.insert(0, str(PROJECT_ROOT))
    from app.core.config import get_settings  # noqa: E402 - after sys.path fix

    settings = get_settings()

    _ensure_directories(settings)

    if not args.skip_docker:
        _start_docker_services(settings)
    else:
        _log("Skipping Docker Compose services (--skip-docker).")

    if not args.skip_migrate:
        _run_migrations()
    else:
        _log("Skipping migrations (--skip-migrate).")

    if not args.skip_celery:
        pool = args.celery_pool or _default_celery_pool()
        _start_celery(pool, args.celery_concurrency)
    else:
        _log("Skipping Celery worker (--skip-celery).")

    _log(f"Starting API server at http://{args.host}:{args.port} (docs at /docs) ...")
    reload_flag = ["--reload"] if args.reload else []
    try:
        subprocess.run(
            [
                "uv",
                "run",
                "uvicorn",
                "app.main:app",
                "--host",
                args.host,
                "--port",
                str(args.port),
                *reload_flag,
            ],
            cwd=PROJECT_ROOT,
        )
    finally:
        _stop_children()


if __name__ == "__main__":
    main()
