from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from opensandbox_plus.config import get_settings


def main() -> None:
    settings = get_settings()
    wait_timeout = int(os.getenv("OSB_PLUS_DB_WAIT_TIMEOUT_SECONDS", "60"))

    if _env_enabled("OSB_PLUS_WAIT_FOR_DATABASE", default=True):
        _wait_for_database(settings.database_url, wait_timeout)

    if _env_enabled("OSB_PLUS_RUN_MIGRATIONS", default=True):
        _run_migrations()

    _exec_uvicorn()


def _wait_for_database(database_url: str, timeout_seconds: int) -> None:
    parsed = urlparse(database_url)
    host = parsed.hostname
    port = parsed.port or 5432
    if not host:
        raise RuntimeError("database URL does not include a host")

    deadline = time.monotonic() + timeout_seconds
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=3):
                print(f"database is reachable at {host}:{port}", flush=True)
                return
        except OSError as exc:
            last_error = exc
            time.sleep(1)

    raise TimeoutError(f"database did not become reachable at {host}:{port}: {last_error}")


def _run_migrations() -> None:
    alembic_ini = Path(os.getenv("OSB_PLUS_ALEMBIC_INI", "/app/server/alembic.ini"))
    print(f"running alembic migrations with {alembic_ini}", flush=True)
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(alembic_ini), "upgrade", "head"],
        check=True,
        cwd=alembic_ini.parent,
    )


def _exec_uvicorn() -> None:
    host = os.getenv("OSB_PLUS_HOST", "0.0.0.0")
    port = os.getenv("OSB_PLUS_PORT", "8080")
    log_level = os.getenv("OSB_PLUS_LOG_LEVEL", "info")
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "opensandbox_plus.main:app",
        "--host",
        host,
        "--port",
        port,
        "--log-level",
        log_level,
    ]
    os.execv(sys.executable, command)


def _env_enabled(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


if __name__ == "__main__":
    main()
