"""Durable local escalation of unanswered tickets after their response deadline.

Run from a scheduler with one worker per database. This records an in-app
notice only; external delivery is a separate, explicitly configured gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.models import SupportMessage, SupportNotificationTarget, SupportTicket, User
from booker_api.notifications.inbox import NOTICE_COPY, persist_safe_notice
from booker_api.notifications.outbox import enqueue_email
from booker_api.security import audit


def queue_new_ticket_notices(db: Session, ticket: SupportTicket) -> dict[str, int]:
    """Route a new ticket inside its creation transaction, without external I/O."""

    primary = (db.query(User).join(
        SupportNotificationTarget,
        SupportNotificationTarget.recipient_user_id == User.id,
    ).filter(
        SupportNotificationTarget.channel == "cabinet",
        SupportNotificationTarget.escalation_level == "primary",
        SupportNotificationTarget.active.is_(True),
        User.is_support_operator.is_(True),
        User.is_platform_admin.is_(False),
        User.email_verified_at.is_not(None),
        User.totp_enabled.is_(True),
    ).one_or_none())
    recipients = [primary] if primary else db.query(User).filter(
        User.is_platform_admin.is_(True),
        User.email_verified_at.is_not(None),
        User.totp_enabled.is_(True),
    ).order_by(User.id).all()
    level = "primary" if primary else "administrator"
    urgent = ticket.priority in {"urgent", "high"}
    template = "support.ticket.urgent" if urgent else "support.ticket.new"
    notices = emails = 0
    for recipient in recipients:
        notice = persist_safe_notice(
            db, recipient_user_id=recipient.id, template=template,
            entity_type="support_ticket", entity_id=ticket.id,
        )
        notices += int(notice is not None)
        if not urgent or settings.email_provider != "smtp" or not settings.email_smtp_host:
            continue
        email_target = db.query(SupportNotificationTarget.id).filter(
            SupportNotificationTarget.recipient_user_id == recipient.id,
            SupportNotificationTarget.channel == "email",
            SupportNotificationTarget.escalation_level == level,
            SupportNotificationTarget.active.is_(True),
        ).first()
        if not email_target:
            continue
        subject, body = NOTICE_COPY[template]
        key = hashlib.sha256(
            f"support-new-urgent:{ticket.id}:{recipient.id}:{email_target[0]}".encode()
        ).hexdigest()
        enqueue_email(
            db, idempotency_key=key, recipient_email=recipient.email,
            subject=subject, body=body, template=template,
            entity_type="support_ticket", entity_id=ticket.id,
        )
        emails += 1
    audit(db, actor_user_id=None, action="support.ticket.new_routed",
          entity_type="support_ticket", entity_id=ticket.id,
          payload={"level": level, "notices": notices, "email_queued": emails,
                   "priority": ticket.priority})
    return {"notices": notices, "email_queued": emails}


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
        return {"escalated": 0, "no_admin": 1, "notices": 0,
                "email_queued": 0, "email_unavailable": 0}
    admin_ids = {row[0] for row in admins}
    email_targets = (db.query(SupportNotificationTarget, User)
                     .join(User, User.id == SupportNotificationTarget.recipient_user_id)
                     .filter(SupportNotificationTarget.channel == "email",
                             SupportNotificationTarget.escalation_level == "administrator",
                             SupportNotificationTarget.active.is_(True),
                             SupportNotificationTarget.recipient_user_id.in_(admin_ids))
                     .all())

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
    escalated = notices = email_queued = email_unavailable = 0
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
        for target, recipient in email_targets:
            if settings.email_provider != "smtp" or not settings.email_smtp_host:
                email_unavailable += 1
                continue
            subject, body = NOTICE_COPY["support.first_response_overdue"]
            key = hashlib.sha256(
                f"support-first-response-overdue:{ticket_id}:{target.id}".encode()
            ).hexdigest()
            enqueue_email(
                db, idempotency_key=key, recipient_email=recipient.email,
                subject=subject, body=body,
                template="support.first_response_overdue",
                entity_type="support_ticket", entity_id=ticket_id,
            )
            email_queued += 1
        db.commit()
        escalated += 1
    return {"escalated": escalated, "no_admin": 0, "notices": notices,
            "email_queued": email_queued, "email_unavailable": email_unavailable}


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
