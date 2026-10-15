"""Negative and positive tests for staging fail-closed preflight."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "infra"))

from staging_preflight import (  # noqa: E402
    check_database_url,
    check_env_file_path,
    check_port_available,
    check_runtime,
    check_uploads,
    check_web_build_stamp,
    pid_owned_by_booker_staging,
    redact_secrets,
    run_checks,
    write_web_build_stamp,
)


def _ok_env(**overrides: str) -> dict[str, str]:
    base = {
        "BOOKER_RUNTIME_ENV": "test",
        "COMPOSE_PROJECT_NAME": "booker-staging",
        "BOOKER_UPLOAD_DIR": "/tmp/booker-staging-uploads",
        "BOOKER_PAYMENT_PROVIDER": "stub",
        "BOOKER_ALLOW_DEMO_SEED": "1",
        "BOOKER_DATABASE_URL": (
            "postgresql+psycopg://booker_staging:secret@127.0.0.1:15432/booker_staging"
        ),
    }
    base.update(overrides)
    return base


def test_preflight_passes_isolated_staging_url():
    results = run_checks(_ok_env())
    assert all(r.ok for r in results), results


@pytest.mark.parametrize(
    "url,code",
    [
        ("postgresql+psycopg://booker:booker@5.45.112.180:5432/booker", "database_production_host"),
        ("postgresql+psycopg://u:p@bukergo.ru:5432/booker", "database_production_host"),
        ("sqlite:////opt/booker/data/booker.db", "database_production_path"),
        ("postgresql+psycopg://booker:booker@127.0.0.1:5432/booker", "pg_port_forbidden"),
        ("postgresql+psycopg://booker:x@127.0.0.1:15432/booker", "pg_db_name_forbidden"),
        ("postgresql+psycopg://root:x@127.0.0.1:15432/booker_staging", "pg_user_forbidden"),
        ("postgresql+psycopg://booker_staging:x@10.0.0.5:15432/booker_staging", "pg_host_not_loopback"),
    ],
)
def test_preflight_rejects_production_shaped_urls(url: str, code: str):
    result = check_database_url(url)
    assert not result.ok
    assert result.code == code


def test_preflight_rejects_production_runtime():
    result = check_runtime("production")
    assert not result.ok
    assert result.code == "runtime_production"


def test_preflight_rejects_opt_booker_uploads():
    result = check_uploads("/opt/booker/data/uploads")
    assert not result.ok


def test_preflight_rejects_wrong_compose_project():
    results = run_checks(_ok_env(COMPOSE_PROJECT_NAME="booker"))
    assert any(not r.ok and r.code == "compose_project_mismatch" for r in results)


def test_preflight_allows_isolated_sqlite():
    result = check_database_url("sqlite:////tmp/booker-staging/booker.db")
    assert result.ok, result


def test_cli_main_exit_codes(tmp_path):
    from staging_preflight import main

    good = tmp_path / "secrets.env"
    good.write_text(
        "\n".join(
            [
                "BOOKER_RUNTIME_ENV=test",
                "COMPOSE_PROJECT_NAME=booker-staging",
                "BOOKER_UPLOAD_DIR=/tmp/booker-staging-uploads",
                "BOOKER_PAYMENT_PROVIDER=stub",
                "BOOKER_ALLOW_DEMO_SEED=1",
                "BOOKER_DATABASE_URL=postgresql+psycopg://booker_staging:s@127.0.0.1:15432/booker_staging",
            ]
        ),
        encoding="utf-8",
    )
    assert main(["--env-file", str(good)]) == 0

    bad = tmp_path / "bad.env"
    bad.write_text(
        "BOOKER_RUNTIME_ENV=production\n"
        "COMPOSE_PROJECT_NAME=booker-staging\n"
        "BOOKER_UPLOAD_DIR=/tmp/booker-staging-uploads\n"
        "BOOKER_PAYMENT_PROVIDER=stub\n"
        "BOOKER_ALLOW_DEMO_SEED=1\n"
        "BOOKER_DATABASE_URL=postgresql+psycopg://booker_staging:s@127.0.0.1:15432/booker_staging\n",
        encoding="utf-8",
    )
    assert main(["--env-file", str(bad)]) == 2

    # Refuse reading /opt/booker env even if file existed — path check before read
    assert main(["--env-file", "/opt/booker/data/fake.env"]) == 2


def test_env_file_path_rejects_production():
    result = check_env_file_path("/opt/booker/data/booker-api.env")
    assert not result.ok
    assert result.code == "env_file_production"


def test_env_file_path_allows_tmp(tmp_path):
    path = tmp_path / "secrets.env"
    path.write_text("x=1\n", encoding="utf-8")
    result = check_env_file_path(str(path))
    assert result.ok, result


def test_uploads_symlink_escape(tmp_path):
    staging = Path("/tmp/booker-staging-symlink-test")
    staging.mkdir(parents=True, exist_ok=True)
    link = staging / "escape"
    target = tmp_path / "opt-booker-lookalike"
    # Simulate escape toward /opt/booker via symlink when possible
    forbidden = Path("/opt/booker")
    if forbidden.exists() or os.geteuid() == 0:
        pytest.skip("cannot safely create /opt/booker symlink fixture")
    # Use a path that resolves outside allowlist
    outside = tmp_path / "outside-uploads"
    outside.mkdir()
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(outside)
    result = check_uploads(str(link))
    assert not result.ok
    assert result.code == "uploads_symlink_escape"
    link.unlink()
    try:
        staging.rmdir()
    except OSError:
        pass


def test_redact_secrets_masks_password_and_url():
    sample = (
        "services:\n"
        "  postgres:\n"
        "    environment:\n"
        "      POSTGRES_PASSWORD: supersecret99\n"
        "    image: postgres\n"
        "DATABASE_URL: postgresql://booker_staging:supersecret99@127.0.0.1:15432/booker_staging\n"
    )
    redacted = redact_secrets(sample, extra_values=["supersecret99"])
    assert "supersecret99" not in redacted
    assert "***" in redacted
    assert "15432" in redacted


def test_port_available_detects_conflict():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        result = check_port_available("127.0.0.1", port)
        assert not result.ok
        assert result.code == "port_in_use"
    finally:
        sock.close()
    free = check_port_available("127.0.0.1", port)
    assert free.code in {"port_ok", "port_in_use"}


def test_web_build_stamp_refuse_unknown(tmp_path, monkeypatch):
    next_dir = tmp_path / ".next"
    next_dir.mkdir()
    stamp_dir = Path("/tmp/booker-staging")
    stamp_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp_dir / "web-build.sha"
    if stamp.exists():
        stamp.unlink()
    result = check_web_build_stamp(str(next_dir), "abc123deadbeef")
    assert not result.ok
    assert result.code == "web_build_stamp_missing"

    write_web_build_stamp("abc123deadbeef")
    ok = check_web_build_stamp(str(next_dir), "abc123deadbeef")
    assert ok.ok, ok

    mismatch = check_web_build_stamp(str(next_dir), "ffffffffffffffff")
    assert not mismatch.ok
    assert mismatch.code == "web_build_stamp_mismatch"


def test_pid_ownership_rejects_missing_and_self():
    assert pid_owned_by_booker_staging(0) is False
    # Current pytest process is not a booker staging app
    assert pid_owned_by_booker_staging(os.getpid()) is False


def test_cli_redact_file(tmp_path):
    from staging_preflight import main

    raw = tmp_path / "compose.yml"
    raw.write_text("POSTGRES_PASSWORD: hunter2secret\nport: 15432\n", encoding="utf-8")
    assert main(["--redact-file", str(raw)]) == 0
