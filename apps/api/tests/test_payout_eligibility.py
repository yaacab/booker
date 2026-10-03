from datetime import timedelta

import pytest

from booker_api.models import Booking, Payment, ReconciliationDiscrepancy, RefundRequest
from booker_api.money_movements import append_money_movement
from booker_api.payout_eligibility import PayoutIneligible, assert_payout_eligible
from booker_api.reconciliation import import_reconciliation_report, resolve_discrepancy
from booker_api.security import now
from tests.test_payments import _awaiting_payment
from tests.test_reconciliation import _captured, _report_row


def _partner_payment(db, facts):
    payment = db.get(Payment, facts["payment_id"])
    payment.provider = "test_partner"
    db.commit()


def _partner_report(db, facts, *, report_id="payout-test-report", entries=None, complete=True):
    return import_reconciliation_report(
        db,
        provider="test_partner",
        merchant=facts["merchant"],
        report_id=report_id,
        period_start=facts["movement_at"] - timedelta(hours=1),
        period_end=facts["movement_at"] + timedelta(hours=1),
        entries=[_report_row(facts)] if entries is None else entries,
        complete=complete,
    )


def _check(db, facts):
    payment = db.get(Payment, facts["payment_id"])
    return assert_payout_eligible(
        db,
        booking_id=payment.booking_id,
        period_start=facts["movement_at"] - timedelta(minutes=30),
        period_end=facts["movement_at"] + timedelta(minutes=30),
    )


def test_payout_guard_needs_completed_checkpoint_and_clear_booking(client):
    _, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        _partner_payment(db, facts)
        with pytest.raises(PayoutIneligible, match="checkpoint_missing"):
            _check(db, facts)
        _partner_report(db, facts)
        db.commit()
        assert isinstance(_check(db, facts), Booking)
        db.rollback()
        payment = db.get(Payment, facts["payment_id"])
        booking = db.get(Booking, payment.booking_id)
        booking.payout_blocked = True
        db.commit()
        with pytest.raises(PayoutIneligible, match="booking_blocked"):
            _check(db, facts)


def test_payout_guard_checks_global_discrepancy_even_if_booking_flag_is_stale(client):
    ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        _partner_payment(db, facts)
        _partner_report(db, facts)
        db.commit()
        _partner_report(db, facts, report_id="failed-incomplete-for-gate", entries=[], complete=False)
        db.commit()
        payment = db.get(Payment, facts["payment_id"])
        booking = db.get(Booking, payment.booking_id)
        booking.payout_blocked = False  # Simulate an old/stale materialized flag.
        db.commit()
        with pytest.raises(PayoutIneligible, match="reconciliation_open"):
            _check(db, facts)
        discrepancy = db.query(ReconciliationDiscrepancy).filter_by(kind="incomplete_report").one()
        resolve_discrepancy(db, discrepancy, actor_user_id=ctx["customer"]["user_id"], resolution="Проверено вручную")
        db.commit()
        assert isinstance(_check(db, facts), Booking)


def test_payout_guard_rejects_uncovered_interval_and_external_mode(client):
    _, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        _partner_payment(db, facts)
        _partner_report(db, facts)
        db.commit()
        payment = db.get(Payment, facts["payment_id"])
        with pytest.raises(PayoutIneligible, match="checkpoint_missing"):
            assert_payout_eligible(
                db,
                booking_id=payment.booking_id,
                period_start=facts["movement_at"] - timedelta(days=1),
                period_end=facts["movement_at"] + timedelta(minutes=1),
            )
        payment.provider = "external"
        db.commit()
        with pytest.raises(PayoutIneligible, match="provider_identity_missing"):
            _check(db, facts)


def test_payout_guard_rejects_stub_and_direct_discrepancy_with_stale_flag(client):
    _, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        with pytest.raises(PayoutIneligible, match="provider_identity_missing"):
            _check(db, facts)
        _partner_payment(db, facts)
        _partner_report(db, facts, entries=[])
        db.commit()
        payment = db.get(Payment, facts["payment_id"])
        booking = db.get(Booking, payment.booking_id)
        booking.payout_blocked = False
        db.commit()
        with pytest.raises(PayoutIneligible, match="reconciliation_open"):
            _check(db, facts)
        payment.provider_merchant = "changed-merchant"
        db.commit()
        with pytest.raises(PayoutIneligible, match="reconciliation_open"):
            _check(db, facts)


def test_payout_guard_rejects_capture_outside_requested_interval(client):
    _, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        _partner_payment(db, facts)
        _partner_report(db, facts)
        db.commit()
        payment = db.get(Payment, facts["payment_id"])
        with pytest.raises(PayoutIneligible, match="movement_outside_period"):
            assert_payout_eligible(
                db,
                booking_id=payment.booking_id,
                period_start=facts["movement_at"] + timedelta(minutes=1),
                period_end=facts["movement_at"] + timedelta(minutes=20),
            )


def test_payout_guard_rejects_capture_with_missing_provider_reference(client):
    _, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        _partner_payment(db, facts)
        _partner_report(db, facts)
        db.commit()
        assert isinstance(_check(db, facts), Booking)
        payment = db.get(Payment, facts["payment_id"])
        payment.provider_reference = None
        db.commit()
        with pytest.raises(PayoutIneligible, match="provider_reference_missing"):
            _check(db, facts)


def test_payout_guard_rejects_pending_payment_without_capture(client):
    ctx = _awaiting_payment(client)
    with client.app.state.SessionLocal() as db:
        payment = db.get(Payment, ctx["payment_id"])
        payment.provider = "test_partner"
        db.commit()
        moment = now()
        with pytest.raises(PayoutIneligible, match="booking_state_ineligible"):
            assert_payout_eligible(
                db,
                booking_id=payment.booking_id,
                period_start=moment - timedelta(hours=1),
                period_end=moment + timedelta(hours=1),
            )


def test_payout_guard_rejects_dispute_open_refund_and_zero_net(client):
    ctx, facts = _captured(client)
    with client.app.state.SessionLocal() as db:
        _partner_payment(db, facts)
        _partner_report(db, facts)
        db.commit()
        payment = db.get(Payment, facts["payment_id"])
        booking = db.get(Booking, payment.booking_id)
        booking.status = "Dispute"
        db.commit()
        with pytest.raises(PayoutIneligible, match="booking_state_ineligible"):
            _check(db, facts)
        booking.status = "Confirmed"
        refund = RefundRequest(
            payment_id=payment.id,
            requested_by_user_id=ctx["customer"]["user_id"],
            amount_rub=payment.amount_rub,
            reason="Требуется проверка",
        )
        db.add(refund)
        db.commit()
        with pytest.raises(PayoutIneligible, match="refund_pending"):
            _check(db, facts)
        refund.status = "refunded"
        payment.status = "refunded"
        db.commit()
        with pytest.raises(PayoutIneligible, match="payment_refunded"):
            _check(db, facts)
        payment.status = "succeeded"  # Simulate stale payment state with a real debit.
        append_money_movement(
            db,
            payment=payment,
            kind="refund",
            direction="debit",
            amount_rub=payment.amount_rub,
            source_type="provider_refund",
            source_id="payout-guard-full-refund",
        )
        db.commit()
        with pytest.raises(PayoutIneligible, match="net_capture_missing"):
            _check(db, facts)
