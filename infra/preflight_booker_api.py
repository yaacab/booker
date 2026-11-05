"""Check the intended systemd API environment before stopping a running service."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from booker_api.config import Settings, validate_runtime_config
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def _assignments(path: Path, *, unit: bool) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(('#', ';', '[')):
            continue
        if unit:
            if not line.startswith("Environment="):
                continue
            line = line.partition("=")[2]
        elif line.split(None, 1)[0] == "export":
            raise RuntimeError("systemd EnvironmentFile must not use export syntax")
        for assignment in shlex.split(line):
            key, separator, value = assignment.partition("=")
            if separator and key.startswith("BOOKER_"):
                values[key] = value
    return values


def preflight(unit_file: Path, env_file: Path) -> None:
    unit_text = unit_file.read_text(encoding="utf-8")
    exec_lines = [
        line.strip().partition("=")[2]
        for line in unit_text.splitlines()
        if line.strip().startswith("ExecStart=")
    ]
    if not any(
        line.startswith("/usr/bin/env BOOKER_RUNTIME_ENV=production ")
        for line in exec_lines
    ):
        raise RuntimeError("systemd ExecStart must pin BOOKER_RUNTIME_ENV=production")
    if not any("--no-proxy-headers" in shlex.split(line) for line in exec_lines):
        raise RuntimeError("API must preserve the direct TCP peer for trusted proxy IP checks")
    if not any("--no-access-log" in shlex.split(line) for line in exec_lines):
        raise RuntimeError("API access log must not include raw request URLs")
    intended = _assignments(unit_file, unit=True)
    file_values = _assignments(env_file, unit=False)
    database_url = file_values.get("BOOKER_DATABASE_URL", "").strip()
    if not database_url or database_url.startswith("{{"):
        raise RuntimeError("BOOKER_DATABASE_URL is required in the protected env file")
    try:
        parsed_database = make_url(database_url)
    except (ArgumentError, ValueError, TypeError):
        raise RuntimeError("BOOKER_DATABASE_URL is invalid") from None
    if parsed_database.drivername == "sqlite":
        if parsed_database.database != "/opt/booker/data/booker.db":
            raise RuntimeError("production SQLite must use /opt/booker/data/booker.db")
    elif not (
        parsed_database.drivername in {"postgresql", "postgresql+psycopg"}
        and parsed_database.host
        and parsed_database.database
    ):
        raise RuntimeError("BOOKER_DATABASE_URL must be production SQLite or PostgreSQL")
    intended.update(file_values)
    intended["BOOKER_RUNTIME_ENV"] = "production"
    for key in list(os.environ):
        if key.startswith("BOOKER_"):
            del os.environ[key]
    os.environ.update(intended)
    validate_runtime_config(Settings())


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: preflight_booker_api.py <unit-file> <env-file>")
    try:
        preflight(Path(sys.argv[1]), Path(sys.argv[2]))
    except RuntimeError as exc:
        raise SystemExit(f"production config preflight failed: {exc}") from None
    except (OSError, ValueError, TypeError):
        raise SystemExit("production config preflight failed: invalid unit or env file") from None
    print("production config preflight OK")


if __name__ == "__main__":
    main()
