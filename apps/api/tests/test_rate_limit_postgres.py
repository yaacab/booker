"""Opt-in real PostgreSQL concurrency check for the shared limiter."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine

from alembic import command
from booker_api.rate_limit import RateLimiter
from tests.postgres_harness import isolated_postgres_schema

pytestmark = pytest.mark.postgres_integration


def test_postgres_two_engines_respect_atomic_limit():
    dsn = os.environ.get("TEST_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN absent: real PostgreSQL limiter not run")
    with isolated_postgres_schema(dsn) as (first_engine, config, _schema):
        command.upgrade(config, "head")
        second_engine = create_engine(first_engine.url)
        try:
            first = RateLimiter(5, 60, database_engine=first_engine)
            second = RateLimiter(5, 60, database_engine=second_engine)

            def attempt(number):
                try:
                    (first if number % 2 else second).check("login:postgres-shared")
                    return 200
                except HTTPException as exc:
                    return exc.status_code

            with ThreadPoolExecutor(max_workers=12) as pool:
                statuses = list(pool.map(attempt, range(16)))
            assert statuses.count(200) == 5
            assert statuses.count(429) == 11
        finally:
            second_engine.dispose()
