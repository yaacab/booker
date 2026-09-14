from sqlalchemy.orm import Session

from booker_api.notifications.types import DeliveryResult, Notification
from booker_api.security import audit


class DevTransport:
    provider = "dev"

    def send(
        self,
        db: Session,
        *,
        actor_user_id: str | None,
        notification: Notification,
    ) -> DeliveryResult:
        audit(
            db,
            actor_user_id=actor_user_id,
            action=f"notification.{notification.channel.value}",
            entity_type=notification.entity_type,
            entity_id=notification.entity_id or notification.template,
            payload={
                **notification.metadata,
                "template": notification.template,
                "recipient_user_id": notification.recipient_user_id,
                "recipient_email": notification.recipient_email,
                "recipient_phone": notification.recipient_phone,
                "subject": notification.subject,
                "body": "[Секрет скрыт]" if notification.template in {"contract.otp", "auth.password_reset"} else notification.body,
                "provider": self.provider,
            },
        )
        return DeliveryResult(
            channel=notification.channel,
            status="logged",
            sent=False,
            provider=self.provider,
        )
