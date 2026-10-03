from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from booker_api.models import Booking, Dispute, DisputeEvidence
from booker_api.security import now

ACTIVE_DISPUTE_STATUSES = ("open", "in_review")

_SLA_BY_CATEGORY = {
    "no_show": ("urgent", timedelta(minutes=30)),
    "payment": ("urgent", timedelta(hours=2)),
    "delay": ("high", timedelta(hours=2)),
    "quality": ("high", timedelta(hours=4)),
    "cancel": ("high", timedelta(hours=4)),
}


def create_dispute(
    db: Session,
    *,
    booking: Booking,
    category: str,
    notes: str,
    actor_user_id: str,
) -> Dispute:
    existing = (
        db.query(Dispute)
        .filter(
            Dispute.booking_id == booking.id,
            Dispute.status.in_(ACTIVE_DISPUTE_STATUSES),
        )
        .one_or_none()
    )
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "По брони уже открыт спор", "dispute_id": existing.id},
        )
    if booking.status not in {"Confirmed", "InProgress", "Completed", "Dispute"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Спор доступен после подтверждения брони")
    if booking.status in {"Confirmed", "InProgress"}:
        booking.status = "Dispute"
    priority, response_window = _SLA_BY_CATEGORY[category]
    dispute = Dispute(
        booking_id=booking.id,
        opened_by_user_id=actor_user_id,
        category=category,
        body=notes.strip(),
        priority=priority,
        response_due_at=now() + response_window,
    )
    db.add(dispute)
    db.flush()
    return dispute


def dispute_payload(db: Session, dispute: Dispute, *, include_internal: bool = False) -> dict:
    evidence = (
        db.query(DisputeEvidence)
        .filter(DisputeEvidence.dispute_id == dispute.id)
        .order_by(DisputeEvidence.created_at.asc(), DisputeEvidence.id.asc())
        .all()
    )
    payload = {
        "id": dispute.id,
        "booking_id": dispute.booking_id,
        "opened_by_user_id": dispute.opened_by_user_id,
        "category": dispute.category,
        "notes": dispute.body,
        "status": dispute.status,
        "priority": dispute.priority,
        "response_due_at": dispute.response_due_at.isoformat() if dispute.response_due_at else None,
        "state_version": dispute.state_version,
        "decision_kind": dispute.decision_kind,
        "decision_note": dispute.decision,
        "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        "created_at": dispute.created_at.isoformat(),
        "evidence": [
            {
                "id": row.id,
                "attachment_id": row.attachment_id,
                "submitted_by_user_id": row.submitted_by_user_id,
                "note": row.note,
                "created_at": row.created_at.isoformat(),
            }
            for row in evidence
        ],
    }
    if include_internal:
        payload["assigned_to_user_id"] = dispute.assigned_to_user_id
        payload["resolved_by_user_id"] = dispute.resolved_by_user_id
    return payload
