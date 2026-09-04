from booker_api.config import settings
from booker_api.notifications.transports.base import NotificationTransport
from booker_api.notifications.transports.dev import DevTransport
from booker_api.notifications.transports.disabled import DisabledTransport
from booker_api.notifications.types import Channel


class NotificationMisconfiguredError(RuntimeError):
    pass


_TRANSPORTS: dict[str, type[NotificationTransport]] = {
    "disabled": DisabledTransport,
    "dev": DevTransport,
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
    cls = _TRANSPORTS.get(provider)
    if cls is None:
        raise NotificationMisconfiguredError(
            f"Неизвестный провайдер {channel.value}: {provider!r}. "
            f"Доступны: {', '.join(sorted(_TRANSPORTS))}."
        )
    return cls()
