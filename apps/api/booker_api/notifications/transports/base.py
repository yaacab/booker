from typing import Protocol

from sqlalchemy.orm import Session

from booker_api.notifications.types import DeliveryResult, Notification


class NotificationTransport(Protocol):
    provider: str

    def send(
        self,
        db: Session,
        *,
        actor_user_id: str | None,
        notification: Notification,
    ) -> DeliveryResult: ...
