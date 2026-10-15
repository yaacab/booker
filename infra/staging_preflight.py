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
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
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
# Secrets must stay outside Git; allow agent/tmp + home, never production paths.
ALLOWED_ENV_FILE_PREFIXES = ("/tmp/", "/home/", "/var/tmp/")
FORBIDDEN_ENV_PREFIXES = ("/opt/booker", "/etc/booker")
ALLOWED_PG_PORTS = frozenset({15432})
ALLOWED_DB_NAME_PREFIXES = ("booker_staging",)
ALLOWED_USER_PREFIXES = ("booker_staging",)
SECRET_ENV_KEYS = frozenset(
    {
        "BOOKER_DATABASE_URL",
        "BOOKER_STAGING_PGPASSWORD",
        "BOOKER_STAGING_POSTGRES_PASSWORD",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "BOOKER_SECRET_KEY",
        "BOOKER_WEBHOOK_SECRET",
        "BOOKER_TOTP_ENCRYPTION_KEY",
        "BOOKER_SESSION_SECRET",
        "PASSWORD",
        "SECRET",
    }
)


@dataclass
class CheckResult:
    ok: bool
    code: str
    detail: str


def _parse_db_url(url: str) -> tuple[str, str, int | None, str, str, str]:
    """Return scheme, host, port, database name, username, password (may be empty)."""
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
        return "sqlite", "localhost", None, path, "", ""
    # Normalize SQLAlchemy driver URLs: postgresql+psycopg://...
    normalized = re.sub(r"^([a-z0-9]+)\+[a-z0-9]+://", r"\1://", raw, flags=re.I)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"postgresql", "postgres", "sqlite"}:
        raise ValueError(f"unsupported scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    port = parsed.port
    dbname = unquote((parsed.path or "").lstrip("/"))
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    return parsed.scheme, host, port, dbname, user, password


def _is_unreplaced_secret_template(value: str) -> bool:
    """True for example placeholders that must never be used to start staging."""
    stripped = (value or "").strip()
    if not stripped:
        return True
    if "{{" in stripped or "}}" in stripped:
        return True
    upper = stripped.upper()
    return any(
        marker in upper
        for marker in (
            "REPLACE_WITH_",
            "CHANGE_ME",
            "YOUR_PASSWORD",
            "TODO_PASSWORD",
            "<SET",
            "PASSWORD_HERE",
        )
    )


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


def resolve_path_nofollow(path: str) -> tuple[str, bool]:
    """Return (abspath without following final symlink, is_symlink)."""
    abs_path = os.path.abspath(path)
    return abs_path, os.path.islink(abs_path)


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
    # Symlink escape: final component or any parent under /opt/booker after resolve
    if os.path.lexists(real):
        try:
            resolved = os.path.realpath(real)
        except OSError as exc:
            return CheckResult(False, "uploads_unresolvable", str(exc))
        if any(marker in resolved for marker in ("/opt/booker", "/etc/booker")):
            return CheckResult(
                False,
                "uploads_symlink_escape",
                f"uploads resolves to forbidden path: {resolved}",
            )
        if not any(resolved.startswith(prefix) for prefix in ALLOWED_UPLOAD_PREFIXES):
            return CheckResult(
                False,
                "uploads_symlink_escape",
                f"uploads symlink escapes allowlist: {resolved}",
            )
    return CheckResult(True, "uploads_ok", real)


def check_env_file_path(path: str | None) -> CheckResult:
    if not path or not str(path).strip():
        return CheckResult(False, "env_file_missing", "env-file path is required")
    abs_path = os.path.abspath(path.strip())
    if any(abs_path.startswith(p) for p in FORBIDDEN_ENV_PREFIXES):
        return CheckResult(False, "env_file_production", f"refusing production env path {abs_path}")
    if not any(abs_path.startswith(p) for p in ALLOWED_ENV_FILE_PREFIXES):
        return CheckResult(
            False,
            "env_file_not_isolated",
            f"env-file must be under {ALLOWED_ENV_FILE_PREFIXES}, got {abs_path}",
        )
    if os.path.lexists(abs_path):
        try:
            resolved = os.path.realpath(abs_path)
        except OSError as exc:
            return CheckResult(False, "env_file_unresolvable", str(exc))
        if any(resolved.startswith(p) for p in FORBIDDEN_ENV_PREFIXES):
            return CheckResult(
                False,
                "env_file_symlink_escape",
                f"env-file resolves to forbidden path: {resolved}",
            )
    return CheckResult(True, "env_file_ok", abs_path)


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
        scheme, host, port, dbname, user, password = _parse_db_url(raw)
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

    if _is_unreplaced_secret_template(password):
        return CheckResult(
            False,
            "database_password_template",
            "BOOKER_DATABASE_URL still has an unreplaced password placeholder",
        )

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


def check_staging_password_env(password: str | None) -> CheckResult:
    value = (password or "").strip()
    if not value:
        # Optional when only SQLITE; run_checks includes this only if key present
        return CheckResult(True, "pgpassword_absent", "ok")
    if _is_unreplaced_secret_template(value):
        return CheckResult(
            False,
            "pgpassword_template",
            "BOOKER_STAGING_PGPASSWORD still has an unreplaced placeholder",
        )
    return CheckResult(True, "pgpassword_ok", "set")


def check_demo_seed(allow: str | None, runtime: str | None) -> CheckResult:
    value = (allow or "").strip()
    if value not in {"1", "true", "yes"}:
        return CheckResult(False, "demo_seed_required", "BOOKER_ALLOW_DEMO_SEED=1 required for staging harness seed")
    # Already enforced that runtime is not production
    return CheckResult(True, "demo_seed_ok", value)


def check_port_available(host: str, port: int) -> CheckResult:
    """Detect port conflict without killing foreign processes.

    Bind without SO_REUSEADDR so an existing LISTEN/bound socket is visible.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        try:
            sock.bind((host, port))
        except OSError as exc:
            return CheckResult(
                False,
                "port_in_use",
                f"{host}:{port} busy ({exc}); refuse to kill foreign process",
            )
        return CheckResult(True, "port_ok", f"{host}:{port}")
    finally:
        sock.close()


def redact_secrets(text: str, extra_values: list[str] | None = None) -> str:
    """Redact password-like tokens from compose config / logs."""
    out = text
    # URL user:password@
    out = re.sub(r"(://[^:/@\s]+:)([^@/\s]+)(@)", r"\1***\3", out)
    # YAML-ish password: value / PASSWORD=value
    out = re.sub(
        r"(?i)((?:password|secret|token|api[_-]?key|passwd)\s*[:=]\s*)([^\s\"']+)",
        r"\1***",
        out,
    )
    for value in extra_values or []:
        if value and len(value) >= 4 and value in out:
            out = out.replace(value, "***")
    return out


def collect_secret_values(env: dict[str, str]) -> list[str]:
    values: list[str] = []
    for key, value in env.items():
        upper = key.upper()
        if upper in SECRET_ENV_KEYS or any(
            marker in upper for marker in ("PASSWORD", "SECRET", "TOKEN", "API_KEY")
        ):
            stripped = (value or "").strip().strip('"').strip("'")
            if stripped and len(stripped) >= 4:
                values.append(stripped)
                # Also redact password segment inside URLs
                if "://" in stripped and "@" in stripped:
                    try:
                        _, _, _, _, _user, pwd = _parse_db_url(stripped)
                    except ValueError:
                        continue
                    if pwd and not _is_unreplaced_secret_template(pwd):
                        values.append(pwd)
    return values


def check_web_build_stamp(next_dir: str, expected_sha: str) -> CheckResult:
    """Refuse unknown .next without matching SHA stamp under /tmp/booker-staging."""
    stamp_path = Path("/tmp/booker-staging/web-build.sha")
    if not os.path.isdir(next_dir):
        return CheckResult(True, "web_build_absent", "no .next — build required")
    if not stamp_path.is_file():
        return CheckResult(
            False,
            "web_build_stamp_missing",
            f"refuse unknown .next without SHA stamp at {stamp_path}",
        )
    stamped = stamp_path.read_text(encoding="utf-8").strip()
    if stamped != expected_sha.strip():
        return CheckResult(
            False,
            "web_build_stamp_mismatch",
            f"stamp {stamped[:12]}… != HEAD {expected_sha[:12]}…; rebuild required",
        )
    return CheckResult(True, "web_build_stamp_ok", stamped)


def write_web_build_stamp(sha: str) -> Path:
    dest = Path("/tmp/booker-staging")
    dest.mkdir(parents=True, mode=0o700, exist_ok=True)
    stamp = dest / "web-build.sha"
    stamp.write_text(sha.strip() + "\n", encoding="utf-8")
    try:
        stamp.chmod(0o600)
    except OSError:
        pass
    return stamp


def pid_owned_by_booker_staging(pid: int, expected_tokens: tuple[str, ...] = ("booker", "uvicorn", "next")) -> bool:
    """True only if /proc/<pid>/cmdline looks like our staging app."""
    cmdline_path = f"/proc/{pid}/cmdline"
    try:
        raw = Path(cmdline_path).read_bytes()
    except (OSError, FileNotFoundError):
        return False
    text = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").lower()
    if not text.strip():
        return False
    # Must look like our stack; refuse killing unrelated PIDs from stale pidfiles
    has_stack = any(tok in text for tok in expected_tokens)
    staging_hint = "booker" in text or "staging" in text or "uvicorn" in text or "next-server" in text or "next" in text
    return has_stack and staging_hint


def run_checks(env: dict[str, str]) -> list[CheckResult]:
    results = [
        check_runtime(env.get("BOOKER_RUNTIME_ENV")),
        check_compose_project(env.get("COMPOSE_PROJECT_NAME")),
        check_uploads(env.get("BOOKER_UPLOAD_DIR")),
        check_payment_provider(env.get("BOOKER_PAYMENT_PROVIDER")),
        check_database_url(env.get("BOOKER_DATABASE_URL")),
        check_demo_seed(env.get("BOOKER_ALLOW_DEMO_SEED"), env.get("BOOKER_RUNTIME_ENV")),
    ]
    if "BOOKER_STAGING_PGPASSWORD" in env:
        results.append(check_staging_password_env(env.get("BOOKER_STAGING_PGPASSWORD")))
    env_file = env.get("BOOKER_STAGING_ENV_FILE") or env.get("_PREFLIGHT_ENV_FILE")
    if env_file:
        results.append(check_env_file_path(env_file))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Booker staging fail-closed preflight")
    parser.add_argument("--env-file", help="Optional key=value file (secrets outside git)")
    parser.add_argument("--check-ports", nargs=2, metavar=("API_PORT", "WEB_PORT"), type=int)
    parser.add_argument("--check-web-stamp", metavar="SHA", help="Validate .next against stamp for SHA")
    parser.add_argument("--web-next-dir", default="", help="Path to apps/web/.next")
    parser.add_argument("--redact-file", help="Read file, print secret-redacted content to stdout")
    args = parser.parse_args(argv)

    if args.redact_file:
        path = args.redact_file
        if not os.path.isfile(path):
            print(f"preflight FAIL: redact-file not found: {path}", file=sys.stderr)
            return 2
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        print(redact_secrets(text))
        return 0

    env = dict(os.environ)
    if args.env_file:
        path = args.env_file
        if not os.path.isfile(path) and not os.path.islink(path):
            # Allow missing only after path policy check for production refuse
            abs_probe = os.path.abspath(path)
            if abs_probe.startswith("/opt/booker") or abs_probe.startswith("/etc/booker"):
                print(f"preflight FAIL: refusing production env path {abs_probe}", file=sys.stderr)
                return 2
            print(f"preflight FAIL: env-file not found: {path}", file=sys.stderr)
            return 2
        # Refuse reading obvious production env paths (before read / before follow)
        env_check = check_env_file_path(path)
        if not env_check.ok:
            print(f"preflight FAIL [{env_check.code}] {env_check.detail}", file=sys.stderr)
            return 2
        if not os.path.isfile(path):
            print(f"preflight FAIL: env-file not found: {path}", file=sys.stderr)
            return 2
        env["_PREFLIGHT_ENV_FILE"] = os.path.abspath(path)
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")

    results = run_checks(env)

    if args.check_ports:
        api_port, web_port = args.check_ports
        results.append(check_port_available("127.0.0.1", api_port))
        results.append(check_port_available("127.0.0.1", web_port))

    if args.check_web_stamp:
        next_dir = args.web_next_dir or os.path.join(
            os.path.dirname(__file__), "..", "apps", "web", ".next"
        )
        results.append(check_web_build_stamp(os.path.abspath(next_dir), args.check_web_stamp))

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
