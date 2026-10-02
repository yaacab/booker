"""Email outbox enqueue + retry without duplicate semantic delivery (E21)."""

from __future__ import annotations

import json
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from sqlalchemy import case, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.models import (
    EmailOutbox,
    OrganizationInvitation,
    SupportMessage,
    SupportNotificationTarget,
    SupportTicket,
    User,
    utcnow,
)
from booker_api.notifications.inbox import NOTICE_COPY
from booker_api.security import audit, aware


@dataclass(frozen=True)
class TransientEmail:
    """An email body held only for the duration of one SMTP attempt."""

    recipient_email: str
    subject: str
    body: str
    idempotency_key: str = ""


def enqueue_email(
    db: Session,
    *,
    idempotency_key: str,
    recipient_email: str,
    subject: str,
    body: str,
    template: str = "",
    entity_type: str = "notification",
    entity_id: str = "",
) -> EmailOutbox:
    if template in {"auth.password_reset", "auth.admin_totp_proof", "auth.email_verification"}:
        raise ValueError("Authentication proofs must be delivered without a persisted outbox body")
    existing = (
        db.query(EmailOutbox).filter(EmailOutbox.idempotency_key == idempotency_key).one_or_none()
    )
    if existing:
        return existing
    row = EmailOutbox(
        idempotency_key=idempotency_key,
        recipient_email=recipient_email.strip(),
        subject=subject or "Букер",
        body=body or "",
        template=template or "",
        entity_type=entity_type,
        entity_id=entity_id or "",
        status="pending",
        attempts=0,
        last_error="",
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row
    except IntegrityError:
        existing = (
            db.query(EmailOutbox)
            .filter(EmailOutbox.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing:
            return existing
        raise


def scrub_password_reset_outbox(db: Session) -> int:
    """Erase historical reset links and stop retries of messages with lost secrets."""
    result = db.execute(
        update(EmailOutbox)
        .where(EmailOutbox.template == "auth.password_reset")
        .where((EmailOutbox.body != "") | EmailOutbox.status.in_(("pending", "failed", "sending")))
        .values(
            body="",
            status=case(
                (EmailOutbox.status.in_(("pending", "failed", "sending")), "cancelled"),
                else_=EmailOutbox.status,
            ),
            last_error="reset secret removed; request a new link",
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


def _deliver(row: EmailOutbox | TransientEmail) -> tuple[bool, str]:
    to = (row.recipient_email or "").strip()
    host = (settings.email_smtp_host or "").strip()
    if not to or not host:
        return False, "missing recipient or BOOKER_EMAIL_SMTP_HOST"
    msg = EmailMessage()
    msg["Subject"] = row.subject or "Букер"
    msg["From"] = settings.email_from or settings.support_email or "noreply@bukergo.ru"
    msg["To"] = to
    msg.set_content(row.body or "")
    try:
        with smtplib.SMTP(host, settings.email_smtp_port, timeout=20) as smtp:
            smtp.starttls()
            user = (settings.email_smtp_user or "").strip()
            password = (settings.email_api_key or "").strip()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True, "sent"
    except (OSError, smtplib.SMTPException) as exc:
        return False, f"{exc.__class__.__name__}:{exc}"


def deliver_outbox_row(
    db: Session,
    row: EmailOutbox,
    *,
    actor_user_id: str | None = None,
) -> dict:
    """Claim and deliver one row without allowing concurrent workers to send it twice."""
    if row.template == "auth.password_reset":
        scrub_password_reset_outbox(db)
        db.commit()
        return {"sent": False, "status": "cancelled"}
    if row.status in {"sent", "cancelled", "uncertain"}:
        return {"sent": row.status == "sent", "status": row.status}
    if row.template == "support.first_response_overdue":
        # Delivery is separate from escalation commit. Recheck the staff role,
        # destination, ticket state and approved schedule before external I/O.
        user = db.query(User).filter(User.email == row.recipient_email).one_or_none()
        target = (db.query(SupportNotificationTarget).filter(
            SupportNotificationTarget.recipient_user_id == user.id,
            SupportNotificationTarget.channel == "email",
            SupportNotificationTarget.escalation_level == "administrator",
            SupportNotificationTarget.active.is_(True),
        ).one_or_none() if user else None)
        ticket = db.get(SupportTicket, row.entity_id) if row.entity_type == "support_ticket" else None
        has_reply = bool(ticket and db.query(SupportMessage.id).filter(
            SupportMessage.ticket_id == ticket.id,
            SupportMessage.author_kind == "operator",
        ).first())
        expected_copy = NOTICE_COPY["support.first_response_overdue"]
        if (not user or not target or not ticket or not user.is_platform_admin
                or not user.email_verified_at or not user.totp_enabled
                or ticket.overdue_escalated_at is None
                or ticket.status in {"closed", "resolved"} or has_reply
                or (row.subject, row.body) != expected_copy):
            row.status = "cancelled"
            row.last_error = "support target or ticket is no longer eligible"
            audit(db, actor_user_id=actor_user_id,
                  action="email.outbox.cancelled", entity_type="email_outbox",
                  entity_id=row.id,
                  payload={"template": row.template, "reason": row.last_error})
            db.commit()
            return {"sent": False, "status": "cancelled"}
        try:
            schedule = json.loads(target.schedule_json)
        except (TypeError, ValueError):
            schedule = None
        approved_schedule = {"timezone": "Europe/Moscow", "weekdays": list(range(7)),
                             "start": "10:00", "end": "22:00"}
        if schedule != approved_schedule:
            row.status = "cancelled"
            row.last_error = "support target schedule is invalid"
            db.commit()
            return {"sent": False, "status": "cancelled"}
        local_time = utcnow().astimezone(ZoneInfo("Europe/Moscow"))
        if not (10 <= local_time.hour < 22):
            return {"sent": False, "status": "deferred"}
        if settings.email_provider != "smtp" or not settings.email_smtp_host:
            return {"sent": False, "status": "deferred"}
    claimed = (
        db.query(EmailOutbox)
        .filter(
            EmailOutbox.id == row.id,
            EmailOutbox.status.in_(("pending", "failed")),
        )
        .update({EmailOutbox.status: "sending"}, synchronize_session=False)
    )
    db.commit()
    if claimed != 1:
        current = db.get(EmailOutbox, row.id)
        return {
            "sent": bool(current and current.status == "sent"),
            "status": current.status if current else "missing",
        }

    current = db.get(EmailOutbox, row.id)
    assert current is not None
    if current.entity_type == "organization_invitation":
        invitation = db.get(OrganizationInvitation, current.entity_id)
        if (
            not invitation
            or invitation.status != "pending"
            or aware(invitation.expires_at) <= utcnow()
        ):
            current.status = "cancelled"
            current.last_error = "invitation is not pending"
            audit(
                db,
                actor_user_id=actor_user_id,
                action="email.outbox.cancelled",
                entity_type="email_outbox",
                entity_id=current.id,
                payload={"template": current.template, "reason": current.last_error},
            )
            db.commit()
            return {"sent": False, "status": "cancelled"}

    ok, detail = _deliver(current)
    current.attempts = int(current.attempts or 0) + 1
    if ok:
        current.status = "sent"
        current.sent_at = utcnow()
        current.last_error = ""
    else:
        # SMTP can accept a message before a socket timeout. Support alerts
        # need an operator check before another send to avoid duplicate paging.
        current.status = "uncertain" if current.template == "support.first_response_overdue" else "failed"
        current.last_error = detail[:2000]
    audit(
        db,
        actor_user_id=actor_user_id,
        action="email.outbox.delivery",
        entity_type="email_outbox",
        entity_id=current.id,
        payload={
            "template": current.template,
            "status": current.status,
            "attempts": current.attempts,
            "detail": detail[:200],
        },
    )
    db.commit()
    return {"sent": ok, "status": current.status}


def retry_pending_outbox(
    db: Session,
    *,
    actor_user_id: str | None = None,
    limit: int = 50,
) -> dict:
    """Retry pending/failed rows. Already-sent keys are skipped (no duplicate)."""
    if scrub_password_reset_outbox(db):
        db.commit()
    rows = (
        db.query(EmailOutbox)
        .filter(EmailOutbox.status.in_(("pending", "failed")))
        .order_by(EmailOutbox.created_at.asc())
        .limit(limit)
        .all()
    )
    sent = 0
    failed = 0
    skipped = 0
    for row in rows:
        result = deliver_outbox_row(db, row, actor_user_id=actor_user_id)
        if result["sent"]:
            sent += 1
        elif result["status"] == "failed":
            failed += 1
        else:
            skipped += 1
    return {"sent": sent, "failed": failed, "skipped": skipped, "processed": len(rows)}
