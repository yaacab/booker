from booker_api.config import settings
from booker_api.notifications.inbox import persist_safe_notice
from booker_api.notifications.transports.base import NotificationTransport
from booker_api.notifications.transports.dev import DevTransport
from booker_api.notifications.transports.disabled import DisabledTransport
from booker_api.notifications.transports.smtp import SmtpTransport
from booker_api.notifications.types import Channel


class NotificationMisconfiguredError(RuntimeError):
    pass


class AuditTransport(DevTransport):
    """Audit-only in-app transport without a dev-labelled production provider."""

    provider = "audit"

    def send(self, db, *, actor_user_id, notification):
        if notification.channel is Channel.IN_APP:
            persist_safe_notice(
                db,
                recipient_user_id=notification.recipient_user_id,
                template=notification.template,
                entity_type=notification.entity_type,
                entity_id=notification.entity_id,
            )
        return super().send(db, actor_user_id=actor_user_id, notification=notification)


_TRANSPORTS: dict[str, type[NotificationTransport]] = {
    "disabled": DisabledTransport,
    "dev": DevTransport,
    "audit": AuditTransport,
    "smtp": SmtpTransport,
}


def _provider_for(channel: Channel) -> str:
    if channel is Channel.EMAIL:
        return settings.email_provider
    if channel is Channel.SMS:
        return settings.sms_provider
    if channel is Channel.PUSH:
        return settings.push_provider
    return settings.in_app_provider


def transport_for(channel: Channel) -> NotificationTransport:
    provider = _provider_for(channel)
    if provider == "audit" and channel is not Channel.IN_APP:
        raise NotificationMisconfiguredError("audit transport is only available for in-app events")
    cls = _TRANSPORTS.get(provider)
    if cls is None:
        raise NotificationMisconfiguredError(
            f"Неизвестный провайдер {channel.value}: {provider!r}. "
            f"Доступны: {', '.join(sorted(_TRANSPORTS))}."
        )
    return cls()
