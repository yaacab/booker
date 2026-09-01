from booker_api.notifications.registry import transport_for
from booker_api.notifications.types import Channel


def sms_transport():
    return transport_for(Channel.SMS)
