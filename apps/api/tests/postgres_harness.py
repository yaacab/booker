"""Guarded, per-run PostgreSQL schema for destructive migration/concurrency tests."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url


def validate_test_postgres_dsn(dsn: str) -> URL:
    """Refuse remote, ambiguous, or non-test DSNs before any connection is opened."""
    if not dsn:
        raise ValueError("TEST_POSTGRES_DSN is empty")
    try:
        url = make_url(dsn)
    except Exception as exc:
        raise ValueError("TEST_POSTGRES_DSN is malformed") from exc
    if url.drivername != "postgresql+psycopg":
        raise ValueError("TEST_POSTGRES_DSN must use postgresql+psycopg")
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("TEST_POSTGRES_DSN must point to loopback")
    if not url.database or "test" not in url.database.lower():
        raise ValueError("TEST_POSTGRES_DSN database name must contain 'test'")
    if url.query:
        raise ValueError("TEST_POSTGRES_DSN query parameters are not allowed")
    return url


@contextmanager
def isolated_postgres_schema(dsn: str) -> Iterator[tuple[Engine, Config, str]]:
    """Create and remove only this invocation's unique schema."""
    url = validate_test_postgres_dsn(dsn)
    schema = f"booker_it_{uuid.uuid4().hex}"
    admin_engine = create_engine(url, future=True)
    scoped_engine = None
    created = False
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        scoped_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
        scoped_engine = create_engine(scoped_url, future=True)
        with scoped_engine.connect() as connection:
            actual = connection.execute(text("SELECT current_schema()")).scalar_one()
            if actual != schema:
                raise RuntimeError("PostgreSQL search_path did not select isolated schema")
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url", scoped_url.render_as_string(hide_password=False).replace("%", "%%")
        )
        yield scoped_engine, config, schema
    finally:
        if scoped_engine is not None:
            scoped_engine.dispose()
        try:
            if created:
                with admin_engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            admin_engine.dispose()
