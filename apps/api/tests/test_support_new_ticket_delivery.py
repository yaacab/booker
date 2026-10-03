"""New support tickets reach eligible staff without leaking ticket content."""

from datetime import datetime, timezone

from booker_api.config import settings
from booker_api.models import EmailOutbox, User, UserNotification
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_support_agent import _create_org, _create_session, _send
from tests.test_support_security import _ticket_payload
from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers, totp_code


def _primary_operator(client, SessionLocal, email):
    operator = register(client, email)
    with SessionLocal() as db:
        user = db.get(User, operator["user_id"])
        user.is_support_operator = True
        user.email_verified_at = datetime.now(timezone.utc)
        user.totp_enabled = True
        user.totp_secret = TEST_TOTP_SECRET
        db.commit()
    login = client.post("/auth/login", json={
        "email": email, "password": "password1", "totp": totp_code(),
    })
    assert login.status_code == 200, login.text
    operator["token"] = login.json()["token"]
    return operator


def _target(client, admin, recipient, channel):
    result = client.post(
        "/admin/support/notification-targets",
        json={"recipient_user_id": recipient["user_id"], "channel": channel,
              "escalation_level": "primary", "active": True},
        headers={**admin_totp_headers(admin["token"]), "If-Match": "0"},
    )
    assert result.status_code == 200, result.text


def test_new_ticket_notifies_primary_once_and_revoked_operator_cannot_read(
    client, SessionLocal,
):
    admin = _promote_admin(client, "route-admin@booker.test", totp=TEST_TOTP_SECRET)
    operator = _primary_operator(client, SessionLocal, "route-operator@booker.test")
    customer = register(client, "route-customer@booker.test")
    _target(client, admin, operator, "cabinet")
    headers = {**auth_header(customer["token"]), "Idempotency-Key": "route-normal-ticket"}
    first = client.post("/support/tickets", json=_ticket_payload(), headers=headers)
    assert first.status_code == 201, first.text
    repeat = client.post("/support/tickets", json=_ticket_payload(), headers=headers)
    assert repeat.status_code == 201 and repeat.json()["id"] == first.json()["id"]
    ticket_id = first.json()["id"]
    inbox = client.get("/notifications", headers=auth_header(operator["token"]))
    assert inbox.status_code == 200
    assert [(item["template"], item["entity_id"]) for item in inbox.json()["items"]
            if item["template"] == "support.ticket.new"] == [("support.ticket.new", ticket_id)]
    assert ticket_id not in client.get(
        "/notifications", headers=auth_header(customer["token"])
    ).text
    assert ticket_id not in client.get(
        "/notifications", headers=auth_header(admin["token"])
    ).text
    with SessionLocal() as db:
        assert db.query(UserNotification).filter_by(
            template="support.ticket.new", entity_id=ticket_id,
        ).count() == 1
        db.get(User, operator["user_id"]).is_support_operator = False
        db.commit()
    assert ticket_id not in client.get(
        "/notifications", headers=auth_header(operator["token"])
    ).text


def test_no_primary_falls_back_to_eligible_admin_cabinet(client):
    admin = _promote_admin(client, "route-fallback-admin@booker.test", totp=TEST_TOTP_SECRET)
    customer = register(client, "route-fallback-customer@booker.test")
    result = client.post(
        "/support/tickets", json=_ticket_payload(),
        headers={**auth_header(customer["token"]), "Idempotency-Key": "route-fallback-ticket"},
    )
    assert result.status_code == 201
    items = client.get("/notifications", headers=auth_header(admin["token"])).json()["items"]
    assert any(item["template"] == "support.ticket.new"
               and item["entity_id"] == result.json()["id"] for item in items)


