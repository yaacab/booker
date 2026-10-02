from typing import ClassVar

from booker_api.config import settings
from booker_api.rate_limit import RateLimiter, client_key


def test_client_key_ignores_spoofed_forwarded_for():
    class FakeClient:
        host = "10.0.0.1"

    class FakeRequest:
        headers: ClassVar[dict[str, str]] = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
        client = FakeClient()

    assert client_key(FakeRequest(), "login") == "login:10.0.0.1"


def test_client_key_prefers_x_real_ip_only_from_configured_proxy(monkeypatch):
    class FakeClient:
        host = "10.0.0.1"

    class FakeRequest:
        headers: ClassVar[dict[str, str]] = {
            "x-real-ip": "198.51.100.10",
            "x-forwarded-for": "203.0.113.5, 10.0.0.1",
        }
        client = FakeClient()

    assert client_key(FakeRequest(), "login") == "login:10.0.0.1"
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "10.0.0.0/8")
    assert client_key(FakeRequest(), "login") == "login:198.51.100.10"


def test_client_key_rejects_spoofed_real_ip_from_direct_peer():
    class FakeClient:
        host = "203.0.113.9"

    class FakeRequest:
        headers: ClassVar[dict[str, str]] = {"x-real-ip": "198.51.100.10"}
        client = FakeClient()

    assert client_key(FakeRequest(), "login") == "login:203.0.113.9"


def test_rate_limiter_evicts_stale_keys():
    limiter = RateLimiter(max_requests=5, window_seconds=60, max_keys=2)
    limiter.check("a:1.1.1.1")
    limiter.check("b:2.2.2.2")
    limiter.check("c:3.3.3.3")
    assert len(limiter._hits) <= 2
