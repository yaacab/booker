"""Commit security notices and non-secret email outbox rows with auth changes."""

from __future__ import annotations

import hashlib
from uuid import uuid4

from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.models import User
from booker_api.notifications.inbox import NOTICE_COPY, persist_safe_notice
from booker_api.notifications.outbox import enqueue_email
from booker_api.security import audit


def queue_security_notice(
    db: Session,
    *,
    recipient: User,
    template: str,
    actor_user_id: str | None,
) -> str:
    """Use static copy only; the SMTP worker can act only after DB commit."""
    if not template.startswith("security.") or template not in NOTICE_COPY:
        raise ValueError("Unknown security notice template")
    event_id = str(uuid4())
    notice = persist_safe_notice(
        db,
        recipient_user_id=recipient.id,
        template=template,
        entity_type="user",
        entity_id=event_id,
    )
    assert notice is not None
    if settings.email_provider == "smtp" and recipient.email:
        subject, body = NOTICE_COPY[template]
        key = hashlib.sha256(
            f"booker-security-notice:{notice.id}:{recipient.id}".encode()
        ).hexdigest()
        enqueue_email(
            db,
            idempotency_key=key,
            recipient_email=recipient.email,
            subject=subject,
            body=body,
            template=template,
            entity_type="user",
            entity_id=event_id,
        )
    audit(
        db,
        actor_user_id=actor_user_id,
        action="security.notice.queued",
        entity_type="user",
        entity_id=recipient.id,
        payload={"template": template, "notice_id": notice.id,
                 "email_outbox_queued": settings.email_provider == "smtp" and bool(recipient.email)},
    )
    return notice.id
