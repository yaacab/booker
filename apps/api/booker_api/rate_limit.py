"""Shared abuse limits. Production uses atomic database counters, not worker memory."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import threading
import time
from collections import defaultdict
from functools import lru_cache

from fastapi import HTTPException, Request, status
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from booker_api.config import settings

logger = logging.getLogger(__name__)


def _uses_database() -> bool:
    return settings.rate_limit_backend == "database" or (
        settings.rate_limit_backend == "auto"
        and settings.runtime_env in {"staging", "production"}
    )


def _database_url() -> str:
    if settings.rate_limit_database_url:
        return settings.rate_limit_database_url
    parsed = make_url(settings.database_url)
    if parsed.get_backend_name() == "sqlite":
        if not parsed.database or parsed.database == ":memory:":
            raise RuntimeError("database rate limiting requires a persistent SQLite file")
        # Keep limiter writes outside request transactions on the business SQLite DB.
        return str(parsed.set(database=f"{parsed.database}.rate-limit"))
    return settings.database_url


@lru_cache(maxsize=4)
def _engine_for_url(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        return create_engine(url, connect_args={"timeout": 5, "check_same_thread": False})
    from booker_api.db import engine as business_engine

    if str(business_engine.url) == url:
        return business_engine
    return create_engine(url, pool_pre_ping=True)


def _ensure_table(bind: Engine) -> None:
    with bind.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS rate_limit_counters ("
            "bucket_key VARCHAR(64) PRIMARY KEY, "
            "expires_at BIGINT NOT NULL, hits INTEGER NOT NULL)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_rate_limit_counters_expires_at "
            "ON rate_limit_counters (expires_at)"
        ))


def initialize_rate_limit_store() -> None:
    """Fail startup if the shared counter store cannot be prepared."""
    if _uses_database():
        _ensure_table(_engine_for_url(_database_url()))


class RateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        max_keys: int | None = None,
        *,
        database_engine: Engine | None = None,
        fail_closed: bool = True,
    ) -> None:
        if max_requests < 1 or window_seconds < 1:
            raise ValueError("rate limit and window must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys or settings.rate_limit_max_keys
        self.database_engine = database_engine
        self.fail_closed = fail_closed
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._cleanup_tick = 0

    def _prune(self, now: float, window_start: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= window_start]
        for key in stale:
            del self._hits[key]
        overflow = len(self._hits) - self.max_keys
        if overflow > 0:
            oldest = sorted(self._hits.items(), key=lambda item: item[1][0] if item[1] else now)
            for key, _ in oldest[:overflow]:
                del self._hits[key]

    def _check_memory(self, key: str) -> int | None:
        now = time.monotonic()
        window_start = now - self.window_seconds
        with self._lock:
            self._prune(now, window_start)
            hits = [t for t in self._hits[key] if t > window_start]
            if len(hits) >= self.max_requests:
                return max(1, int(hits[0] + self.window_seconds - now + 0.999))
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > self.max_keys:
                ranked = sorted(self._hits.items(), key=lambda item: item[1][0] if item[1] else now)
                for drop_key, _ in ranked[: len(self._hits) - self.max_keys]:
                    del self._hits[drop_key]
        return None

    def _check_database(self, key: str, bind: Engine) -> int | None:
        if bind.dialect.name not in {"sqlite", "postgresql"}:
            raise RuntimeError("unsupported rate limit database")
        with bind.begin() as conn:
            clock = (
                "SELECT CAST(strftime('%s', 'now') AS INTEGER)"
                if bind.dialect.name == "sqlite"
                else "SELECT CAST(FLOOR(EXTRACT(EPOCH FROM clock_timestamp())) AS BIGINT)"
            )
            epoch = int(conn.execute(text(clock)).scalar_one())
            bucket = epoch // self.window_seconds
            expires_at = (bucket + 1) * self.window_seconds
            digest = hmac.new(
                settings.webhook_secret.encode(),
                f"{key}\0{self.window_seconds}\0{bucket}".encode(),
                hashlib.sha256,
            ).hexdigest()
            result = conn.execute(
                text(
                    "INSERT INTO rate_limit_counters (bucket_key, expires_at, hits) "
                    "VALUES (:bucket_key, :expires_at, 1) "
                    "ON CONFLICT (bucket_key) DO UPDATE SET "
                    "hits = rate_limit_counters.hits + 1 "
                    "WHERE rate_limit_counters.hits < :limit RETURNING hits"
                ),
                {"bucket_key": digest, "expires_at": expires_at, "limit": self.max_requests},
            ).scalar_one_or_none()
            with self._lock:
                self._cleanup_tick = (self._cleanup_tick + 1) % 64
                cleanup = self._cleanup_tick == 0
        if cleanup:
            try:
                with bind.begin() as conn:
                    conn.execute(
                        text(
                            "DELETE FROM rate_limit_counters WHERE bucket_key IN ("
                            "SELECT bucket_key FROM rate_limit_counters WHERE expires_at <= :now "
                            "ORDER BY expires_at LIMIT 256)"
                        ),
                        {"now": epoch},
                    )
            except SQLAlchemyError:
                # Maintenance must not reverse an already committed rate decision.
                logger.warning("rate limit counter cleanup failed")
        if result is None:
            return max(1, expires_at - epoch)
        return None

    def check(self, key: str) -> None:
        if self.database_engine is not None or _uses_database():
            try:
                retry_after = self._check_database(
                    key, self.database_engine or _engine_for_url(_database_url())
                )
            except Exception as exc:
                if self.fail_closed:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "Ограничение запросов временно недоступно.",
                        headers={"Retry-After": "1"},
                    ) from exc
                return
        else:
            retry_after = self._check_memory(key)
        if retry_after is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Слишком много запросов. Попробуйте позже.",
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
        if self.database_engine is not None:
            with self.database_engine.begin() as conn:
                conn.execute(text("DELETE FROM rate_limit_counters"))


def client_key(request: Request, prefix: str) -> str:
    """Trust X-Real-IP only when the direct peer is an approved reverse proxy."""
    peer = request.client.host if request.client and request.client.host else "unknown"
    ip = peer
    try:
        peer_ip = ipaddress.ip_address(peer)
        trusted = any(
            peer_ip in ipaddress.ip_network(cidr.strip(), strict=False)
            for cidr in settings.trusted_proxy_cidrs.split(",") if cidr.strip()
        )
        if trusted:
            real_ip = request.headers.get("x-real-ip", "").strip()
            if real_ip:
                ip = str(ipaddress.ip_address(real_ip))
    except ValueError:
        ip = peer
    return f"{prefix}:{ip}"


auth_limiter = RateLimiter(max_requests=20, window_seconds=300)
webhook_limiter = RateLimiter(max_requests=120, window_seconds=60)
analytics_limiter = RateLimiter(max_requests=120, window_seconds=60, fail_closed=False)
upload_limiter = RateLimiter(max_requests=30, window_seconds=300)
admin_sensitive_limiter = RateLimiter(max_requests=10, window_seconds=300)
otp_limiter = RateLimiter(max_requests=30, window_seconds=300)
messaging_limiter = RateLimiter(max_requests=60, window_seconds=60)
request_creation_limiter = RateLimiter(max_requests=20, window_seconds=3600)
claim_limiter = RateLimiter(max_requests=5, window_seconds=3600)
support_agent_limiter = RateLimiter(max_requests=5, window_seconds=600)
support_creation_limiter = RateLimiter(max_requests=10, window_seconds=3600)
