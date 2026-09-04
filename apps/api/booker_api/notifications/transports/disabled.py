from sqlalchemy.orm import Session

from booker_api.notifications.types import DeliveryResult, Notification


class DisabledTransport:
    provider = "disabled"

    def send(
        self,
        db: Session,
        *,
        actor_user_id: str | None,
        notification: Notification,
    ) -> DeliveryResult:
        return DeliveryResult(
            channel=notification.channel,
            status="disabled",
            sent=False,
            provider=self.provider,
        )
