import hashlib
import hmac

from booker_api.config import settings
from tests.conftest import auth_header, register
from tests.test_offers import ack_both, setup_negotiation


def _sign(event_id: str, payment_id: str, status: str) -> str:
    payload = f"{event_id}:{payment_id}:{status}"
    return hmac.new(settings.webhook_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _awaiting_payment(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    assert (
        client.post(
            f"/bookings/{ctx['booking_id']}/hold",
            headers=auth_header(ctx["customer"]["token"]),
        ).status_code
        == 200
    )
    contract = client.post(
        f"/bookings/{ctx['booking_id']}/contract",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    for side, token in (
        ("customer", ctx["customer"]["token"]),
        ("supplier", ctx["owner"]["token"]),
    ):
        signed = client.post(
            f"/contracts/{contract['id']}/sign",
            json={"side": side, "otp": contract[f"otp_{side}"]},
            headers=auth_header(token),
        )
        assert signed.status_code == 200, signed.text
    assert signed.json()["booking_status"] == "AwaitingPayment"
    pay = client.post(
        f"/bookings/{ctx['booking_id']}/payments",
        json={"idempotency_key": "pay-1"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert pay.status_code == 200
    replay = client.post(
        f"/bookings/{ctx['booking_id']}/payments",
        json={"idempotency_key": "pay-1"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert replay.json()["idempotent"] is True
    ctx["payment_id"] = pay.json()["id"]
    return ctx


def test_failed_webhook_does_not_confirm(client):
    ctx = _awaiting_payment(client)
    res = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-fail",
            "payment_id": ctx["payment_id"],
            "status": "failed",
            "signature": _sign("evt-fail", ctx["payment_id"], "failed"),
        },
    )
    assert res.status_code == 200
    assert res.json()["booking_status"] == "AwaitingPayment"
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["status"] == "AwaitingPayment"


def test_webhook_idempotent_and_confirms_once(client):
    ctx = _awaiting_payment(client)
    payload = {
        "event_id": "evt-ok",
        "payment_id": ctx["payment_id"],
        "status": "succeeded",
        "signature": _sign("evt-ok", ctx["payment_id"], "succeeded"),
    }
    first = client.post("/payments/webhook", json=payload)
    second = client.post("/payments/webhook", json=payload)
    assert first.status_code == 200
    assert first.json()["booking_status"] == "Confirmed"
    assert second.json() == first.json()
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["status"] == "Confirmed"
    assert room["tabs"] == ["chat", "terms", "documents", "payments", "dispute"]
    assert room["event_id"]
    assert "documents" in room
    assert any(d["kind"] == "offer" for d in room["documents"])
    assert any(d["kind"] == "contract" for d in room["documents"])


def test_stub_complete_confirms(client):
    ctx = _awaiting_payment(client)
    res = client.post(
        f"/payments/{ctx['payment_id']}/stub-complete",
        json={"status": "succeeded"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert res.status_code == 200
    assert res.json()["booking_status"] == "Confirmed"


def test_stub_complete_forbidden_for_outsider(client):
    ctx = _awaiting_payment(client)
    outsider = register(client, "outsider@booker.test", "Outsider")
    res = client.post(
        f"/payments/{ctx['payment_id']}/stub-complete",
        json={"status": "succeeded"},
        headers=auth_header(outsider["token"]),
    )
    assert res.status_code == 403
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["status"] == "AwaitingPayment"


def test_webhook_rejected_when_default_secret_disallowed(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_default_webhook_secret", False)
    ctx = _awaiting_payment(client)
    res = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-guard",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-guard", ctx["payment_id"], "succeeded"),
        },
    )
    assert res.status_code == 503
