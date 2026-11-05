from datetime import datetime, timezone

from sqlalchemy.orm import Session

from booker_api.models import OfferVersion, PaymentObligation, PaymentPlan
from booker_api.payment_scheduler import version_payment_terms
from booker_api.security import now

OBLIGATION_KINDS = ("advance", "balance", "security_deposit")


def _deadline(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(timezone.utc) if value else None


def payment_schedule(version: OfferVersion) -> dict[str, int]:
    advance = version.advance_rub or version.total_rub
    balance = version.balance_rub
    if advance + balance != version.total_rub:
        balance = version.total_rub - advance
    return {
        "advance": advance,
        "balance": balance,
        "security_deposit": version.security_deposit_rub,
    }


def ensure_payment_plan(db: Session, version: OfferVersion) -> PaymentPlan:
    plan = db.query(PaymentPlan).filter_by(offer_version_id=version.id).one_or_none()
    if plan:
        return plan
    plan = PaymentPlan(offer_version_id=version.id, currency=version.currency)
    db.add(plan)
    db.flush()
    terms = version_payment_terms(version)
    for kind, amount_rub in payment_schedule(version).items():
        item = terms.get(kind) or {}
        db.add(
            PaymentObligation(
                plan_id=plan.id,
                kind=kind,
                amount_rub=amount_rub,
                recipient="supplier",
                due_at=_deadline(item.get("due_at")),
                grace_until=_deadline(item.get("grace_until")),
                required_before_check_in=bool(item.get("required_before_check_in", False)),
                status="pending" if amount_rub > 0 else "not_applicable",
            )
        )
    db.flush()
    return plan


def obligation_for_payment(
    db: Session,
    *,
    version: OfferVersion,
    obligation_id: str | None,
) -> PaymentObligation:
    plan = ensure_payment_plan(db, version)
    query = db.query(PaymentObligation).filter_by(plan_id=plan.id)
    if obligation_id:
        row = query.filter_by(id=obligation_id).one_or_none()
    else:
        row = query.filter_by(kind="advance").one_or_none()
    if row is None:
        raise LookupError("Платёжное обязательство не найдено")
    return row


def mark_obligation_satisfied(obligation: PaymentObligation | None) -> None:
    if obligation is None or obligation.status == "satisfied":
        return
    obligation.status = "satisfied"
    obligation.satisfied_at = now()
