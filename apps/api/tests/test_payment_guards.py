"""Production gates, payment IDOR and signed out-of-order capture safety."""
from datetime import timedelta

import pytest

from booker_api.config import Settings, settings
from booker_api.models import AvailabilitySlot, Booking, BookingHold, Payment, TeamMember
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_payments import _awaiting_payment, _sign


def webhook(client, payment_id, event_id, status="succeeded"):
    return client.post("/payments/webhook", json={
        "event_id": event_id, "payment_id": payment_id, "status": status,
        "signature": _sign(event_id, payment_id, status),
    })


@pytest.mark.parametrize("environment,provider,opt_in", [
    ("production", "stub", True), ("production", "stub", False),
    ("test", "stub", False), ("test", "disabled", True), ("test", "", True),
])
def test_stub_never_available_without_all_explicit_gates(client, monkeypatch, environment, provider, opt_in):
    ctx = _awaiting_payment(client)
    monkeypatch.setattr(settings, "environment", environment)
    monkeypatch.setattr(settings, "payment_provider", provider)
    monkeypatch.setattr(settings, "payment_allow_stub", opt_in)
    headers = auth_header(ctx["customer"]["token"])
    assert client.post(f"/payments/{ctx['payment_id']}/stub-complete", json={}, headers=headers).status_code == 403
    assert client.post(f"/bookings/{ctx['booking_id']}/payments", json={"idempotency_key": "pay-1"}, headers=headers).status_code == 503
    assert webhook(client, ctx["payment_id"], "blocked").status_code == 503
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=headers).json()
    assert room["payment"]["status"] == "pending"
    assert not room["payment_capabilities"]["available"]
    assert not room["payment_capabilities"]["can_test_complete"]


def test_payment_defaults_fail_closed():
    assert Settings.model_fields["payment_provider"].default == "disabled"
    assert Settings.model_fields["environment"].default == "production"
    assert Settings.model_fields["payment_allow_stub"].default is False


def test_checkout_checks_org_and_writer_before_existing_idempotency(client, SessionLocal):
    ctx = _awaiting_payment(client)
    outsider = register(client, "payment-outsider@booker.test")
    viewer = register(client, "payment-viewer@booker.test")
    with SessionLocal() as db:
        db.add(TeamMember(organization_id=ctx["cust_org"]["id"], user_id=viewer["user_id"], role="viewer"))
        db.commit()
    for actor in [outsider, viewer, ctx["owner"]]:
        for key in ["pay-1", "new-key"]:
            assert client.post(f"/bookings/{ctx['booking_id']}/payments", json={"idempotency_key": key}, headers=auth_header(actor["token"])).status_code == 403
    assert client.post(f"/payments/{ctx['payment_id']}/stub-complete", json={}, headers=auth_header(viewer["token"])).status_code == 403
    with SessionLocal() as db:
        assert db.query(Payment).count() == 1
        # Removing payment makes the same auth test cover a fresh checkout.
        db.delete(db.get(Payment, ctx["payment_id"]))
        db.commit()
    assert client.post(f"/bookings/{ctx['booking_id']}/payments", json={"idempotency_key": "fresh"}, headers=auth_header(outsider["token"])).status_code == 403
    with SessionLocal() as db:
        assert db.query(Payment).count() == 0


def test_duplicate_checkout_and_out_of_order_events_never_reverse_capture(client, SessionLocal):
    ctx = _awaiting_payment(client)
    headers = auth_header(ctx["customer"]["token"])
    duplicate = client.post(f"/bookings/{ctx['booking_id']}/payments", json={"idempotency_key": "second-key"}, headers=headers)
    assert duplicate.json()["id"] == ctx["payment_id"]
    assert webhook(client, ctx["payment_id"], "success").json()["booking_status"] == "Confirmed"
    later = webhook(client, ctx["payment_id"], "late-failure", "failed")
    assert later.json()["payment_status"] == "succeeded"
    assert webhook(client, ctx["payment_id"], "success", "failed").status_code == 409
    with SessionLocal() as db:
        assert db.query(Payment).count() == 1
        hold = db.query(BookingHold).filter_by(booking_id=ctx["booking_id"]).one()
        assert hold.status == "consumed"
        hold.expires_at = now() - timedelta(hours=1)
        db.commit()
    from booker_api.routers.deals import expire_holds
    with SessionLocal() as db:
        expire_holds(db)
        assert db.get(AvailabilitySlot, ctx["slot"]["id"]).status == "confirmed"
        assert db.get(Booking, ctx["booking_id"]).status == "Confirmed"


