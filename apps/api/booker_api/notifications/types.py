from dataclasses import dataclass, field
from enum import Enum


class Channel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"


@dataclass(frozen=True)
class Notification:
    channel: Channel
    template: str
    recipient_user_id: str | None = None
    recipient_email: str | None = None
    recipient_phone: str | None = None
    subject: str = ""
    body: str = ""
    entity_type: str = "notification"
    entity_id: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryResult:
    channel: Channel
    status: str
    sent: bool
    provider: str

    def as_dict(self) -> dict:
        return {
            "channel": self.channel.value,
            "status": self.status,
            "sent": self.sent,
            "provider": self.provider,
        }
