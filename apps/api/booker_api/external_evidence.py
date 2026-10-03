"""External transfer evidence is not a provider money fact."""

from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.models import ExternalPaymentEvent, Payment

KINDS = {"payer_reported", "recipient_acknowledged", "admin_evidence_reviewed",
         "correction_requested", "correction_approved"}


def safe_note(value: str) -> str:
    note = value.strip()
    if (len(note) < 3 or len(note) > 500 or any(ord(char) < 32 for char in note)
            or re.search(r"https?://|@|\b\d{10,}\b", note, re.IGNORECASE)):
        raise HTTPException(422, "Пояснение не должно содержать ссылок, контактов или длинных номеров")
    return note


def reserve_version(db: Session, payment: Payment, expected: int) -> int:
    changed = db.execute(
        update(Payment)
        .where(Payment.id == payment.id, Payment.external_evidence_version == expected)
        .values(external_evidence_version=expected + 1)
    ).rowcount
    if changed != 1:
        raise HTTPException(409, "Версия сведений изменилась")
    db.expire(payment)
    return expected + 1


def append_event(db: Session, *, payment: Payment, report_id: str, kind: str,
                 idempotency_key: str, expected_version: int, actor_user_id: str,
                 parent_event_id: str | None = None, reason_code: str | None = None,
                 note: str = "") -> ExternalPaymentEvent:
    if kind not in KINDS:
        raise ValueError("unknown external evidence kind")
    event = ExternalPaymentEvent(
        payment_id=payment.id, report_id=report_id, kind=kind,
        parent_event_id=parent_event_id, idempotency_key=idempotency_key,
        expected_version=expected_version, actor_user_id=actor_user_id,
        reason_code=reason_code, note=note,
    )
    db.add(event)
    db.flush()
    return event


def effective_review_state(events: list[ExternalPaymentEvent], report_status: str,
                           report_id: str) -> str:
    events = [row for row in events if row.report_id == report_id]
    if any(row.kind == "correction_approved" for row in events):
        return "corrected"
    if any(row.kind == "correction_requested" for row in events):
        return "correction_pending"
    if any(row.kind == "admin_evidence_reviewed" for row in events) or report_status == "recorded":
        return "admin_evidence_reviewed"
    if any(row.kind == "recipient_acknowledged" for row in events):
        return "recipient_acknowledged"
    return "payer_reported"