def test_late_capture_records_money_without_confirming_expired_date(client, SessionLocal):
    ctx = _awaiting_payment(client)
    with SessionLocal() as db:
        db.query(BookingHold).filter_by(booking_id=ctx["booking_id"]).one().expires_at = now() - timedelta(seconds=1)
        db.commit()
    result = webhook(client, ctx["payment_id"], "late-success")
    assert result.status_code == 200
    assert result.json()["payment_status"] == "succeeded"
    assert result.json()["booking_status"] == "AwaitingPayment"
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=auth_header(ctx["customer"]["token"])).json()
    assert room["payment"]["requires_operator"] is True
    assert not room["payment_capabilities"]["can_test_complete"]


def test_reserving_date_freezes_terms_before_signing_contract(client):
    from tests.test_offers import ack_both, setup_negotiation

    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    headers = auth_header(ctx["customer"]["token"])
    assert client.post(f"/bookings/{ctx['booking_id']}/hold", headers=headers).status_code == 200
    changed = client.post(f"/offers/{ctx['offer']['id']}/versions", headers=auth_header(ctx["owner"]["token"]), json={"honorarium_rub": 1})
    assert changed.status_code == 409
    original = client.get(f"/deal-room/{ctx['booking_id']}", headers=headers).json()["quote"]
    assert original["honorarium_rub"] == 100000
    assert original["customer_ack"] and original["supplier_ack"]


def test_e2e_auth_limit_cannot_relax_production(monkeypatch):
    from booker_api.rate_limit import auth_request_limit

    monkeypatch.setattr(settings, "test_auth_rate_limit", 1000)
    monkeypatch.setattr(settings, "environment", "production")
    assert auth_request_limit() == 20
    monkeypatch.setattr(settings, "environment", "test")
    assert auth_request_limit() == 1000
    monkeypatch.setattr(settings, "test_auth_rate_limit", 1000000)
    assert auth_request_limit() == 1000


@pytest.mark.parametrize('problem', ['closed_event', 'foreign_hold', 'amount'])
def test_capture_preserves_money_but_does_not_claim_invalid_reservation(client, SessionLocal, problem):
    from booker_api.models import AuditLog, Event
    ctx = _awaiting_payment(client)
    with SessionLocal() as db:
        booking = db.get(Booking, ctx['booking_id'])
        hold = db.query(BookingHold).filter_by(booking_id=booking.id, status='active').one()
        if problem == 'closed_event':
            db.get(Event, booking.event_id).status = 'Cancelled'
        elif problem == 'foreign_hold':
            other = Booking(event_id=booking.event_id, offer_id=booking.offer_id, slot_id=booking.slot_id, status='DateHeld')
            db.add(other); db.flush(); hold.booking_id = other.id
        else:
            db.get(Payment, ctx['payment_id']).amount_rub += 1
        db.commit(); hold_id = hold.id
    response = webhook(client, ctx['payment_id'], f'conflict-{problem}')
    assert response.status_code == 200, response.text
    assert response.json()['payment_status'] == 'succeeded'
    assert response.json()['booking_status'] == 'AwaitingPayment'
    with SessionLocal() as db:
        assert db.get(AvailabilitySlot, db.get(Booking, ctx['booking_id']).slot_id).status == 'held'
        assert db.get(BookingHold, hold_id).status == 'active'
        assert db.query(AuditLog).filter_by(action='payment.reservation_conflict', entity_id=ctx['payment_id']).count() == 1


def test_new_checkout_rejects_closed_event(client, SessionLocal):
    from booker_api.models import Event
    ctx = _awaiting_payment(client)
    with SessionLocal() as db:
        payment = db.get(Payment, ctx['payment_id'])
        booking = db.get(Booking, ctx['booking_id'])
        db.delete(payment)
        db.get(Event, booking.event_id).status = 'Cancelled'
        db.commit()
    result = client.post(f"/bookings/{ctx['booking_id']}/payments", headers=auth_header(ctx['customer']['token']), json={'idempotency_key': 'closed-event'})
    assert result.status_code == 409
    with SessionLocal() as db:
        assert db.query(Payment).filter_by(booking_id=ctx['booking_id']).count() == 0
