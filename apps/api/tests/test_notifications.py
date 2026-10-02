from datetime import timedelta

import pytest

from booker_api.config import settings
from booker_api.notifications import (
    Channel,
    Notification,
    NotificationMisconfiguredError,
    notify,
    on_offer_created,
    on_request_created,
)
from booker_api.notifications.registry import transport_for
from booker_api.notifications.transports.dev import DevTransport
from booker_api.notifications.transports.disabled import DisabledTransport
from booker_api.security import now
from tests.conftest import auth_header, publish_artist, register


def test_notification_inbox_is_private(client, SessionLocal):
    from booker_api.models import AuditLog

    recipient = register(client, "inbox-private-recipient@booker.test")
    outsider = register(client, "inbox-private-outsider@booker.test")
    with SessionLocal() as db:
        db.add(
            AuditLog(
                action="notification.in_app",
                entity_type="test",
                entity_id="private-inbox",
                payload='{"recipient_user_id": "' + recipient["user_id"] + '", "body": "PRIVATE_INBOX_BODY"}',
            )
        )
        db.commit()
    assert client.get("/notifications").status_code == 401
    denied = client.get("/notifications", headers=auth_header(outsider["token"]))
    assert denied.status_code == 200
    assert "PRIVATE_INBOX_BODY" not in denied.text
    allowed = client.get("/notifications", headers=auth_header(recipient["token"]))
    assert allowed.status_code == 200
    assert "PRIVATE_INBOX_BODY" in allowed.text


def test_dev_in_app_body_is_private_and_not_persisted_in_audit(client, SessionLocal):
    from booker_api.models import AuditLog

    recipient = register(client, "dev-inbox-recipient@booker.test")
    outsider = register(client, "dev-inbox-outsider@booker.test")
    with SessionLocal() as db:
        notify(
            db,
            actor_user_id=None,
            notifications=[
                Notification(
                    channel=Channel.IN_APP,
                    template="contract.otp",
                    recipient_user_id=recipient["user_id"],
                    subject="Private code",
                    body="CODE_ONLY_IN_PROCESS_MEMORY_654321",
                    entity_type="contract",
                    entity_id="contract-dev-inbox",
                    metadata={"expires_at": (now() + timedelta(minutes=15)).isoformat()},
                )
            ],
        )
        db.commit()
        row = db.query(AuditLog).filter_by(entity_id="contract-dev-inbox").one()
        assert "654321" not in row.payload
        assert "CODE_ONLY_IN_PROCESS_MEMORY" not in row.payload

    allowed = client.get("/notifications", headers=auth_header(recipient["token"]))
    denied = client.get("/notifications", headers=auth_header(outsider["token"]))
    assert "CODE_ONLY_IN_PROCESS_MEMORY_654321" in allowed.text
    assert "CODE_ONLY_IN_PROCESS_MEMORY_654321" not in denied.text


def test_disabled_transports_do_not_send_or_audit(client, SessionLocal, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "disabled")
    monkeypatch.setattr(settings, "sms_provider", "disabled")
    monkeypatch.setattr(settings, "push_provider", "disabled")
    monkeypatch.setattr(settings, "in_app_provider", "disabled")

    db = SessionLocal()
    try:
        results = notify(
            db,
            actor_user_id=None,
            notifications=[
                Notification(
                    channel=Channel.EMAIL,
                    template="test.email",
                    recipient_email="a@booker.test",
                    entity_id="n1",
                ),
                Notification(
                    channel=Channel.SMS,
                    template="test.sms",
                    recipient_phone="+79000000000",
                    entity_id="n2",
                ),
            ],
        )
        db.commit()
    finally:
        db.close()

    assert results == [
        {"channel": "email", "status": "disabled", "sent": False, "provider": "disabled"},
        {"channel": "sms", "status": "disabled", "sent": False, "provider": "disabled"},
    ]

    from booker_api.models import AuditLog

    db = client.app.state.SessionLocal()
    try:
        rows = db.query(AuditLog).filter(AuditLog.action.like("notification.%")).all()
        assert rows == []
    finally:
        db.close()


def test_dev_transport_logs_to_audit(client, SessionLocal, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "dev")
    monkeypatch.setattr(settings, "in_app_provider", "dev")

    db = SessionLocal()
    try:
        results = notify(
            db,
            actor_user_id="actor-1",
            notifications=[
                Notification(
                    channel=Channel.EMAIL,
                    template="request.created",
                    recipient_user_id="user-1",
                    recipient_email="supplier@booker.test",
                    subject="Новая заявка",
                    body="Тест",
                    entity_type="request",
                    entity_id="req-1",
                ),
                Notification(
                    channel=Channel.IN_APP,
                    template="request.created",
                    recipient_user_id="user-1",
                    subject="Новая заявка",
                    body="Тест",
                    entity_type="request",
                    entity_id="req-1",
                ),
            ],
        )
        db.commit()
    finally:
        db.close()

    assert all(r["status"] == "logged" and r["sent"] is False for r in results)

    from booker_api.models import AuditLog

    db = SessionLocal()
    try:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.action.in_(["notification.email", "notification.in_app"]))
            .order_by(AuditLog.action)
            .all()
        )
        assert len(rows) == 2
        email_row = next(r for r in rows if r.action == "notification.email")
        assert email_row.entity_type == "request"
        assert email_row.entity_id == "req-1"
        assert email_row.actor_user_id == "actor-1"
    finally:
        db.close()


