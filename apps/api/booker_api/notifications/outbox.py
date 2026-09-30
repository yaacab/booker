"""Email outbox enqueue + retry without duplicate semantic delivery (E21)."""

from __future__ import annotations

import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.models import EmailOutbox, utcnow
from booker_api.security import audit, now


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
        db.query(EmailOutbox).filter(EmailOutbox.idempotency_key == idempotency_key).populate_existing().one_or_none()
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
    connection = db.connection()
    if connection.dialect.name == 'sqlite' and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql('BEGIN')
    try:
        with db.begin_nested():
            db.add(row); db.flush()
    except IntegrityError:
        existing = db.query(EmailOutbox).filter_by(idempotency_key=idempotency_key).one_or_none()
        if not existing:
            raise
        return existing
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
    msg["Message-ID"] = f"<{row.id}@bukergo.ru>"
    msg.set_content(row.body or "")
    data_started = False
    try:
        with smtplib.SMTP(host, settings.email_smtp_port, timeout=20) as smtp:
            smtp.starttls()
            user = (settings.email_smtp_user or "").strip()
            password = (settings.email_api_key or "").strip()
            if user and password:
                smtp.login(user, password)
            data_started = True
            smtp.send_message(msg)
        return True, "sent"
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
        return False, f"rejected:{exc.__class__.__name__}"
    except (OSError, smtplib.SMTPException) as exc:
        return False, f"{'uncertain' if data_started else 'retryable'}:{exc.__class__.__name__}"


def retry_pending_outbox(db: Session, *, actor_user_id: str | None = None, limit: int = 50) -> dict:
    """Process committed rows in a separate session; never commit the caller's work.

    Expired claims are ambiguous (SMTP may have accepted DATA), so they are held
    for operator review instead of automatically resending.
    """
    counts = {"sent": 0, "failed": 0, "skipped": 0, "uncertain": 0, "processed": 0}
    if settings.email_provider != "smtp":
        return {**counts, "state": "disabled"}
    if not (settings.email_smtp_host or "").strip():
        return {**counts, "state": "unconfigured"}
    limit = max(1, min(limit, 100))
    with Session(bind=db.get_bind()) as worker:
        moment = now()
        stale = worker.query(EmailOutbox.id).filter(EmailOutbox.status == 'sending', EmailOutbox.claim_expires_at <= moment).limit(limit).all()
        for (row_id,) in stale:
            changed = worker.execute(update(EmailOutbox).where(EmailOutbox.id == row_id, EmailOutbox.status == 'sending', EmailOutbox.claim_expires_at <= moment)
                .values(status='uncertain', last_error='worker_claim_expired', claim_token=None, claim_expires_at=None))
            if changed.rowcount:
                counts['uncertain'] += 1
                audit(worker, actor_user_id=actor_user_id, action='email.outbox.uncertain', entity_type='email_outbox', entity_id=row_id, payload={"reason": "worker_claim_expired"})
        worker.commit()
        eligible = (EmailOutbox.status.in_(['pending', 'failed']), EmailOutbox.attempts < 5,
            or_(EmailOutbox.next_attempt_at.is_(None), EmailOutbox.next_attempt_at <= now()))
        candidates = worker.query(EmailOutbox.id).filter(*eligible).order_by(EmailOutbox.created_at, EmailOutbox.id).limit(limit).all()
        worker.commit()
        for (row_id,) in candidates:
            token = secrets.token_hex(32)
            claimed = worker.execute(update(EmailOutbox).where(EmailOutbox.id == row_id, *eligible)
                .values(status='sending', claim_token=token, claim_expires_at=now()+timedelta(minutes=10), attempts=EmailOutbox.attempts+1))
            worker.commit()
            if not claimed.rowcount:
                counts['skipped'] += 1; continue
            row = worker.get(EmailOutbox, row_id)
            # Claim has committed before the first network operation.
            try:
                ok, detail = _deliver(row)
            except Exception as exc:  # noqa: BLE001 — unknown provider outcome must never trigger an automatic resend.
                ok, detail = False, f'uncertain:{type(exc).__name__}'
            state = 'sent' if ok else 'uncertain' if detail.startswith('uncertain:') else 'failed'
            values = {'status': state, 'claim_token': None, 'claim_expires_at': None,
                'last_error': '' if ok else detail[:120], 'next_attempt_at': None if state != 'failed' else now()+timedelta(seconds=min(3600, 60*2**(row.attempts-1)))}
            if ok:
                values['sent_at'] = utcnow()
            saved = worker.execute(update(EmailOutbox).where(EmailOutbox.id == row_id, EmailOutbox.status == 'sending', EmailOutbox.claim_token == token).values(**values))
            if saved.rowcount:
                counts[state] += 1
                audit(worker, actor_user_id=actor_user_id, action='email.outbox.retry', entity_type='email_outbox', entity_id=row_id,
                    payload={'status': state, 'attempts': row.attempts})
            else:
                counts['uncertain'] += 1
            worker.commit(); counts['processed'] += 1
    return {**counts, "state": "processed"}
