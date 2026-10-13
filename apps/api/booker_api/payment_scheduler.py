"""Immutable payment deadlines and effective obligation states."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from booker_api.models import OfferVersion, PaymentObligation
from booker_api.security import aware, now

KINDS = ("advance", "balance", "security_deposit")


def _parse_datetime(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} обязателен")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} должен быть датой ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} должен содержать часовой пояс")
    return parsed.astimezone(timezone.utc)


def build_payment_terms_snapshot(
    body: dict[str, Any],
    *,
    amounts: dict[str, int],
    event_date: datetime,
) -> dict[str, dict[str, Any]]:
    """Validate explicit legal terms without inventing deadline intervals."""
    supplied = body.get("payment_terms")
    if supplied is not None and not isinstance(supplied, dict):
        raise ValueError("payment_terms должен быть объектом")
    supplied = supplied or {}
    event_at = aware(event_date)
    result: dict[str, dict[str, Any]] = {}
    for kind in KINDS:
        amount = int(amounts[kind])
        raw = supplied.get(kind) or {}
        if not isinstance(raw, dict):
            raise TypeError(f"payment_terms.{kind} должен быть объектом")
        if amount <= 0:
            result[kind] = {
                "due_at": None,
                "grace_until": None,
                "required_before_check_in": False,
            }
            continue
        # The advance is already a hard prerequisite for Confirmed. Its deadline
        # is action based (invoice/payment), so legacy all-upfront offers remain valid.
        if kind == "advance" and not raw:
            result[kind] = {
                "due_at": None,
                "grace_until": None,
                "required_before_check_in": True,
            }
            continue
        due_at = _parse_datetime(raw.get("due_at"), field=f"payment_terms.{kind}.due_at")
        grace_until = _parse_datetime(
            raw.get("grace_until"), field=f"payment_terms.{kind}.grace_until"
        )
        required = raw.get("required_before_check_in")
        if not isinstance(required, bool):
            raise TypeError(
                f"payment_terms.{kind}.required_before_check_in должен быть boolean"
            )
        if grace_until < due_at:
            raise ValueError(f"grace_until для {kind} не может быть раньше due_at")
        if required and grace_until > event_at:
            raise ValueError(f"grace_until для {kind} должен быть не позже даты события")
        result[kind] = {
            "due_at": due_at.isoformat(),
            "grace_until": grace_until.isoformat(),
            "required_before_check_in": required,
        }
    return result


def serialize_payment_terms(terms: dict[str, dict[str, Any]]) -> str:
    return json.dumps(terms, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def version_payment_terms(version: OfferVersion) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(version.payment_terms_json or "{}")
    except (TypeError, json.JSONDecodeError):
        raw = {}
    return raw if isinstance(raw, dict) else {}


def obligation_effective_state(
    obligation: PaymentObligation, *, at: datetime | None = None
) -> str:
    if obligation.amount_rub <= 0 or obligation.status == "not_applicable":
        return "not_applicable"
    if obligation.status == "satisfied":
        return "satisfied"
    current = aware(at or now())
    if obligation.grace_until and current > aware(obligation.grace_until):
        return "overdue"
    if obligation.due_at and current >= aware(obligation.due_at):
        return "due"
    return "pending"


def obligation_payload(obligation: PaymentObligation, *, at: datetime | None = None) -> dict:
    state = obligation_effective_state(obligation, at=at)
    return {
        "id": obligation.id,
        "kind": obligation.kind,
        "amount_rub": obligation.amount_rub,
        "recipient": obligation.recipient,
        "due_at": obligation.due_at.isoformat() if obligation.due_at else None,
        "grace_until": obligation.grace_until.isoformat() if obligation.grace_until else None,
        "required_before_check_in": obligation.required_before_check_in,
        "status": obligation.status,
        "effective_state": state,
        "blocks_check_in": obligation.required_before_check_in
        and state not in {"satisfied", "not_applicable"},
    }


def enqueue_payment_reminders(db: Session, *, at: datetime | None = None) -> dict[str, int]:
    """Create one outbox item per obligation and effective reminder stage."""
    from booker_api.models import (
        Booking,
        EmailOutbox,
        Event,
        PaymentPlan,
        TeamMember,
        User,
    )
    from booker_api.notifications.outbox import enqueue_email

    created = existing = 0
    current = at or now()
    obligations = db.query(PaymentObligation).filter(PaymentObligation.status == "pending").all()
    for obligation in obligations:
        stage = obligation_effective_state(obligation, at=current)
        if stage not in {"due", "overdue"}:
            continue
        plan = db.get(PaymentPlan, obligation.plan_id)
        booking = (
            db.query(Booking)
            .filter(Booking.accepted_offer_version_id == plan.offer_version_id)
            .one_or_none()
            if plan
            else None
        )
        event = db.get(Event, booking.event_id) if booking else None
        if not event:
            continue
        recipient = (
            db.query(User)
            .join(TeamMember, TeamMember.user_id == User.id)
            .filter(
                TeamMember.organization_id == event.organization_id,
                TeamMember.role.in_(("owner", "admin", "manager")),
                User.email.is_not(None),
            )
            .order_by(TeamMember.id.asc())
            .first()
        )
        if not recipient:
            continue
        key = f"payment-obligation:{obligation.id}:{stage}"
        was_present = db.query(EmailOutbox.id).filter_by(idempotency_key=key).first() is not None
        enqueue_email(
            db,
            idempotency_key=key,
            recipient_email=recipient.email,
            subject="Платёж по графику Букера",
            body=(
                f"Событие: {event.title}. Обязательство {obligation.kind}: "
                f"{obligation.amount_rub} RUB, состояние {stage}."
            ),
            template=f"payment_{stage}",
            entity_type="payment_obligation",
            entity_id=obligation.id,
        )
        existing += int(was_present)
        created += int(not was_present)
    return {"created": created, "existing": existing}
