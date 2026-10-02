"""Durable local escalation of unanswered tickets after their response deadline.

Run from a scheduler with one worker per database. This records an in-app
notice only; external delivery is a separate, explicitly configured gate.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.models import SupportMessage, SupportTicket, User
from booker_api.notifications.inbox import persist_safe_notice
from booker_api.security import audit


def escalate_overdue(db: Session, *, at: datetime, limit: int = 100) -> dict[str, int]:
    """CAS each ticket so a simultaneous reply or worker cannot double-escalate."""
    if at.tzinfo is None or limit < 1 or limit > 500:
        raise ValueError("UTC-aware at and a limit of 1..500 are required")
    at = at.astimezone(timezone.utc)
    admins = db.query(User.id).filter(
        User.is_platform_admin.is_(True),
        User.email_verified_at.is_not(None),
        User.totp_enabled.is_(True),
    ).order_by(User.id).all()
    if not admins:
        return {"escalated": 0, "no_admin": 1, "notices": 0}

    replied = db.query(SupportMessage.id).filter(
        SupportMessage.ticket_id == SupportTicket.id,
        SupportMessage.author_kind == "operator",
    ).exists()
    rows = db.query(SupportTicket.id, SupportTicket.state_version).filter(
        SupportTicket.response_due_at.is_not(None),
        SupportTicket.response_due_at <= at,
        SupportTicket.overdue_escalated_at.is_(None),
        SupportTicket.status.notin_(("closed", "resolved")),
        ~replied,
    ).order_by(SupportTicket.response_due_at, SupportTicket.id).limit(limit).all()
    escalated = notices = 0
    for ticket_id, version in rows:
        # The EXISTS predicate is checked again inside the conditional write.
        # Replies advance state_version, so either transaction wins, not both.
        changed = db.execute(update(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.state_version == version,
            SupportTicket.response_due_at <= at,
            SupportTicket.overdue_escalated_at.is_(None),
            SupportTicket.status.notin_(("closed", "resolved")),
            ~replied,
        ).values(
            overdue_escalated_at=at,
            state_version=SupportTicket.state_version + 1,
        )).rowcount
        if changed != 1:
            db.rollback()
            continue
        audit(db, actor_user_id=None,
              action="support.ticket.first_response_overdue",
              entity_type="support_ticket", entity_id=ticket_id,
              payload={"state_version": version + 1})
        for (admin_id,) in admins:
            notice = persist_safe_notice(
                db, recipient_user_id=admin_id,
                template="support.first_response_overdue",
                entity_type="support_ticket", entity_id=ticket_id,
            )
            notices += int(notice is not None)
        db.commit()
        escalated += 1
    return {"escalated": escalated, "no_admin": 0, "notices": notices}


def main() -> int:
    parser = argparse.ArgumentParser(description="Escalate unanswered Booker support tickets")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    from booker_api.db import SessionLocal

    with SessionLocal() as db:
        result = escalate_overdue(db, at=datetime.now(timezone.utc), limit=args.limit)
    print(json.dumps(result, sort_keys=True))
    return 0 if not result["no_admin"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
