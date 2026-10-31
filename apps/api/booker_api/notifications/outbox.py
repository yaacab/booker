"""Email outbox enqueue + retry without duplicate semantic delivery (E21)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.models import EmailOutbox, utcnow
from booker_api.security import audit


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
    db.add(row)
    db.flush()
    return row


def _deliver(row: EmailOutbox) -> tuple[bool, str]:
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
    except OSError as exc:
        return False, f"{exc.__class__.__name__}:{exc}"


def retry_pending_outbox(
    db: Session,
    *,
    actor_user_id: str | None = None,
    limit: int = 50,
) -> dict:
    """Retry pending/failed rows. Already-sent keys are skipped (no duplicate)."""
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
        if row.status == "sent":
            skipped += 1
            continue
        ok, detail = _deliver(row)
        row.attempts = int(row.attempts or 0) + 1
        if ok:
            row.status = "sent"
            row.sent_at = utcnow()
            row.last_error = ""
            sent += 1
        else:
            row.status = "failed"
            row.last_error = detail[:2000]
            failed += 1
        audit(
            db,
            actor_user_id=actor_user_id,
            action="email.outbox.retry",
            entity_type="email_outbox",
            entity_id=row.id,
            payload={
                "idempotency_key": row.idempotency_key,
                "status": row.status,
                "attempts": row.attempts,
                "detail": detail[:200],
            },
        )
    db.commit()
    return {"sent": sent, "failed": failed, "skipped": skipped, "processed": len(rows)}
