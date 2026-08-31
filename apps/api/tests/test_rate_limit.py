import hashlib
import hmac

from fastapi import HTTPException

from booker_api.config import settings
from booker_api.rate_limit import (
    RateLimiter,
    auth_limiter,
    client_key,
    upload_limiter,
    webhook_limiter,
)


def test_rate_limiter_blocks_after_max():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    limiter.check("k")
    limiter.check("k")
    try:
        limiter.check("k")
        assert False, "expected 429"
    except HTTPException as exc:
        assert exc.status_code == 429
        assert "Слишком много" in exc.detail


from typing import ClassVar


def test_client_key_prefers_forwarded_for():
    class FakeClient:
        host = "10.0.0.1"

    class FakeRequest:
        headers: ClassVar[dict[str, str]] = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
        client = FakeClient()

    assert client_key(FakeRequest(), "login") == "login:203.0.113.5"


def test_login_rate_limit(client):
    auth_limiter.reset()
    original = auth_limiter.max_requests
    auth_limiter.max_requests = 2
    try:
        for _ in range(2):
            client.post("/auth/login", json={"email": "nobody@booker.test", "password": "wrong"})
        blocked = client.post("/auth/login", json={"email": "nobody@booker.test", "password": "wrong"})
        assert blocked.status_code == 429
    finally:
        auth_limiter.max_requests = original
        auth_limiter.reset()


def test_webhook_rate_limit(client):
    webhook_limiter.reset()
    original = webhook_limiter.max_requests
    webhook_limiter.max_requests = 2
    payload_base = "evt:pay:failed"
    sig = hmac.new(settings.webhook_secret.encode(), payload_base.encode(), hashlib.sha256).hexdigest()
    body = {"event_id": "evt", "payment_id": "pay", "status": "failed", "signature": sig}
    try:
        for _ in range(2):
            client.post("/payments/webhook", json=body)
        blocked = client.post("/payments/webhook", json=body)
        assert blocked.status_code == 429
    finally:
        webhook_limiter.max_requests = original
        webhook_limiter.reset()


MINIMAL_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


def test_upload_rate_limit(client, tmp_path, monkeypatch):
    from booker_api.config import settings
    from tests.test_payments import _awaiting_payment

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    upload_limiter.reset()
    original = upload_limiter.max_requests
    upload_limiter.max_requests = 2
    ctx = _awaiting_payment(client)
    booking_id = ctx["booking_id"]
    customer = ctx["customer"]
    files = {"file": ("brief.pdf", MINIMAL_PDF, "application/pdf")}
    headers = {"Authorization": f"Bearer {customer['token']}"}
    try:
        for _ in range(2):
            res = client.post(
                f"/bookings/{booking_id}/attachments",
                files=files,
                headers=headers,
            )
            assert res.status_code == 200, res.text
        blocked = client.post(
            f"/bookings/{booking_id}/attachments",
            files=files,
            headers=headers,
        )
        assert blocked.status_code == 429
    finally:
        upload_limiter.max_requests = original
        upload_limiter.reset()