def test_unknown_provider_is_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "sendgrid")
    with pytest.raises(NotificationMisconfiguredError, match="sendgrid"):
        transport_for(Channel.EMAIL)


def test_transport_registry_defaults():
    assert isinstance(transport_for(Channel.EMAIL), DisabledTransport)
    assert isinstance(transport_for(Channel.SMS), DisabledTransport)
    assert isinstance(transport_for(Channel.PUSH), DisabledTransport)
    assert isinstance(transport_for(Channel.IN_APP), DevTransport)


def test_request_created_hook_logs_in_app_only_by_default(client):
    customer = register(client, "notify-cust@booker.test", "Клиент")
    owner = register(client, "notify-owner@booker.test", "Артист")
    cust_org = client.post(
        "/orgs",
        json={"name": "Заказчик", "kind": "customer"},
        headers=auth_header(customer["token"]),
    ).json()
    artist_org = client.post(
        "/orgs",
        json={"name": "Шоу", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ Notify", "category": "dj"},
        headers=auth_header(owner["token"]),
    ).json()
    starts = (now() + timedelta(days=45)).replace(microsecond=0)
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
        },
        headers=auth_header(owner["token"]),
    )
    assert slot.status_code == 200, slot.text
    publish_artist(client, owner, artist["id"])
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Свадьба",
            "event_date": starts.isoformat(),
            "guest_count": 80,
        },
        headers=auth_header(customer["token"]),
    ).json()
    res = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "artist", "resource_id": artist["id"]},
        headers=auth_header(customer["token"]),
    )
    assert res.status_code == 200

    from booker_api.models import AuditLog

    db = client.app.state.SessionLocal()
    try:
        email_rows = db.query(AuditLog).filter(AuditLog.action == "notification.email").all()
        in_app_rows = db.query(AuditLog).filter(AuditLog.action == "notification.in_app").all()
        assert email_rows == []
        assert len(in_app_rows) == 1
        assert in_app_rows[0].entity_type == "request"
    finally:
        db.close()


def test_offer_created_hook_notifies_customer_org(client):
    customer = register(client, "notify-off-c@booker.test", "Клиент")
    owner = register(client, "notify-off-o@booker.test", "Артист")
    cust_org = client.post(
        "/orgs",
        json={"name": "Заказчик", "kind": "customer"},
        headers=auth_header(customer["token"]),
    ).json()
    artist_org = client.post(
        "/orgs",
        json={"name": "Шоу", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()
    artist = client.post(
        "/artists",
        json={"organization_id": artist_org["id"], "name": "DJ Offer", "category": "dj"},
        headers=auth_header(owner["token"]),
    ).json()
    starts = (now() + timedelta(days=45)).replace(microsecond=0)
    slot = client.post(
        "/slots",
        json={
            "resource_type": "artist",
            "resource_id": artist["id"],
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=4)).isoformat(),
        },
        headers=auth_header(owner["token"]),
    ).json()
    publish_artist(client, owner, artist["id"])
    event = client.post(
        "/events",
        json={
            "organization_id": cust_org["id"],
            "title": "Корпоратив",
            "event_date": starts.isoformat(),
            "guest_count": 80,
        },
        headers=auth_header(customer["token"]),
    ).json()
    req = client.post(
        f"/events/{event['id']}/requests",
        json={"resource_type": "artist", "resource_id": artist["id"]},
        headers=auth_header(customer["token"]),
    ).json()
    offer = client.post(
        f"/requests/{req['id']}/offers",
        json={"honorarium_rub": 100000, "slot_id": slot["id"]},
        headers=auth_header(owner["token"]),
    )
    assert offer.status_code == 200

    from booker_api.models import AuditLog

    db = client.app.state.SessionLocal()
    try:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.action == "notification.in_app", AuditLog.entity_type == "offer")
            .all()
        )
        assert len(rows) == 1
    finally:
        db.close()


def test_service_helpers_return_delivery_results(client, SessionLocal):
    customer = register(client, "notify-svc-c@booker.test", "Клиент")
    owner = register(client, "notify-svc-o@booker.test", "Артист")
    cust_org = client.post(
        "/orgs",
        json={"name": "Заказчик", "kind": "customer"},
        headers=auth_header(customer["token"]),
    ).json()
    artist_org = client.post(
        "/orgs",
        json={"name": "Шоу", "kind": "artist"},
        headers=auth_header(owner["token"]),
    ).json()

    db = SessionLocal()
    try:
        request_results = on_request_created(
            db,
            actor_user_id=customer["user_id"],
            request_id="req-svc",
            supplier_org_id=artist_org["id"],
            event_title="Тест",
        )
        offer_results = on_offer_created(
            db,
            actor_user_id=owner["user_id"],
            offer_id="offer-svc",
            customer_org_id=cust_org["id"],
            event_title="Тест",
        )
        db.commit()
    finally:
        db.close()

    assert request_results == [
        {"channel": "in_app", "status": "logged", "sent": False, "provider": "dev"},
        {"channel": "email", "status": "disabled", "sent": False, "provider": "disabled"},
    ]
    assert offer_results == [
        {"channel": "in_app", "status": "logged", "sent": False, "provider": "dev"},
        {"channel": "email", "status": "disabled", "sent": False, "provider": "disabled"},
    ]
