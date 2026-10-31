"""In-memory rate limiting for abuse-prone API endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from booker_api.config import settings


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int, max_keys: int | None = None) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys or settings.rate_limit_max_keys
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, now: float, window_start: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= window_start]
        for key in stale:
            del self._hits[key]
        overflow = len(self._hits) - self.max_keys
        if overflow > 0:
            oldest = sorted(self._hits.items(), key=lambda item: item[1][0] if item[1] else now)
            for key, _ in oldest[:overflow]:
                del self._hits[key]

    def check(self, key: str) -> None:
        now = time.monotonic()
        window_start = now - self.window_seconds
        with self._lock:
            self._prune(now, window_start)
            hits = [t for t in self._hits[key] if t > window_start]
            if len(hits) >= self.max_requests:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Слишком много запросов. Попробуйте позже.",
                )
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > self.max_keys:
                ranked = sorted(
                    self._hits.items(),
                    key=lambda item: item[1][0] if item[1] else now,
                )
                for drop_key, _ in ranked[: len(self._hits) - self.max_keys]:
                    del self._hits[drop_key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_key(request: Request, prefix: str) -> str:
    """Derive rate-limit key from trusted direct client IP, not client-supplied X-Forwarded-For."""
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        ip = real_ip
    elif request.client and request.client.host:
        ip = request.client.host
    else:
        ip = "unknown"
    return f"{prefix}:{ip}"


# Auth: 20 attempts / 5 min per IP; webhooks: 120 / min per IP
auth_limiter = RateLimiter(max_requests=20, window_seconds=300)
webhook_limiter = RateLimiter(max_requests=120, window_seconds=60)
analytics_limiter = RateLimiter(max_requests=120, window_seconds=60)
upload_limiter = RateLimiter(max_requests=30, window_seconds=300)
admin_sensitive_limiter = RateLimiter(max_requests=10, window_seconds=300)
messaging_limiter = RateLimiter(max_requests=60, window_seconds=60)
