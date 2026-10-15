"""Negative and positive tests for staging fail-closed preflight."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "infra"))

from staging_preflight import (  # noqa: E402
    check_database_url,
    check_runtime,
    check_uploads,
    run_checks,
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
