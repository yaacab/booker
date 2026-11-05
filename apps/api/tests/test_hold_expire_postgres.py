"""PostgreSQL concurrency proofs for V0 hold expire vs confirm.

Requires TEST_POSTGRES_DSN (loopback, database name contains 'test').
Without DSN these tests SKIP — skip is NOT PASS.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from alembic import command
from booker_api import contract_ack
from booker_api.config import settings
from booker_api.db import get_db
from booker_api.legal_registry import seed_draft_versions
from booker_api.main import app
from booker_api.models import AvailabilitySlot, Booking, BookingHold, Payment
from booker_api.routers import payments
from booker_api.schemas import WebhookIn
from tests.conftest import auth_header
from tests.postgres_harness import isolated_postgres_schema
from tests.test_hold_race import setup_same_slot_negotiations
from tests.test_payments import _awaiting_payment, _sign

pytestmark = pytest.mark.postgres_integration


@pytest.fixture()
def postgres_hold_client(monkeypatch):
    dsn = os.environ.get("TEST_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN absent: PostgreSQL concurrency not run")
    with isolated_postgres_schema(dsn) as (engine, config, _schema):
        command.upgrade(config, "head")
        TestingSessionLocal = sessionmaker(
            bind=engine, autoflush=False, autocommit=False, future=True
        )
        issued_test_codes: dict[str, str] = {}
        TestingSessionLocal._issued_contract_codes = issued_test_codes
        original_challenge = contract_ack.new_challenge

        def capture_challenge():
            code, digest, expires_at = original_challenge()
            issued_test_codes[digest] = code
            return code, digest, expires_at

        monkeypatch.setattr(payments, "new_challenge", capture_challenge)

        def _get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _get_db
        with TestingSessionLocal() as seed_db:
            seed_draft_versions(seed_db)
            seed_db.commit()
        with TestClient(app) as client:
            client.app.state.SessionLocal = TestingSessionLocal
            yield client
        app.dependency_overrides.clear()


def _force_hold_past(client, booking_id: str) -> None:
    db = client.app.state.SessionLocal()
    try:
        hold = (
            db.query(BookingHold)
            .filter_by(booking_id=booking_id, status="active")
            .one()
        )
        hold.expires_at = datetime.now(timezone.utc) - timedelta(seconds=2)
        db.commit()
    finally:
        db.close()


def test_postgres_expire_vs_webhook_one_winner(postgres_hold_client):
    """Expire and confirm race: never Confirmed booking with open slot."""
    client = postgres_hold_client
    ctx = _awaiting_payment(client)
    _force_hold_past(client, ctx["booking_id"])

    barrier = Barrier(2)
    outcomes: list[str] = []

    def run_expire():
        session = client.app.state.SessionLocal()
        try:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            barrier.wait(timeout=10)
            from booker_api.booking_holds import expire_holds

            n = expire_holds(session)
            session.commit()
            outcomes.append(f"expire:{n}")
        finally:
            session.close()

    def run_webhook():
        session = client.app.state.SessionLocal()
        try:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            barrier.wait(timeout=10)
            body = WebhookIn(
                event_id="pg-race-evt",
                payment_id=ctx["payment_id"],
                status="succeeded",
                signature=_sign("pg-race-evt", ctx["payment_id"], "succeeded"),
            )
            result = payments._apply_payment_webhook(body, session)
            outcomes.append(
                f"webhook:{result.get('booking_status')}:{result.get('requires_review')}"
            )
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_expire), pool.submit(run_webhook)]
        for fut in futures:
            fut.result(timeout=30)

    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        slot = db.get(AvailabilitySlot, booking.slot_id)
        if booking.status == "Confirmed":
            assert slot.status == "confirmed"
            assert slot.status != "open"
        elif booking.status == "Cancelled":
            assert slot.status == "open"
            payment = db.get(Payment, ctx["payment_id"])
            assert payment.status in {"pending", "succeeded"}
        else:
            raise AssertionError(
                f"unexpected booking status {booking.status}; outcomes={outcomes}"
            )
    finally:
        db.close()


def test_postgres_parallel_holds_same_slot_one_winner(postgres_hold_client):
    """Two connections race for the same slot — exactly one active hold."""
    client = postgres_hold_client
    ctx = setup_same_slot_negotiations(client, "pg-parallel")
    barrier = Barrier(2)
    codes: list[int] = []

    def hold_one(booking_id: str, token: str):
        session = client.app.state.SessionLocal()
        try:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            barrier.wait(timeout=10)
            # Use HTTP path so full router locking applies.
        finally:
            session.close()
        res = client.post(
            f"/bookings/{booking_id}/hold",
            headers=auth_header(token),
        )
        codes.append(res.status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(hold_one, ctx["booking_id"], ctx["customer"]["token"]),
            pool.submit(hold_one, ctx["booking_id_2"], ctx["customer2"]["token"]),
        ]
        for fut in futures:
            fut.result(timeout=30)

    assert sorted(codes) == [200, 409], codes
    db = client.app.state.SessionLocal()
    try:
        active = db.query(BookingHold).filter(BookingHold.status == "active").all()
        assert len(active) == 1
        slot = db.get(AvailabilitySlot, ctx["slot"]["id"])
        assert slot.status == "held"
    finally:
        db.close()


def test_postgres_confirm_after_expire_requires_review(postgres_hold_client):
    client = postgres_hold_client
    ctx = _awaiting_payment(client)
    _force_hold_past(client, ctx["booking_id"])
    expire = client.post(
        "/holds/expire",
        headers={"X-Internal-Token": settings.webhook_secret},
    )
    assert expire.status_code == 200
    assert expire.json()["expired"] == 1

    payload = {
        "event_id": "pg-late-pay",
        "payment_id": ctx["payment_id"],
        "status": "succeeded",
        "signature": _sign("pg-late-pay", ctx["payment_id"], "succeeded"),
    }
    res = client.post("/payments/webhook", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["booking_status"] == "Cancelled"
    assert body["requires_review"] is True
    assert body["payment_status"] == "succeeded"

    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        slot = db.get(AvailabilitySlot, booking.slot_id)
        assert booking.status == "Cancelled"
        assert slot.status == "open"
    finally:
        db.close()


def test_postgres_webhook_foreign_slot_requires_review(postgres_hold_client):
    client = postgres_hold_client
    ctx = _awaiting_payment(client)
    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        hold = (
            db.query(BookingHold)
            .filter_by(booking_id=booking.id, status="active")
            .one()
        )
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
        "event_id": "pg-foreign-slot",
        "payment_id": ctx["payment_id"],
        "status": "succeeded",
        "signature": _sign("pg-foreign-slot", ctx["payment_id"], "succeeded"),
    }
    res = client.post("/payments/webhook", json=payload)
    assert res.status_code == 200
    assert res.json()["requires_review"] is True
    assert res.json()["booking_status"] == "AwaitingPayment"


def test_postgres_webhook_redelivery_idempotent(postgres_hold_client):
    client = postgres_hold_client
    ctx = _awaiting_payment(client)
    payload = {
        "event_id": "pg-redeliver",
        "payment_id": ctx["payment_id"],
        "status": "succeeded",
        "signature": _sign("pg-redeliver", ctx["payment_id"], "succeeded"),
    }
    first = client.post("/payments/webhook", json=payload)
    assert first.status_code == 200
    assert first.json()["booking_status"] == "Confirmed"
    second = client.post("/payments/webhook", json=payload)
    assert second.status_code == 200
    assert second.json()["booking_status"] == "Confirmed"
    assert second.json().get("idempotent") is True or second.json()["payment_status"] == "succeeded"

    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        assert booking.status == "Confirmed"
        assert db.get(AvailabilitySlot, booking.slot_id).status == "confirmed"
        hold = db.query(BookingHold).filter_by(booking_id=booking.id).one()
        assert hold.status == "cancelled"
    finally:
        db.close()


def test_postgres_late_payment_after_cancel_requires_review(postgres_hold_client):
    """Payment notice after cancel (expire path) must not re-confirm."""
    client = postgres_hold_client
    ctx = _awaiting_payment(client)
    _force_hold_past(client, ctx["booking_id"])
    assert (
        client.post(
            "/holds/expire",
            headers={"X-Internal-Token": settings.webhook_secret},
        ).json()["expired"]
        == 1
    )
    # Second concurrent late notice from a separate connection.
    barrier = Barrier(2)
    results: list[dict] = []

    def deliver(event_id: str):
        session = client.app.state.SessionLocal()
        try:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            barrier.wait(timeout=10)
            body = WebhookIn(
                event_id=event_id,
                payment_id=ctx["payment_id"],
                status="succeeded",
                signature=_sign(event_id, ctx["payment_id"], "succeeded"),
            )
            results.append(payments._apply_payment_webhook(body, session))
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(deliver, "pg-late-a"),
            pool.submit(deliver, "pg-late-b"),
        ]
        for fut in futures:
            fut.result(timeout=30)

    assert all(r["booking_status"] == "Cancelled" for r in results)
    assert any(r.get("requires_review") is True for r in results)
    assert all(
        r.get("requires_review") is True or r.get("ignored_terminal_event") is True
        for r in results
    )
    db = client.app.state.SessionLocal()
    try:
        booking = db.get(Booking, ctx["booking_id"])
        assert booking.status == "Cancelled"
        assert db.get(AvailabilitySlot, booking.slot_id).status == "open"
        payment = db.get(Payment, ctx["payment_id"])
        assert payment.status == "succeeded"
    finally:
        db.close()
