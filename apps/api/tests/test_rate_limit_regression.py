from typing import ClassVar

from booker_api.rate_limit import RateLimiter, client_key


def test_client_key_ignores_spoofed_forwarded_for():
    class FakeClient:
        host = "10.0.0.1"

    class FakeRequest:
        headers: ClassVar[dict[str, str]] = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
        client = FakeClient()

    assert client_key(FakeRequest(), "login") == "login:10.0.0.1"


def test_client_key_prefers_x_real_ip():
    class FakeClient:
        host = "10.0.0.1"

    class FakeRequest:
        headers: ClassVar[dict[str, str]] = {
            "x-real-ip": "198.51.100.10",
            "x-forwarded-for": "203.0.113.5, 10.0.0.1",
        }
        client = FakeClient()

    assert client_key(FakeRequest(), "login") == "login:198.51.100.10"


def test_rate_limiter_evicts_stale_keys():
    limiter = RateLimiter(max_requests=5, window_seconds=60, max_keys=2)
    limiter.check("a:1.1.1.1")
    limiter.check("b:2.2.2.2")
    limiter.check("c:3.3.3.3")
    assert len(limiter._hits) <= 2
