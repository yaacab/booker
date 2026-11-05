"""PII-free HTTP signals for the local operations checker."""

import json
import logging
import re
import sys
import time

logger = logging.getLogger("booker.ops.http")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False
PREFIX = "BOOKER_HTTP_METRIC "
_ROUTE = re.compile(r"^/[A-Za-z0-9_{}./-]{0,159}$")


def metric_line(scope: dict, status_code: int, elapsed_ms: int) -> str:
    route = getattr(scope.get("route"), "path", None)
    if not isinstance(route, str) or not _ROUTE.fullmatch(route):
        route = "unmatched"
    method = scope.get("method", "OTHER")
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        method = "OTHER"
    return PREFIX + json.dumps(
        {
            "route": route,
            "method": method,
            "status": max(100, min(int(status_code), 599)),
            "latency_ms": max(0, min(int(elapsed_ms), 3_600_000)),
        },
        separators=(",", ":"),
        sort_keys=True,
    )


class OpsHttpMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        status_code = 500

        async def send_observed(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_observed)
        finally:
            try:
                logger.info(metric_line(scope, status_code, int((time.monotonic() - started) * 1000)))
            except Exception:  # noqa: BLE001, S110
                # Monitoring must never change the business response.
                pass
