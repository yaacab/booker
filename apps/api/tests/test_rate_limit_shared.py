import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import get_context

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from booker_api.config import settings
from booker_api.models import User
from booker_api.rate_limit import (
    RateLimiter,
    _engine_for_url,
    _ensure_table,
    auth_limiter,
    initialize_rate_limit_store,
)


def _engines(tmp_path):
    url = f"sqlite:///{tmp_path / 'rate-limit.db'}"
    first = create_engine(url, connect_args={"timeout": 5, "check_same_thread": False})
    second = create_engine(url, connect_args={"timeout": 5, "check_same_thread": False})
    _ensure_table(first)
    return first, second


def _app(limiter):
    app = FastAPI()

    @app.post("/attempt")
    def attempt():
        limiter.check("auth:ip:203.0.113.4")
        return {"ok": True}

    return app


def _process_attempts(url, queue):
    engine = create_engine(url, connect_args={"timeout": 5, "check_same_thread": False})
    limiter = RateLimiter(5, 60, database_engine=engine)
    statuses = []
    for _ in range(8):
        try:
            limiter.check("login:two-processes")
            statuses.append(200)
        except HTTPException as exc:
            statuses.append(exc.status_code)
    queue.put(statuses)
    engine.dispose()


def test_two_app_instances_share_limit_and_restart_does_not_reset(tmp_path):
    first_engine, second_engine = _engines(tmp_path)
    first = RateLimiter(2, 60, database_engine=first_engine)
    second = RateLimiter(2, 60, database_engine=second_engine)
    with TestClient(_app(first)) as app_one, TestClient(_app(second)) as app_two:
        assert app_one.post("/attempt").status_code == 200
        assert app_two.post("/attempt").status_code == 200
        blocked = app_one.post("/attempt")
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
    restarted = RateLimiter(2, 60, database_engine=second_engine)
    with TestClient(_app(restarted)) as app_three:
        assert app_three.post("/attempt").status_code == 429
    with first_engine.connect() as conn:
        stored = conn.execute(text("SELECT bucket_key FROM rate_limit_counters")).scalar_one()
    assert len(stored) == 64
    assert "203.0.113.4" not in stored


def test_production_auto_uses_persistent_sibling_sqlite_store(tmp_path, monkeypatch):
    business = tmp_path / "booker.db"
    monkeypatch.setattr(settings, "runtime_env", "production")
    monkeypatch.setattr(settings, "rate_limit_backend", "auto")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{business}")
    monkeypatch.setattr(settings, "rate_limit_database_url", "")
    initialize_rate_limit_store()
    assert (tmp_path / "booker.db.rate-limit").exists()
    first = RateLimiter(1, 60)
    first.check("login:203.0.113.5")
    try:
        RateLimiter(1, 60).check("login:203.0.113.5")
    except HTTPException as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("production auto mode did not share the counter")
    _engine_for_url.cache_clear()


def test_concurrent_independent_instances_do_not_exceed_limit(tmp_path):
    first_engine, second_engine = _engines(tmp_path)
    first = RateLimiter(5, 60, database_engine=first_engine)
    second = RateLimiter(5, 60, database_engine=second_engine)

    def attempt(number):
        try:
            (first if number % 2 else second).check("login:shared-ip")
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        statuses = list(pool.map(attempt, range(16)))
    assert statuses.count(200) == 5
    assert statuses.count(429) == 11


def test_two_processes_share_counter(tmp_path):
    for engine in _engines(tmp_path):
        engine.dispose()
    url = f"sqlite:///{tmp_path / 'rate-limit.db'}"
    context = get_context("spawn")
    queue = context.Queue()
    processes = [context.Process(target=_process_attempts, args=(url, queue)) for _ in range(2)]
    for process in processes:
        process.start()
    statuses = [status for _ in processes for status in queue.get(timeout=15)]
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0
    assert statuses.count(200) == 5
    assert statuses.count(429) == 11


def test_scopes_expiry_and_retry_after(tmp_path):
    first_engine, _ = _engines(tmp_path)
    limiter = RateLimiter(1, 2, database_engine=first_engine)
    limiter.check("request:u:one:org:one")
    for scope in ("request:u:two:org:one", "request:u:one:org:two", "login:ip:one", "login:ip:two"):
        limiter.check(scope)
    # The fixed two-second bucket may turn between the first and second check.
    # In that case one repeat is valid in the new bucket; the next must block.
    for _ in range(3):
        try:
            limiter.check("request:u:one:org:one")
        except HTTPException as exc:
            assert exc.status_code == 429
            retry_after = int(exc.headers["Retry-After"])
            assert 1 <= retry_after <= 2
            break
    else:
        raise AssertionError("limit did not block")
    time.sleep(retry_after + 0.1)
    limiter.check("request:u:one:org:one")


def test_backend_failure_policy(tmp_path):
    broken = create_engine(f"sqlite:///{tmp_path / 'uninitialized.db'}")
    critical = RateLimiter(1, 60, database_engine=broken)
    try:
        critical.check("admin:ip")
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.headers["Retry-After"] == "1"
    else:
        raise AssertionError("critical operation failed open")
    low_risk = RateLimiter(1, 60, database_engine=broken, fail_closed=False)
    low_risk.check("analytics:ip")


def test_auth_backend_failure_prevents_registration_side_effect(client, SessionLocal, tmp_path):
    pack = client.get("/legal/pack").json()
    broken = create_engine(f"sqlite:///{tmp_path / 'uninitialized-auth.db'}")
    old_engine = auth_limiter.database_engine
    auth_limiter.database_engine = broken
    try:
        response = client.post("/auth/register", json={
            "email": "limit-failure@booker.test",
            "password": "password1",
            "full_name": "Blocked",
            "phone": "+79000000000",
            "accept_offer": True,
            "accept_privacy": True,
            "accept_processing": True,
            "accepted_documents": [
                {k: doc[k] for k in ("key", "version", "content_hash")}
                for doc in pack["documents"] if doc["required"]
            ],
            "draft_test_acknowledgement": True,
        })
        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
    finally:
        auth_limiter.database_engine = old_engine
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == "limit-failure@booker.test").count() == 0


def test_bounded_cleanup_removes_only_expired_buckets(tmp_path):
    engine, _ = _engines(tmp_path)
    limiter = RateLimiter(100, 60, database_engine=engine)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO rate_limit_counters (bucket_key, expires_at, hits) VALUES "
                 "('expired', 1, 1), ('future', 9999999999, 1)")
        )
    for _ in range(64):
        limiter.check("cleanup:scope")
    with engine.connect() as conn:
        keys = set(conn.execute(text("SELECT bucket_key FROM rate_limit_counters")).scalars())
    assert "expired" not in keys
    assert "future" in keys
