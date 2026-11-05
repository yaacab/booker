"""SMTP email transport. Enabled when BOOKER_EMAIL_PROVIDER=smtp."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from booker_api.config import settings
from booker_api.notifications.outbox import TransientEmail, _deliver, enqueue_email
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
            f"{notification.entity_id}:{to}:"
            f"{notification.metadata.get('delivery_id', '')}"
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

        if notification.template in {"auth.password_reset", "auth.admin_totp_proof", "auth.email_verification"} and notification.metadata.get("ephemeral_secret") is not True:
            raise ValueError("Authentication proof delivery must be ephemeral")
        if notification.metadata.get("ephemeral_secret") is True:
            message = TransientEmail(
                recipient_email=to,
                subject=notification.subject or "Букер",
                body=notification.body or "",
                idempotency_key=idem,
            )
            ok, _ = _deliver(message)
            status = "sent" if ok else "error"
            audit(
                db,
                actor_user_id=actor_user_id,
                action="notification.email",
                entity_type=notification.entity_type,
                entity_id=notification.entity_id or notification.template,
                payload={
                    "template": notification.template,
                    "recipient_email_hash": hashlib.sha256(to.encode()).hexdigest(),
                    "status": status,
                    "provider": self.provider,
                    "delivery_id": notification.metadata.get("delivery_id"),
                    "ephemeral_secret": True,
                },
            )
            return DeliveryResult(
                channel=notification.channel,
                status=status,
                sent=ok,
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
                    "recipient_email_hash": hashlib.sha256(to.encode()).hexdigest(),
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
                "recipient_email_hash": hashlib.sha256(to.encode()).hexdigest(),
                "has_subject": bool(notification.subject),
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
