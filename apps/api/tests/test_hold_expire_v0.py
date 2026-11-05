"""V0-SAFE-HOLD-EXPIRE: atomic expiry across exclusive booking states + late payment."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from booker_api.booking_holds import count_stale_exclusive_holds
from booker_api.config import settings
from booker_api.models import (
    AuditLog,
    AvailabilitySlot,
    Booking,
    BookingHold,
    MoneyMovement,
)
from tests.conftest import auth_header, contract_otps
from tests.test_offers import ack_both, setup_negotiation
from tests.test_payments import _awaiting_payment, _sign


def _force_hold_past(client, booking_id: str) -> str:
    db = client.app.state.SessionLocal()
    try:
        hold = (
            db.query(BookingHold)
            .filter(BookingHold.booking_id == booking_id, BookingHold.status == "active")
            .one()
        )
        hold.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        hold_id = hold.id
        db.commit()
        return hold_id
    finally:
        db.close()


def _expire(client):
    res = client.post(
        "/holds/expire",
        headers={"X-Internal-Token": settings.webhook_secret},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _hold_to_awaiting_contract(client):
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
    )
    assert contract.status_code == 200, contract.text
    ctx["contract"] = contract.json()
    return ctx


def test_expire_date_held_cancels_and_opens_slot(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    assert (
        client.post(
            f"/bookings/{ctx['booking_id']}/hold",
            headers=auth_header(ctx["customer"]["token"]),
        ).status_code
        == 200
    )
    _force_hold_past(client, ctx["booking_id"])
    assert _expire(client)["expired"] == 1
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["status"] == "Cancelled"
    artist = client.get(f"/artists/{ctx['artist']['id']}").json()
    assert artist["slots"][0]["status"] == "open"


def test_expire_awaiting_contract_cancels_and_opens_slot(client):
    ctx = _hold_to_awaiting_contract(client)
    _force_hold_past(client, ctx["booking_id"])
    assert _expire(client)["expired"] == 1
    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        assert booking.status == "Cancelled"
        slot = db.get(AvailabilitySlot, booking.slot_id)
        assert slot.status == "open"
        hold = db.query(BookingHold).filter_by(booking_id=booking.id).one()
        assert hold.status == "expired"
    finally:
        db.close()


def test_expire_awaiting_payment_cancels_and_opens_slot(client):
    ctx = _awaiting_payment(client)
    _force_hold_past(client, ctx["booking_id"])
    assert _expire(client)["expired"] == 1
    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        assert booking.status == "Cancelled"
        assert db.get(AvailabilitySlot, booking.slot_id).status == "open"
    finally:
        db.close()


def test_expire_does_not_open_confirmed_slot(client):
    ctx = _awaiting_payment(client)
    payload = {
        "event_id": "evt-confirm-keep-slot",
        "payment_id": ctx["payment_id"],
        "status": "succeeded",
        "signature": _sign("evt-confirm-keep-slot", ctx["payment_id"], "succeeded"),
    }
    assert client.post("/payments/webhook", json=payload).status_code == 200
    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        assert booking.status == "Confirmed"
        slot = db.get(AvailabilitySlot, booking.slot_id)
        assert slot.status == "confirmed"
        # Force a leftover active hold into the past (should not reopen confirmed).
        hold = BookingHold(
            booking_id=booking.id,
            slot_id=slot.id,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            status="active",
        )
        db.add(hold)
        db.commit()
    finally:
        db.close()
    assert _expire(client)["expired"] == 1
    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        assert booking.status == "Confirmed"
        assert db.get(AvailabilitySlot, booking.slot_id).status == "confirmed"
    finally:
        db.close()


def test_confirm_with_active_hold_consumes_hold(client):
    ctx = _awaiting_payment(client)
    payload = {
        "event_id": "evt-ok-consume",
        "payment_id": ctx["payment_id"],
        "status": "succeeded",
        "signature": _sign("evt-ok-consume", ctx["payment_id"], "succeeded"),
    }
    res = client.post("/payments/webhook", json=payload)
    assert res.status_code == 200
    assert res.json()["booking_status"] == "Confirmed"
    assert res.json().get("requires_review") is False
    db = client.app.state.SessionLocal()
    try:
        hold = db.query(BookingHold).filter_by(booking_id=ctx["booking_id"]).one()
        assert hold.status == "cancelled"
        consumed = (
            db.query(AuditLog)
            .filter_by(entity_id=ctx["booking_id"], action="hold.consumed")
            .count()
        )
        assert consumed == 1
        expired = (
            db.query(AuditLog)
            .filter_by(entity_id=ctx["booking_id"], action="hold.expired")
            .count()
        )
        assert expired == 0
        assert db.get(AvailabilitySlot, db.get(Booking, ctx["booking_id"]).slot_id).status == "confirmed"
    finally:
        db.close()


def test_webhook_after_expire_requires_review_no_confirm(client):
    ctx = _awaiting_payment(client)
    _force_hold_past(client, ctx["booking_id"])
    assert _expire(client)["expired"] == 1
    payload = {
        "event_id": "evt-late-after-expire",
        "payment_id": ctx["payment_id"],
        "status": "succeeded",
        "signature": _sign("evt-late-after-expire", ctx["payment_id"], "succeeded"),
    }
    res = client.post("/payments/webhook", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["booking_status"] == "Cancelled"
    assert body["payment_status"] == "succeeded"
    assert body["requires_review"] is True
    db = client.app.state.SessionLocal()
    try:
        assert db.get(Booking, ctx["booking_id"]).status == "Cancelled"
        assert db.get(AvailabilitySlot, db.get(Booking, ctx["booking_id"]).slot_id).status == "open"
        assert db.query(MoneyMovement).filter_by(payment_id=ctx["payment_id"]).count() == 1
        assert (
            db.query(AuditLog)
            .filter_by(entity_id=ctx["payment_id"], action="payment.requires_review")
            .count()
            == 1
        )
    finally:
        db.close()


def test_webhook_rejects_confirm_of_foreign_held_slot(client):
    ctx = _awaiting_payment(client)
    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        hold = (
            db.query(BookingHold)
            .filter_by(booking_id=booking.id, status="active")
            .one()
        )
        # Simulate slot belonging to another reservation semantically: mark hold slot mismatch
        # by pointing hold.slot_id away while booking.slot stays held.
        foreign = AvailabilitySlot(
            resource_type="artist",
            resource_id=db.get(AvailabilitySlot, booking.slot_id).resource_id,
            starts_at=datetime.now(timezone.utc) + timedelta(days=40),
            ends_at=datetime.now(timezone.utc) + timedelta(days=40, hours=2),
            status="open",
        )
        db.add(foreign)
        db.flush()
        hold.slot_id = foreign.id
        db.commit()
    finally:
        db.close()
    payload = {
        "event_id": "evt-foreign-slot",
        "payment_id": ctx["payment_id"],
        "status": "succeeded",
        "signature": _sign("evt-foreign-slot", ctx["payment_id"], "succeeded"),
    }
    res = client.post("/payments/webhook", json=payload)
    assert res.status_code == 200
    assert res.json()["requires_review"] is True
    assert res.json()["booking_status"] == "AwaitingPayment"
    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        assert booking.status == "AwaitingPayment"
        assert db.get(AvailabilitySlot, booking.slot_id).status == "held"
    finally:
        db.close()


def test_repeated_expire_is_idempotent(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    assert (
        client.post(
            f"/bookings/{ctx['booking_id']}/hold",
            headers=auth_header(ctx["customer"]["token"]),
        ).status_code
        == 200
    )
    _force_hold_past(client, ctx["booking_id"])
    assert _expire(client)["expired"] == 1
    assert _expire(client)["expired"] == 0


def test_contract_create_after_expire_rejected(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    assert (
        client.post(
            f"/bookings/{ctx['booking_id']}/hold",
            headers=auth_header(ctx["customer"]["token"]),
        ).status_code
        == 200
    )
    _force_hold_past(client, ctx["booking_id"])
    res = client.post(
        f"/bookings/{ctx['booking_id']}/contract",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert res.status_code == 409
    db = client.app.state.SessionLocal()
    try:
        assert db.get(Booking, ctx["booking_id"]).status == "Cancelled"
    finally:
        db.close()


def test_contract_sign_after_expire_rejected(client):
    ctx = _hold_to_awaiting_contract(client)
    otps = contract_otps(client.app.state.SessionLocal, ctx["contract"]["id"])
    _force_hold_past(client, ctx["booking_id"])
    signed = client.post(
        f"/contracts/{ctx['contract']['id']}/sign",
        json={
            "side": "customer",
            "otp": otps["otp_customer"],
            "body_hash": ctx["contract"]["body_sha256"],
        },
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert signed.status_code == 409
    db = client.app.state.SessionLocal()
    try:
        assert db.get(Booking, ctx["booking_id"]).status == "Cancelled"
    finally:
        db.close()


def test_stale_exclusive_inventory_helper(client):
    ctx = _awaiting_payment(client)
    _force_hold_past(client, ctx["booking_id"])
    db = client.app.state.SessionLocal()
    try:
        inv = count_stale_exclusive_holds(db)
        assert inv["total"] == 1
        assert inv["by_status"].get("AwaitingPayment") == 1
    finally:
        db.close()


def test_outsider_cannot_expire_without_token(client):
    res = client.post("/holds/expire")
    assert res.status_code in {401, 403, 422}