def test_assistant_handoff_routes_once_to_admin_when_no_primary(client, SessionLocal):
    admin = _promote_admin(client, "route-handoff-admin@booker.test", totp=TEST_TOTP_SECRET)
    customer = register(client, "route-handoff-customer@booker.test")
    org = _create_org(client, customer, "Route Handoff")
    session = _create_session(client, customer, org["id"], "route-handoff-session")
    _send(client, customer, session["id"], "Исполнитель сегодня не приехал",
          "route-handoff-message")
    headers = {**auth_header(customer["token"]), "Idempotency-Key": "route-handoff-escalate"}
    first = client.post(
        f"/support/assistant/sessions/{session['id']}/escalate",
        json={"reason_code": "event_day_no_show"}, headers=headers,
    )
    repeat = client.post(
        f"/support/assistant/sessions/{session['id']}/escalate",
        json={"reason_code": "event_day_no_show"}, headers=headers,
    )
    assert first.status_code == repeat.status_code == 200
    ticket_id = first.json()["ticket"]["id"]
    assert repeat.json()["ticket"]["id"] == ticket_id
    items = client.get("/notifications", headers=auth_header(admin["token"])).json()["items"]
    assert sum(item["template"] == "support.ticket.urgent"
               and item["entity_id"] == ticket_id for item in items) == 1
    with SessionLocal() as db:
        assert db.query(UserNotification).filter_by(
            template="support.ticket.urgent", entity_id=ticket_id,
        ).count() == 1


def test_urgent_ticket_queues_static_email_and_rechecks_target(
    client, SessionLocal, monkeypatch,
):
    from booker_api.notifications import outbox

    admin = _promote_admin(client, "route-urgent-admin@booker.test", totp=TEST_TOTP_SECRET)
    operator = _primary_operator(client, SessionLocal, "route-urgent-operator@booker.test")
    customer = register(client, "route-urgent-customer@booker.test")
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "localhost")
    _target(client, admin, operator, "cabinet")
    _target(client, admin, operator, "email")
    request = _ticket_payload(body="Фотограф на мероприятие сегодня не приехал")
    created = client.post(
        "/support/tickets", json=request,
        headers={**auth_header(customer["token"]), "Idempotency-Key": "route-urgent-ticket"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["priority"] == "urgent"
    ticket_id = created.json()["id"]
    with SessionLocal() as db:
        row = db.query(EmailOutbox).filter_by(
            template="support.ticket.urgent", entity_id=ticket_id,
        ).one()
        assert row.status == "pending"
        assert "Фотограф" not in row.body
        assert customer["user_id"] not in row.body
        row_id = row.id
    inbox = client.get("/notifications", headers=auth_header(operator["token"])).json()["items"]
    assert any(item["template"] == "support.ticket.urgent"
               and item["entity_id"] == ticket_id for item in inbox)
    monkeypatch.setattr(outbox, "utcnow", lambda: datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc))
    attempts = []
    monkeypatch.setattr(outbox, "_deliver", lambda row: (attempts.append(row.id) or True, "sent"))
    with SessionLocal() as db:
        assert outbox.deliver_outbox_row(db, db.get(EmailOutbox, row_id))["status"] == "sent"
        assert outbox.deliver_outbox_row(db, db.get(EmailOutbox, row_id))["status"] == "sent"
    assert attempts == [row_id]


def test_urgent_email_cancelled_when_staff_reply_precedes_delivery(
    client, SessionLocal, monkeypatch,
):
    from booker_api.notifications import outbox

    admin = _promote_admin(client, "route-cancel-admin@booker.test", totp=TEST_TOTP_SECRET)
    operator = _primary_operator(client, SessionLocal, "route-cancel-operator@booker.test")
    customer = register(client, "route-cancel-customer@booker.test")
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "localhost")
    _target(client, admin, operator, "cabinet")
    _target(client, admin, operator, "email")
    created = client.post(
        "/support/tickets",
        json=_ticket_payload(body="Исполнитель сегодня не приехал"),
        headers={**auth_header(customer["token"]), "Idempotency-Key": "route-cancel-ticket"},
    )
    assert created.status_code == 201
    ticket = created.json()
    with SessionLocal() as db:
        row_id = db.query(EmailOutbox).filter_by(
            template="support.ticket.urgent", entity_id=ticket["id"],
        ).one().id
    replied = client.post(
        f"/admin/support/tickets/{ticket['id']}/messages",
        json={"body": "Проверяем срочное обращение"},
        headers={**admin_totp_headers(admin["token"]),
                 "If-Match": str(ticket["state_version"]),
                 "Idempotency-Key": "route-cancel-reply"},
    )
    assert replied.status_code == 201, replied.text
    monkeypatch.setattr(outbox, "utcnow", lambda: datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(outbox, "_deliver", lambda _row: (_ for _ in ()).throw(AssertionError("sent")))
    with SessionLocal() as db:
        assert outbox.deliver_outbox_row(db, db.get(EmailOutbox, row_id))["status"] == "cancelled"
