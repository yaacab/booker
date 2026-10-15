#!/usr/bin/env python3
"""Fail-closed preflight for Booker staging harness.

Refuse to proceed when DATABASE_URL / runtime / uploads / compose project
look like production or are unknown. Used by staging-up.sh and unit tests.
Exit 0 only when all checks pass; otherwise exit 2 and print reasons.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from urllib.parse import unquote, urlparse


PRODUCTION_HOSTS = frozenset(
    {
        "5.45.112.180",
        "bukergo.ru",
        "www.bukergo.ru",
        "bookergo.ru",
        "www.bookergo.ru",
        "bukergo.online",
        "www.bukergo.online",
    }
)
PRODUCTION_PATH_MARKERS = (
    "/opt/booker/data",
    "sqlite:////opt/booker",
)
FORBIDDEN_RUNTIME = frozenset({"production", "prod"})
ALLOWED_RUNTIME = frozenset({"test", "staging", "local"})
REQUIRED_COMPOSE_PROJECT = "booker-staging"
ALLOWED_UPLOAD_PREFIXES = ("/tmp/booker-staging",)
ALLOWED_PG_PORTS = frozenset({15432})
ALLOWED_DB_NAME_PREFIXES = ("booker_staging",)
ALLOWED_USER_PREFIXES = ("booker_staging",)


@dataclass
class CheckResult:
    ok: bool
    code: str
    detail: str


def _parse_db_url(url: str) -> tuple[str, str, int | None, str, str]:
    """Return scheme, host, port, database name, username (may be empty)."""
    raw = url.strip()
    if not raw:
        raise ValueError("empty DATABASE_URL")
    if raw.startswith("sqlite:"):
        # sqlite:////abs → /abs; sqlite:///rel → rel
        if raw.startswith("sqlite:////"):
            path = raw[len("sqlite:///") :]
        elif raw.startswith("sqlite:///"):
            path = raw[len("sqlite:///") :]
        else:
            raise ValueError("unsupported sqlite URL form")
        return "sqlite", "localhost", None, path, ""
    # Normalize SQLAlchemy driver URLs: postgresql+psycopg://...
    normalized = re.sub(r"^([a-z0-9]+)\+[a-z0-9]+://", r"\1://", raw, flags=re.I)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"postgresql", "postgres", "sqlite"}:
        raise ValueError(f"unsupported scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    port = parsed.port
    dbname = unquote((parsed.path or "").lstrip("/"))
    user = unquote(parsed.username or "")
    return parsed.scheme, host, port, dbname, user


def check_runtime(runtime: str | None) -> CheckResult:
    value = (runtime or "").strip().lower()
    if not value:
        return CheckResult(False, "runtime_missing", "BOOKER_RUNTIME_ENV is required")
    if value in FORBIDDEN_RUNTIME:
        return CheckResult(False, "runtime_production", f"runtime {value!r} is forbidden for staging")
    if value not in ALLOWED_RUNTIME:
        return CheckResult(False, "runtime_unknown", f"runtime {value!r} is not in allowlist")
    return CheckResult(True, "runtime_ok", value)


def check_compose_project(name: str | None) -> CheckResult:
    value = (name or "").strip()
    if value != REQUIRED_COMPOSE_PROJECT:
        return CheckResult(
            False,
            "compose_project_mismatch",
            f"COMPOSE_PROJECT_NAME must be {REQUIRED_COMPOSE_PROJECT!r}, got {value!r}",
        )
    return CheckResult(True, "compose_project_ok", value)


def check_uploads(path: str | None) -> CheckResult:
    value = (path or "").strip()
    if not value:
        return CheckResult(False, "uploads_missing", "BOOKER_UPLOAD_DIR is required")
    real = os.path.abspath(value)
    if any(marker in real for marker in ("/opt/booker",)):
        return CheckResult(False, "uploads_production", f"uploads path looks like production: {real}")
    if not any(real.startswith(prefix) for prefix in ALLOWED_UPLOAD_PREFIXES):
        return CheckResult(
            False,
            "uploads_not_isolated",
            f"uploads must be under {ALLOWED_UPLOAD_PREFIXES}, got {real}",
        )
    return CheckResult(True, "uploads_ok", real)


def check_payment_provider(provider: str | None) -> CheckResult:
    value = (provider or "").strip().lower()
    if value not in {"stub", "disabled", "external"}:
        return CheckResult(False, "payment_forbidden", f"payment provider {value!r} not allowed for staging")
    if value not in {"stub", "disabled"}:
        # external without live merchant is fail-closed in app; still refuse live-ish labels
        return CheckResult(False, "payment_not_stub", "staging harness requires BOOKER_PAYMENT_PROVIDER=stub")
    return CheckResult(True, "payment_ok", value)


def check_database_url(url: str | None) -> CheckResult:
    if not url or not url.strip():
        return CheckResult(False, "database_missing", "BOOKER_DATABASE_URL is required")
    raw = url.strip()
    lowered = raw.lower()
    for host in PRODUCTION_HOSTS:
        if host in lowered:
            return CheckResult(False, "database_production_host", f"URL mentions production host {host}")
    for marker in PRODUCTION_PATH_MARKERS:
        if marker in raw:
            return CheckResult(False, "database_production_path", f"URL mentions production path {marker}")
    try:
        scheme, host, port, dbname, user = _parse_db_url(raw)
    except ValueError as exc:
        return CheckResult(False, "database_unparseable", str(exc))

    if scheme == "sqlite":
        abs_path = os.path.abspath(dbname)
        if "/opt/booker" in abs_path:
            return CheckResult(False, "sqlite_production_path", abs_path)
        if not abs_path.startswith("/tmp/booker-staging"):
            return CheckResult(
                False,
                "sqlite_not_isolated",
                f"sqlite path must be under /tmp/booker-staging, got {abs_path}",
            )
        return CheckResult(True, "sqlite_ok", abs_path)

    if host not in {"127.0.0.1", "localhost"}:
        return CheckResult(False, "pg_host_not_loopback", f"postgres host must be loopback, got {host!r}")
    if port not in ALLOWED_PG_PORTS:
        return CheckResult(
            False,
            "pg_port_forbidden",
            f"postgres port must be one of {sorted(ALLOWED_PG_PORTS)}, got {port!r}",
        )
    if not any(dbname.startswith(p) for p in ALLOWED_DB_NAME_PREFIXES):
        return CheckResult(
            False,
            "pg_db_name_forbidden",
            f"database name must start with booker_staging, got {dbname!r}",
        )
    if not any(user.startswith(p) for p in ALLOWED_USER_PREFIXES):
        return CheckResult(
            False,
            "pg_user_forbidden",
            f"database user must start with booker_staging, got {user!r}",
        )
    # Reject default non-staging credentials shaped like prod local
    if user == "booker" or dbname == "booker":
        return CheckResult(False, "pg_prod_shaped", "user/db 'booker' is not allowed for staging")
    return CheckResult(True, "pg_ok", f"{host}:{port}/{dbname}")


def check_demo_seed(allow: str | None, runtime: str | None) -> CheckResult:
    value = (allow or "").strip()
    if value not in {"1", "true", "yes"}:
        return CheckResult(False, "demo_seed_required", "BOOKER_ALLOW_DEMO_SEED=1 required for staging harness seed")
    # Already enforced that runtime is not production
    return CheckResult(True, "demo_seed_ok", value)


def run_checks(env: dict[str, str]) -> list[CheckResult]:
    return [
        check_runtime(env.get("BOOKER_RUNTIME_ENV")),
        check_compose_project(env.get("COMPOSE_PROJECT_NAME")),
        check_uploads(env.get("BOOKER_UPLOAD_DIR")),
        check_payment_provider(env.get("BOOKER_PAYMENT_PROVIDER")),
        check_database_url(env.get("BOOKER_DATABASE_URL")),
        check_demo_seed(env.get("BOOKER_ALLOW_DEMO_SEED"), env.get("BOOKER_RUNTIME_ENV")),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Booker staging fail-closed preflight")
    parser.add_argument("--env-file", help="Optional key=value file (secrets outside git)")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if args.env_file:
        path = args.env_file
        if not os.path.isfile(path):
            print(f"preflight FAIL: env-file not found: {path}", file=sys.stderr)
            return 2
        # Refuse reading obvious production env paths
        abs_path = os.path.abspath(path)
        if abs_path.startswith("/opt/booker") or abs_path.startswith("/etc/booker"):
            print(f"preflight FAIL: refusing production env path {abs_path}", file=sys.stderr)
            return 2
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")

    results = run_checks(env)
    failed = [r for r in results if not r.ok]
    for r in results:
        status = "OK" if r.ok else "FAIL"
        print(f"preflight {status} [{r.code}] {r.detail}")
    if failed:
        print("preflight ABORT: no writes/migrations will run", file=sys.stderr)
        return 2
    print("preflight PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
