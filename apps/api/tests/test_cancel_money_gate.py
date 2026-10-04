"""Automatic cancellation must preserve the slot while money needs review."""

from booker_api.models import AvailabilitySlot, Booking, Payment
from tests.conftest import auth_header
from tests.test_payments import _awaiting_payment, _sign


def _assert_unchanged(client, ctx, expected_payment_status: str) -> None:
    with client.app.state.SessionLocal() as db:
        booking = db.get(Booking, ctx["booking_id"])
        slot = db.get(AvailabilitySlot, ctx["slot"]["id"])
        payment = db.get(Payment, ctx["payment_id"])
        assert booking is not None
        assert slot is not None
        assert payment is not None
        assert booking.status != "Cancelled"
        assert slot.status in {"held", "confirmed"}
        assert payment.status == expected_payment_status


def test_pending_payment_blocks_automatic_cancellation_without_releasing_slot(client):
    ctx = _awaiting_payment(client)
    response = client.post(
        f"/bookings/{ctx['booking_id']}/cancel",
        json={"reason": "Заказчик передумал"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert response.status_code == 409
    assert "проверки расчётов" in response.json()["detail"]
    _assert_unchanged(client, ctx, "pending")
    completed = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-after-rejected-cancel",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign(
                "evt-after-rejected-cancel", ctx["payment_id"], "succeeded"
            ),
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["booking_status"] == "Confirmed"
    _assert_unchanged(client, ctx, "succeeded")


def test_captured_payment_blocks_automatic_cancellation_without_releasing_slot(client):
    ctx = _awaiting_payment(client)
    completed = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-cancel-money",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-cancel-money", ctx["payment_id"], "succeeded"),
        },
    )
    assert completed.status_code == 200, completed.text
    response = client.post(
        f"/bookings/{ctx['booking_id']}/cancel",
        json={"reason": "Заказчик передумал"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert response.status_code == 409
    _assert_unchanged(client, ctx, "succeeded")


def test_failed_payment_allows_cancellation(client):
    ctx = _awaiting_payment(client)
    failed = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-cancel-failed",
            "payment_id": ctx["payment_id"],
            "status": "failed",
            "signature": _sign("evt-cancel-failed", ctx["payment_id"], "failed"),
        },
    )
    assert failed.status_code == 200, failed.text
    cancelled = client.post(
        f"/bookings/{ctx['booking_id']}/cancel",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "Cancelled"
