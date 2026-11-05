#!/usr/bin/env python3
"""LOCAL catalog bench harness for T09/P07 prep.

Ephemeral in-memory SQLite + TestClient (same pattern as API tests).
Does **not** claim staging p95. Prints JSON summary to stdout.

Usage:
  cd apps/api && .venv/bin/python ../../infra/catalog_bench_local.py --profiles 24
  # or from repo root:
  apps/api/.venv/bin/python infra/catalog_bench_local.py --profiles 24
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)
os.environ.setdefault("BOOKER_RUNTIME_ENV", "test")
os.environ.setdefault("BOOKER_PAYMENT_PROVIDER", "stub")


def main() -> int:
    parser = argparse.ArgumentParser(description="Booker LOCAL catalog bench")
    parser.add_argument("--profiles", type=int, default=24, help="Published artists to seed")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--city", default="Москва")
    args = parser.parse_args()

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from fastapi.testclient import TestClient

    from booker_api.db import Base, enable_sqlite_foreign_keys, ensure_sqlite_columns, get_db
    from booker_api.legal_registry import seed_draft_versions
    from booker_api.main import app
    from booker_api.rate_limit import webhook_limiter, auth_limiter

    eng = enable_sqlite_foreign_keys(
        create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
    )
    Base.metadata.create_all(bind=eng)
    ensure_sqlite_columns(eng)
    SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        seed_draft_versions(db)
        db.commit()

    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    auth_limiter.reset()
    webhook_limiter.reset()

    sql_count = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        sql_count["n"] += 1

    event.listen(eng, "before_cursor_execute", _count)

    client = TestClient(app)
    assert client.get("/health").status_code == 200

    seed_mode = "none"
    try:
        from tests.test_catalog_search_pagination import _seed_artists

        published_ids = set(range(args.profiles))
        _seed_artists(client, SessionLocal, args.profiles, published=published_ids)
        seed_mode = "test_catalog_search_pagination._seed_artists"
    except Exception as exc:  # noqa: BLE001
        seed_mode = f"unavailable:{exc.__class__.__name__}:{exc}"

    latencies_ms: list[float] = []
    sql_per_round: list[int] = []
    last_status = None
    last_body_keys: list[str] = []
    item_count = 0

    for _ in range(args.rounds):
        sql_count["n"] = 0
        t0 = time.perf_counter()
        res = client.get(
            "/catalog/search-page",
            params={"city": args.city, "limit": min(24, max(args.profiles, 1))},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        last_status = res.status_code
        latencies_ms.append(elapsed_ms)
        sql_per_round.append(sql_count["n"])
        if res.status_code == 200:
            body = res.json()
            last_body_keys = sorted(body.keys())
            item_count = len(body.get("items") or []) + len(body.get("venues") or [])

    app.dependency_overrides.clear()

    summary = {
        "level": "LOCAL",
        "claim_staging_p95": False,
        "seed_mode": seed_mode,
        "profiles_requested": args.profiles,
        "items_last_page": item_count,
        "rounds": args.rounds,
        "http_status_last": last_status,
        "response_keys": last_body_keys,
        "latency_ms": {
            "samples": [round(x, 2) for x in latencies_ms],
            "median": round(statistics.median(latencies_ms), 2) if latencies_ms else None,
            "mean": round(statistics.mean(latencies_ms), 2) if latencies_ms else None,
        },
        "sql_statements": {
            "samples": sql_per_round,
            "median": int(statistics.median(sql_per_round)) if sql_per_round else None,
        },
        "index_proposals": [
            "artists(city, category, id) — verify EXPLAIN on PG before migration",
            "venues(city, id)",
            "availability_slots(resource_type, resource_id, starts_at) — only if ANALYZE wins",
        ],
        "still_required_for_T09": [
            "staging supply p50/p95",
            "EXPLAIN on factual engine",
            "mobile image HAR",
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if last_status == 200 else 2


if __name__ == "__main__":
    raise SystemExit(main())
