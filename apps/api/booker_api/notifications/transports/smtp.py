"""SMTP email transport. Enabled when BOOKER_EMAIL_PROVIDER=smtp."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from booker_api.config import settings
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

        msg = EmailMessage()
        msg["Subject"] = notification.subject or "Букер"
        msg["From"] = settings.email_from or settings.support_email or "noreply@bukergo.ru"
        msg["To"] = to
        msg.set_content(notification.body or "")

        try:
            with smtplib.SMTP(host, settings.email_smtp_port, timeout=20) as smtp:
                smtp.starttls()
                user = (settings.email_smtp_user or "").strip()
                password = (settings.email_api_key or "").strip()
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
            sent = True
            status = "sent"
        except OSError as exc:
            sent = False
            status = f"error:{exc.__class__.__name__}"

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
            },
        )
        return DeliveryResult(
            channel=notification.channel,
            status=status,
            sent=sent,
            provider=self.provider,
        )
