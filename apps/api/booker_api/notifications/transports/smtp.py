"""SMTP email transport. Enabled when BOOKER_EMAIL_PROVIDER=smtp."""

from __future__ import annotations

from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.notifications.outbox import _deliver, enqueue_email
from booker_api.notifications.types import DeliveryResult, Notification
from booker_api.security import audit


class SmtpTransport:
    provider = "smtp"

    def send(
        self,
        db: Session,
        *,
        actor_user_id: str | None,
        notification: Notification,
    ) -> DeliveryResult:
        to = (notification.recipient_email or "").strip()
        host = (settings.email_smtp_host or "").strip()
        idem = (
            f"{notification.template}:{notification.entity_type}:"
            f"{notification.entity_id}:{to}"
        )
        if not to or not host:
            audit(
                db,
                actor_user_id=actor_user_id,
                action="notification.email",
                entity_type=notification.entity_type,
                entity_id=notification.entity_id or notification.template,
                payload={
                    "template": notification.template,
                    "status": "skipped",
                    "reason": "missing recipient or BOOKER_EMAIL_SMTP_HOST",
                    "provider": self.provider,
                },
            )
            return DeliveryResult(
                channel=notification.channel,
                status="skipped",
                sent=False,
                provider=self.provider,
            )

        row = enqueue_email(
            db,
            idempotency_key=idem,
            recipient_email=to,
            subject=notification.subject or "Букер",
            body=notification.body or "",
            template=notification.template,
            entity_type=notification.entity_type,
            entity_id=notification.entity_id or notification.template,
        )
        if row.status == "sent":
            # Idempotent: event preserved, no duplicate delivery.
            audit(
                db,
                actor_user_id=actor_user_id,
                action="notification.email",
                entity_type=notification.entity_type,
                entity_id=notification.entity_id or notification.template,
                payload={
                    "template": notification.template,
                    "recipient_email": to,
                    "status": "already_sent",
                    "provider": self.provider,
                    "outbox_id": row.id,
                },
            )
            return DeliveryResult(
                channel=notification.channel,
                status="already_sent",
                sent=True,
                provider=self.provider,
            )

        ok, detail = _deliver(row)
        row.attempts = int(row.attempts or 0) + 1
        if ok:
            row.status = "sent"
            from booker_api.models import utcnow

            row.sent_at = utcnow()
            row.last_error = ""
            status = "sent"
        else:
            row.status = "failed"
            row.last_error = detail[:2000]
            status = f"error:{detail[:80]}"

        audit(
            db,
            actor_user_id=actor_user_id,
            action="notification.email",
            entity_type=notification.entity_type,
            entity_id=notification.entity_id or notification.template,
            payload={
                "template": notification.template,
                "recipient_email": to,
                "subject": notification.subject,
                "status": status,
                "provider": self.provider,
                "outbox_id": row.id,
                "attempts": row.attempts,
            },
        )
        db.flush()
        return DeliveryResult(
            channel=notification.channel,
            status=status,
            sent=ok,
            provider=self.provider,
        )
