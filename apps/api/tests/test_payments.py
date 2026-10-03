import hashlib
import hmac

from booker_api.config import settings
from booker_api.models import Booking, MoneyMovement, Payment, PaymentWebhookEvent
from booker_api.security import now
from tests.conftest import auth_header, contract_otps, register
from tests.test_offers import ack_both, setup_negotiation


def _sign(event_id: str, payment_id: str, status: str) -> str:
    payload = f"{event_id}:{payment_id}:{status}"
    return hmac.new(settings.webhook_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _awaiting_payment(client, offer_overrides=None, before_contract=None):
    ctx = setup_negotiation(client, offer_overrides)
    ack_both(client, ctx)
    if before_contract is not None:
        before_contract(client, ctx)
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
    assert contract.get("otp_delivered") is True
    otps = contract_otps(client.app.state.SessionLocal, contract["id"])
    for side, token in (
        ("customer", ctx["customer"]["token"]),
        ("supplier", ctx["owner"]["token"]),
    ):
        signed = client.post(
            f"/contracts/{contract['id']}/sign",
            json={"side": side, "otp": otps[f"otp_{side}"], "body_hash": contract["body_sha256"]},
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


def test_payment_rejects_missing_accepted_quote_even_with_signed_contract(client):
    ctx = _awaiting_payment(client)
    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        booking.accepted_offer_version_id = None
        db.commit()
    finally:
        db.close()
    response = client.post(
        f"/bookings/{ctx['booking_id']}/payments",
        json={"idempotency_key": "new-payment-without-accepted-quote"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert response.status_code == 409


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
    with client.app.state.SessionLocal() as db:
        assert db.query(MoneyMovement).filter_by(payment_id=ctx["payment_id"]).count() == 0


def test_only_advance_confirms_booking_and_later_obligations_stay_separate(client):
    ctx = _awaiting_payment(
        client,
        {"advance_rub": 40000, "security_deposit_rub": 15000},
    )
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["payment"]["amount_rub"] == 40000
    advance = next(row for row in room["payment_obligations"] if row["kind"] == "advance")
    balance = next(row for row in room["payment_obligations"] if row["kind"] == "balance")
    assert room["payment"]["obligation_id"] == advance["id"]
    conflicting_replay = client.post(
        f"/bookings/{ctx['booking_id']}/payments",
        json={"idempotency_key": "pay-1", "obligation_id": balance["id"]},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert conflicting_replay.status_code == 409
    duplicate_advance = client.post(
        f"/bookings/{ctx['booking_id']}/payments",
        json={"idempotency_key": "pay-advance-again", "obligation_id": advance["id"]},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert duplicate_advance.status_code == 409
    early_balance = client.post(
        f"/bookings/{ctx['booking_id']}/payments",
        json={"idempotency_key": "pay-balance-too-early", "obligation_id": balance["id"]},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert early_balance.status_code == 409

    completed = client.post(
        f"/payments/{ctx['payment_id']}/stub-complete",
        json={"status": "succeeded"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert completed.status_code == 200
    assert completed.json()["booking_status"] == "Confirmed"
    assert completed.json()["obligation_status"] == "satisfied"

    balance_payment = client.post(
        f"/bookings/{ctx['booking_id']}/payments",
        json={"idempotency_key": "pay-balance", "obligation_id": balance["id"]},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert balance_payment.status_code == 200, balance_payment.text
    assert balance_payment.json()["amount_rub"] == 60000
    assert balance_payment.json()["obligation_kind"] == "balance"
    second = client.post(
        f"/payments/{balance_payment.json()['id']}/stub-complete",
        json={"status": "succeeded"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert second.status_code == 200
    assert second.json()["booking_status"] == "Confirmed"
    refreshed = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert len(refreshed["payments"]) == 2
    assert next(
        row for row in refreshed["payment_obligations"] if row["kind"] == "balance"
    )["status"] == "satisfied"


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
    with client.app.state.SessionLocal() as db:
        movements = db.query(MoneyMovement).filter_by(payment_id=ctx["payment_id"]).all()
        assert len(movements) == 1
        assert movements[0].kind == "capture"
        assert movements[0].direction == "credit"
        assert movements[0].amount_rub == room["payment"]["amount_rub"]
        assert movements[0].source_id == "evt-ok"


def test_webhook_rejects_forged_signature_without_payment_side_effects(client, SessionLocal):
    ctx = _awaiting_payment(client)
    with SessionLocal() as db:
        prior_payment = db.get(Payment, ctx["payment_id"]).status
        prior_booking = db.get(Booking, ctx["booking_id"]).status
    denied = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-forged",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": "0" * 64,
        },
    )
    assert denied.status_code == 401, denied.text
    with SessionLocal() as db:
        assert db.get(Payment, ctx["payment_id"]).status == prior_payment
        assert db.get(Booking, ctx["booking_id"]).status == prior_booking
        assert db.query(PaymentWebhookEvent).filter_by(event_id="evt-forged").count() == 0
        assert db.query(MoneyMovement).filter_by(payment_id=ctx["payment_id"]).count() == 0


def test_webhook_terminal_state_is_monotonic_across_event_ids(client):
    ctx = _awaiting_payment(client)
    succeeded = {
        "event_id": "evt-terminal-success",
        "payment_id": ctx["payment_id"],
        "status": "succeeded",
        "signature": _sign("evt-terminal-success", ctx["payment_id"], "succeeded"),
    }
    assert client.post("/payments/webhook", json=succeeded).status_code == 200
    second_success = {
        "event_id": "evt-terminal-success-duplicate",
        "payment_id": ctx["payment_id"],
        "status": "succeeded",
        "signature": _sign(
            "evt-terminal-success-duplicate", ctx["payment_id"], "succeeded"
        ),
    }
    duplicate = client.post("/payments/webhook", json=second_success)
    assert duplicate.status_code == 200
    assert duplicate.json()["ignored_terminal_event"] is True
    late_failed = {
        "event_id": "evt-terminal-late-failed",
        "payment_id": ctx["payment_id"],
        "status": "failed",
        "signature": _sign("evt-terminal-late-failed", ctx["payment_id"], "failed"),
    }
    ignored = client.post("/payments/webhook", json=late_failed)
    assert ignored.status_code == 200
    assert ignored.json()["payment_status"] == "succeeded"
    assert ignored.json()["booking_status"] == "Confirmed"
    with client.app.state.SessionLocal() as db:
        assert db.query(MoneyMovement).filter_by(payment_id=ctx["payment_id"]).count() == 1


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


def test_outsider_cannot_create_or_replay_payment(client):
    ctx = _awaiting_payment(client)
    outsider = register(client, "payment-outsider@booker.test", "Outsider")
    for key in ("new-outsider-key", "pay-1"):
        response = client.post(
            f"/bookings/{ctx['booking_id']}/payments",
            json={"idempotency_key": key},
            headers=auth_header(outsider["token"]),
        )
        assert response.status_code == 403
        assert ctx["payment_id"] not in response.text


def test_viewer_and_platform_admin_cannot_pay_for_customer(client):
    from booker_api.models import User

    ctx = _awaiting_payment(client)
    viewer = register(client, "payment-viewer@booker.test", "Viewer")
    added = client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert added.status_code == 200
    admin = register(client, "payment-admin@booker.test", "Platform Admin")
    with client.app.state.SessionLocal() as db:
        admin_row = db.get(User, admin["user_id"])
        admin_row.email_verified_at = now()
        admin_row.is_platform_admin = True
        db.commit()
    for token in (viewer["token"], admin["token"]):
        response = client.post(
            f"/bookings/{ctx['booking_id']}/payments",
            json={"idempotency_key": "pay-1"},
            headers=auth_header(token),
        )
        assert response.status_code == 403
        assert ctx["payment_id"] not in response.text


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
