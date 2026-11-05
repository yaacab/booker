"""Fail-closed guard for a future partner payout transaction.

Call inside the same database transaction immediately before submitting a payout.
No payout endpoint or provider call is implemented here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from booker_api.models import (
    Booking,
    MoneyMovement,
    Payment,
    ReconciliationDiscrepancy,
    ReconciliationRun,
    RefundRequest,
)
from booker_api.security import aware


class PayoutIneligible(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def assert_payout_eligible(
    db: Session,
    *,
    booking_id: str,
    period_start: datetime,
    period_end: datetime,
) -> Booking:
    """Require a clear booking and a complete checkpoint for each partner merchant.

    The caller must hold the transaction through its payout submission/claim.
    A single completed report must cover the requested interval for each pair;
    separate reports with gaps are deliberately insufficient.
    """
    if (
        period_start.tzinfo is None
        or period_start.utcoffset() is None
        or period_end.tzinfo is None
        or period_end.utcoffset() is None
        or period_end <= period_start
    ):
        raise PayoutIneligible("invalid_period")
    start, end = aware(period_start), aware(period_end)
    booking = db.query(Booking).filter_by(id=booking_id).with_for_update().one_or_none()
    if booking is None:
        raise PayoutIneligible("booking_not_found")
    if booking.payout_blocked:
        raise PayoutIneligible("booking_blocked")
    if booking.status not in {"Confirmed", "InProgress", "Completed"}:
        raise PayoutIneligible("booking_state_ineligible")
    payments = db.query(Payment).filter(Payment.booking_id == booking_id).all()
    if any(payment.status in {"refunded", "partially_refunded"} for payment in payments):
        raise PayoutIneligible("payment_refunded")
    if payments and db.query(RefundRequest.id).filter(
        RefundRequest.payment_id.in_([payment.id for payment in payments]),
        RefundRequest.status.in_(("pending", "processing")),
    ).first():
        raise PayoutIneligible("refund_pending")
    direct_open = (
        db.query(ReconciliationDiscrepancy.id)
        .filter(
            ReconciliationDiscrepancy.booking_id == booking_id,
            ReconciliationDiscrepancy.status == "open",
        )
        .first()
    )
    if direct_open:
        raise PayoutIneligible("reconciliation_open")
    pairs = {
        (provider, merchant)
        for provider, merchant in db.query(Payment.provider, Payment.provider_merchant)
        .filter(Payment.booking_id == booking_id)
        .all()
    }
    if not pairs or any(
        not provider or provider in {"stub", "external", "disabled"} or not merchant
        for provider, merchant in pairs
    ):
        raise PayoutIneligible("provider_identity_missing")
    movements = (
        db.query(MoneyMovement)
        .join(Payment, Payment.id == MoneyMovement.payment_id)
        .filter(Payment.booking_id == booking_id)
        .all()
    )
    if not any(row.kind == "capture" for row in movements):
        raise PayoutIneligible("capture_missing")
    net_amount = sum(
        row.amount_rub if row.direction == "credit" else -row.amount_rub
        for row in movements
    )
    if net_amount <= 0:
        raise PayoutIneligible("net_capture_missing")
    if any(
        row.kind == "capture" and not db.get(Payment, row.payment_id).provider_reference
        for row in movements
    ):
        raise PayoutIneligible("provider_reference_missing")
    if any(not start <= aware(row.created_at) < end for row in movements):
        raise PayoutIneligible("movement_outside_period")
    for provider, merchant in sorted(pairs):
        open_discrepancy = (
            db.query(ReconciliationDiscrepancy.id)
            .join(ReconciliationRun, ReconciliationRun.id == ReconciliationDiscrepancy.run_id)
            .filter(
                ReconciliationRun.provider == provider,
                ReconciliationRun.merchant == merchant,
                ReconciliationDiscrepancy.status == "open",
                ReconciliationDiscrepancy.booking_id.is_(None),
            )
            .first()
        )
        if open_discrepancy:
            raise PayoutIneligible("reconciliation_open")
        checkpoint = (
            db.query(ReconciliationRun.id)
            .filter(
                ReconciliationRun.provider == provider,
                ReconciliationRun.merchant == merchant,
                ReconciliationRun.status.in_(("completed", "completed_with_discrepancies")),
                ReconciliationRun.period_start <= start,
                ReconciliationRun.period_end >= end,
            )
            .first()
        )
        if not checkpoint:
            raise PayoutIneligible("checkpoint_missing")
    return booking
