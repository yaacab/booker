"""SMTP delivery is queued in the originating transaction, never sent inline."""
from sqlalchemy.orm import Session

from booker_api.models import EmailOutbox
from booker_api.notifications.inbox import notification_key
from booker_api.notifications.outbox import enqueue_email
from booker_api.notifications.types import Channel, DeliveryResult, Notification
from booker_api.security import audit


class SmtpTransport:
    provider = "smtp"

    def send(self, db: Session, *, actor_user_id: str | None, notification: Notification) -> DeliveryResult:
        if notification.channel != Channel.EMAIL:
            raise ValueError("SMTP поддерживает только email")
        to = (notification.recipient_email or "").strip()
        if not to:
            return DeliveryResult(channel=notification.channel, status="skipped", sent=False, provider=self.provider)
        key = notification_key(to, notification.template, notification.entity_type, notification.entity_id,
            notification.subject, notification.body, notification.dedupe_key)
        legacy_key = f"{notification.template}:{notification.entity_type}:{notification.entity_id}:{to}"
        legacy = db.query(EmailOutbox).filter_by(idempotency_key=legacy_key).populate_existing().one_or_none()
        row = legacy if legacy and legacy.body == (notification.body or "") and legacy.subject == (notification.subject or "Букер") and legacy.recipient_email == to else None
        row = row or enqueue_email(db, idempotency_key=key, recipient_email=to, subject=notification.subject,
            body=notification.body, template=notification.template, entity_type=notification.entity_type,
            entity_id=notification.entity_id or notification.template)
        state = "already_sent" if row.status == "sent" else "queued" if row.status in {"pending", "failed"} else row.status
        audit(db, actor_user_id=actor_user_id, action="notification.email", entity_type=notification.entity_type,
            entity_id=notification.entity_id or notification.template,
            payload={"template": notification.template, "status": state, "provider": self.provider, "outbox_id": row.id})
        return DeliveryResult(channel=notification.channel, status=state, sent=row.status == "sent", provider=self.provider)
