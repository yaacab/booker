"""In-memory rate limiting for auth and webhook endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        window_start = now - self.window_seconds
        with self._lock:
            hits = [t for t in self._hits[key] if t > window_start]
            if len(hits) >= self.max_requests:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Слишком много запросов. Попробуйте позже.",
                )
            hits.append(now)
            self._hits[key] = hits

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_key(request: Request, prefix: str) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"{prefix}:{ip}"


# Auth: 20 attempts / 5 min per IP; webhooks: 120 / min per IP
auth_limiter = RateLimiter(max_requests=20, window_seconds=300)
webhook_limiter = RateLimiter(max_requests=120, window_seconds=60)
analytics_limiter = RateLimiter(max_requests=120, window_seconds=60)
