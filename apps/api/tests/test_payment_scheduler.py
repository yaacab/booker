from datetime import datetime, timedelta, timezone

import pytest

from booker_api.models import EmailOutbox, PaymentObligation
from booker_api.payment_scheduler import (
    build_payment_terms_snapshot,
    enqueue_payment_reminders,
    obligation_effective_state,
    obligation_payload,
)
from tests.test_offers import ack_both, setup_negotiation


def test_effective_payment_states_cover_due_grace_and_overdue_boundaries():
    due = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
    grace = due + timedelta(hours=2)
    obligation = PaymentObligation(
        amount_rub=50000,
        status="pending",
        due_at=due,
        grace_until=grace,
        required_before_check_in=True,
    )
    assert obligation_effective_state(obligation, at=due - timedelta(seconds=1)) == "pending"
    assert obligation_payload(obligation, at=due - timedelta(seconds=1))["blocks_check_in"] is True
    assert obligation_effective_state(obligation, at=due) == "due"
    assert obligation_effective_state(obligation, at=grace) == "due"
    assert obligation_effective_state(obligation, at=grace + timedelta(seconds=1)) == "overdue"
    obligation.status = "satisfied"
    assert obligation_effective_state(obligation, at=grace + timedelta(days=1)) == "satisfied"


def test_terms_require_explicit_deadlines_for_balance_and_deposit():
    event_at = datetime(2030, 1, 10, 18, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="payment_terms.balance.due_at обязателен"):
        build_payment_terms_snapshot(
            {},
            amounts={"advance": 40000, "balance": 60000, "security_deposit": 0},
            event_date=event_at,
        )

    terms = build_payment_terms_snapshot(
        {
            "payment_terms": {
                "balance": {
                    "due_at": (event_at - timedelta(days=2)).isoformat(),
                    "grace_until": (event_at - timedelta(days=1)).isoformat(),
                    "required_before_check_in": True,
                },
                "security_deposit": {
                    "due_at": (event_at - timedelta(hours=4)).isoformat(),
                    "grace_until": event_at.isoformat(),
                    "required_before_check_in": False,
                },
            }
        },
        amounts={"advance": 40000, "balance": 60000, "security_deposit": 10000},
        event_date=event_at,
    )
    assert terms["balance"]["required_before_check_in"] is True
    assert terms["security_deposit"]["required_before_check_in"] is False


def test_required_grace_must_not_extend_past_event():
    event_at = datetime(2030, 1, 10, 18, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="не позже даты события"):
        build_payment_terms_snapshot(
            {
                "payment_terms": {
                    "balance": {
                        "due_at": event_at.isoformat(),
                        "grace_until": (event_at + timedelta(minutes=1)).isoformat(),
                        "required_before_check_in": True,
                    }
                }
            },
            amounts={"advance": 1, "balance": 1, "security_deposit": 0},
            event_date=event_at,
        )


def test_payment_terms_are_normalized_to_utc_before_sqlite_storage():
    terms = build_payment_terms_snapshot(
        {
            "payment_terms": {
                "balance": {
                    "due_at": "2030-01-10T12:00:00+03:00",
                    "grace_until": "2030-01-10T13:00:00+03:00",
                    "required_before_check_in": True,
                }
            }
        },
        amounts={"advance": 1, "balance": 1, "security_deposit": 0},
        event_date=datetime(2030, 1, 10, 18, tzinfo=timezone.utc),
    )
    assert terms["balance"]["due_at"] == "2030-01-10T09:00:00+00:00"
    assert terms["balance"]["grace_until"] == "2030-01-10T10:00:00+00:00"


def test_payment_reminder_is_idempotent_per_obligation_and_stage(client):
    ctx = setup_negotiation(
        client,
        {
            "advance_rub": 40000,
            "payment_terms": {
                "balance": {
                    "due_at": "2020-01-01T10:00:00+00:00",
                    "grace_until": "2020-01-01T12:00:00+00:00",
                    "required_before_check_in": True,
                }
            },
        },
    )
    ack_both(client, ctx)
    with client.app.state.SessionLocal() as db:
        first = enqueue_payment_reminders(db)
        db.commit()
        second = enqueue_payment_reminders(db)
        db.commit()
        rows = db.query(EmailOutbox).filter_by(entity_type="payment_obligation").all()
    assert first == {"created": 1, "existing": 0}
    assert second == {"created": 0, "existing": 1}
    assert len(rows) == 1
    assert rows[0].template == "payment_overdue"
