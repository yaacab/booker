import hashlib
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4

from sqlalchemy.orm import Session

from booker_api.notifications.types import DeliveryResult, Notification
from booker_api.security import audit

_DEV_INBOX_LOCK = Lock()
_DEV_INBOX: list[dict] = []
_DEV_INBOX_MAX = 1000
_DEV_INBOX_TTL = timedelta(hours=1)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def dev_inbox_for(user_id: str, *, limit: int) -> list[dict]:
    """Return bounded local-only messages without persisting bodies in audit logs."""
    now = datetime.now(timezone.utc)
    with _DEV_INBOX_LOCK:
        _DEV_INBOX[:] = [
            item for item in _DEV_INBOX
            if _aware(item["expires_at"]) > now
            and _aware(item["created_at"]) + _DEV_INBOX_TTL > now
        ]
        return [
            {
                key: value.isoformat() if isinstance(value, datetime) else value
                for key, value in item.items()
                if key != "recipient_user_id"
            }
            for item in reversed(_DEV_INBOX)
            if item["recipient_user_id"] == user_id
        ][:limit]


class DevTransport:
    provider = "dev"

    def send(
        self,
        db: Session,
        *,
        actor_user_id: str | None,
        notification: Notification,
    ) -> DeliveryResult:
        if (
            self.provider == "dev"
            and notification.channel.value == "in_app"
            and notification.recipient_user_id
        ):
            now = datetime.now(timezone.utc)
            raw_expiry = notification.metadata.get("expires_at")
            try:
                expires_at = datetime.fromisoformat(raw_expiry) if raw_expiry else now + _DEV_INBOX_TTL
            except (TypeError, ValueError):
                expires_at = now + _DEV_INBOX_TTL
            with _DEV_INBOX_LOCK:
                _DEV_INBOX.append({
                    "id": str(uuid4()),
                    "channel": "in_app",
                    "template": notification.template,
                    "subject": notification.subject,
                    "body": notification.body,
                    "entity_type": notification.entity_type,
                    "entity_id": notification.entity_id,
                    "created_at": now,
                    "expires_at": _aware(expires_at),
                    "recipient_user_id": notification.recipient_user_id,
                })
                if len(_DEV_INBOX) > _DEV_INBOX_MAX:
                    del _DEV_INBOX[:len(_DEV_INBOX) - _DEV_INBOX_MAX]
        audit(
            db,
            actor_user_id=actor_user_id,
            action=f"notification.{notification.channel.value}",
            entity_type=notification.entity_type,
            entity_id=notification.entity_id or notification.template,
            payload={
                "template": notification.template,
                "recipient_user_id": notification.recipient_user_id,
                "recipient_email_hash": (
                    hashlib.sha256(notification.recipient_email.encode()).hexdigest()
                    if notification.recipient_email
                    else None
                ),
                "has_recipient_phone": bool(notification.recipient_phone),
                "has_subject": bool(notification.subject),
                "has_body": bool(notification.body),
                "provider": self.provider,
                **notification.metadata,
            },
        )
        return DeliveryResult(
            channel=notification.channel,
            status="logged",
            sent=False,
            provider=self.provider,
        )
