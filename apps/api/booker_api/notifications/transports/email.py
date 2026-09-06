from booker_api.notifications.registry import transport_for
from booker_api.notifications.types import Channel


def email_transport():
    return transport_for(Channel.EMAIL)


def sms_transport():
    return transport_for(Channel.SMS)


def push_transport():
    return transport_for(Channel.PUSH)


def in_app_transport():
    return transport_for(Channel.IN_APP)
