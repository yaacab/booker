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
from sqlalchemy.orm import sessionmaker

from alembic import command
from booker_api.db import get_db
from booker_api.legal_registry import seed_draft_versions
from booker_api.main import app
from booker_api.models import AvailabilitySlot, Booking, BookingHold, Payment
from booker_api.routers import payments
from booker_api.schemas import WebhookIn
from tests.postgres_harness import isolated_postgres_schema
from tests.test_payments import _awaiting_payment, _sign

pytestmark = pytest.mark.postgres_integration


@pytest.fixture()
def postgres_hold_client():
    dsn = os.environ.get("TEST_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN absent: PostgreSQL concurrency not run")
    with isolated_postgres_schema(dsn) as (engine, config, _schema):
        command.upgrade(config, "head")
        TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        def _get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _get_db
        with TestClient(app) as client:
            client.app.state.SessionLocal = TestingSessionLocal
            seed_draft_versions(TestingSessionLocal())
            yield client
        app.dependency_overrides.clear()


def test_postgres_expire_vs_webhook_one_winner(postgres_hold_client):
    """Expire and confirm race: never Confirmed booking with open slot."""
    client = postgres_hold_client
    ctx = _awaiting_payment(client)
    db = client.app.state.SessionLocal()
    try:
        hold = (
            db.query(BookingHold)
            .filter_by(booking_id=ctx["booking_id"], status="active")
            .one()
        )
        hold.expires_at = datetime.now(timezone.utc) - timedelta(seconds=2)
        db.commit()
    finally:
        db.close()

    barrier = Barrier(2)
    outcomes: list[str] = []

    def run_expire():
        barrier.wait(timeout=10)
        session = client.app.state.SessionLocal()
        try:
            from booker_api.booking_holds import expire_holds

            n = expire_holds(session)
            session.commit()
            outcomes.append(f"expire:{n}")
        finally:
            session.close()

    def run_webhook():
        barrier.wait(timeout=10)
        session = client.app.state.SessionLocal()
        try:
            body = WebhookIn(
                event_id="pg-race-evt",
                payment_id=ctx["payment_id"],
                status="succeeded",
                signature=_sign("pg-race-evt", ctx["payment_id"], "succeeded"),
            )
            result = payments._apply_payment_webhook(body, session)
            outcomes.append(f"webhook:{result.get('booking_status')}:{result.get('requires_review')}")
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
            # If webhook lost the race after expire, payment may still succeed with review.
            assert payment.status in {"pending", "succeeded"}
        else:
            raise AssertionError(f"unexpected booking status {booking.status}; outcomes={outcomes}")
    finally:
        db.close()
