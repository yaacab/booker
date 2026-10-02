"""Automatic first-response escalation is durable, private, and repeat-safe."""

from datetime import datetime, timedelta, timezone

from booker_api.config import settings
from booker_api.models import (
    AuditLog,
    EmailOutbox,
    SupportNotificationTarget,
    SupportTicket,
    User,
    UserNotification,
)
from booker_api.security import now
from booker_api.support_escalation import escalate_overdue
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_support_security import _ticket_payload
from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers


def _ticket(client, user, key):
    result = client.post(
        "/support/tickets", json=_ticket_payload(),
        headers={**auth_header(user["token"]), "Idempotency-Key": key},
    )
    assert result.status_code == 201, result.text
    return result.json()


def _due(SessionLocal, ticket_id, at):
    with SessionLocal() as db:
        row = db.get(SupportTicket, ticket_id)
        row.response_due_at = at - timedelta(minutes=1)
        db.commit()


def test_overdue_goes_to_eligible_admins_once_and_stays_private(client, SessionLocal):
    owner = register(client, "escalation-owner@booker.test")
    ticket = _ticket(client, owner, "escalation-ticket-one")
    at = datetime.now(timezone.utc)
    _due(SessionLocal, ticket["id"], at)
    _promote_admin(client, "escalation-no-factor@booker.test")
    with SessionLocal() as db:
        assert escalate_overdue(db, at=at) == {
            "escalated": 0, "no_admin": 1, "notices": 0,
            "email_queued": 0, "email_unavailable": 0,
        }
        assert db.get(SupportTicket, ticket["id"]).overdue_escalated_at is None

    admin = _promote_admin(client, "escalation-admin@booker.test", totp=TEST_TOTP_SECRET)
    second = _promote_admin(client, "escalation-second@booker.test", totp=TEST_TOTP_SECRET)
    with SessionLocal() as db:
        assert escalate_overdue(db, at=at) == {
            "escalated": 1, "no_admin": 0, "notices": 2,
            "email_queued": 0, "email_unavailable": 0,
        }
        assert escalate_overdue(db, at=at) == {
            "escalated": 0, "no_admin": 0, "notices": 0,
            "email_queued": 0, "email_unavailable": 0,
        }
        assert db.query(UserNotification).filter(
            UserNotification.entity_type == "support_ticket",
            UserNotification.entity_id == ticket["id"],
        ).count() == 2
        assert db.query(AuditLog).filter(
            AuditLog.entity_id == ticket["id"],
            AuditLog.action == "support.ticket.first_response_overdue",
        ).count() == 1

    for staff in (admin, second):
        inbox = client.get("/notifications", headers=auth_header(staff["token"]))
        assert inbox.status_code == 200
        assert any(row["template"] == "support.first_response_overdue"
                   and row["entity_id"] == ticket["id"] for row in inbox.json()["items"])
    customer_inbox = client.get("/notifications", headers=auth_header(owner["token"]))
    assert ticket["id"] not in str(customer_inbox.json())
    customer_ticket = client.get(
        f"/support/tickets/{ticket['id']}", headers=auth_header(owner["token"])
    ).json()
    assert "overdue_escalated_at" not in customer_ticket
    staff_detail = client.get(
        f"/admin/support/tickets/{ticket['id']}",
        headers=admin_totp_headers(admin["token"]),
    ).json()
    assert staff_detail["overdue_escalated_at"] is not None
    assert any(event["action"] == "support.ticket.first_response_overdue"
               for event in staff_detail["system_events"])
    escalated = client.get(
        "/admin/support/tickets?escalated_only=true",
        headers=admin_totp_headers(admin["token"]),
    )
    assert escalated.status_code == 200
    assert [row["id"] for row in escalated.json()["items"]] == [ticket["id"]]
    with SessionLocal() as db:
        former = db.get(User, second["user_id"])
        former.is_platform_admin = False
        db.commit()
    former_inbox = client.get("/notifications", headers=auth_header(second["token"]))
    assert ticket["id"] not in str(former_inbox.json())


def test_replied_closed_and_not_due_are_not_escalated(client, SessionLocal):
    owner = register(client, "escalation-replied@booker.test")
    admin = _promote_admin(client, "escalation-worker@booker.test", totp=TEST_TOTP_SECRET)
    replied = _ticket(client, owner, "escalation-replied-one")
    closed = _ticket(client, owner, "escalation-closed-two")
    future = _ticket(client, owner, "escalation-future-three")
    at = datetime.now(timezone.utc)
    for row in (replied, closed):
        _due(SessionLocal, row["id"], at)
    headers = admin_totp_headers(admin["token"])
    assert client.post(
        f"/admin/support/tickets/{replied['id']}/messages",
        json={"body": "Ответили до запуска обработки"},
        headers={**headers, "Idempotency-Key": "escalation-reply-one",
                 "If-Match": str(replied["state_version"])},
    ).status_code == 201
    assert client.post(
        f"/admin/support/tickets/{closed['id']}/close",
        headers={**headers, "If-Match": str(closed["state_version"])},
    ).status_code == 200
    with SessionLocal() as db:
        assert escalate_overdue(db, at=at) == {
            "escalated": 0, "no_admin": 0, "notices": 0,
            "email_queued": 0, "email_unavailable": 0,
        }
        assert all(db.get(SupportTicket, row["id"]).overdue_escalated_at is None
                   for row in (replied, closed, future))


def test_admin_target_queues_email_after_commit_and_rechecks_before_send(
    client, SessionLocal, monkeypatch,
):
    from booker_api.notifications import outbox

    owner = register(client, "escalation-mail-owner@booker.test")
    admin = _promote_admin(client, "escalation-mail-admin@booker.test", totp=TEST_TOTP_SECRET)
    headers = {**admin_totp_headers(admin["token"]), "If-Match": "0"}
    target_body = {"recipient_user_id": admin["user_id"], "channel": "email",
                   "escalation_level": "administrator", "active": True}
    url = "/admin/support/notification-targets"
    assert client.get(url, headers=auth_header(owner["token"])).status_code == 403
    assert client.post(url, json=target_body, headers=headers).status_code == 409
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "localhost")
    configured = client.post(url, json=target_body, headers=headers)
    assert configured.status_code == 200, configured.text
    assert configured.json()["state_version"] == 0
    duplicate = client.post(url, json=target_body, headers=headers)
    assert duplicate.status_code == 200 and duplicate.json()["idempotent"] is True
    listing = client.get(url, headers=admin_totp_headers(admin["token"]))
    assert listing.status_code == 200
    assert listing.json()["items"][0]["active"] is True
    assert "escalation-mail-admin@" not in listing.text

    ticket = _ticket(client, owner, "escalation-mail-ticket")
    at = datetime.now(timezone.utc)
    _due(SessionLocal, ticket["id"], at)
    attempts = []
    monkeypatch.setattr(outbox, "_deliver", lambda row: (attempts.append(row.id) or True, "sent"))
    with SessionLocal() as db:
        result = escalate_overdue(db, at=at)
        assert result == {"escalated": 1, "no_admin": 0, "notices": 1,
                          "email_queued": 1, "email_unavailable": 0}
        row = db.query(EmailOutbox).filter_by(template="support.first_response_overdue").one()
        assert row.status == "pending"
        assert ticket["id"] not in row.body
        assert owner["user_id"] not in row.body
        assert not attempts
        row_id = row.id

    monkeypatch.setattr(outbox, "utcnow", lambda: datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc))
    with SessionLocal() as db:
        assert outbox.deliver_outbox_row(db, db.get(EmailOutbox, row_id))["status"] == "deferred"
        assert db.get(EmailOutbox, row_id).attempts == 0
    monkeypatch.setattr(outbox, "utcnow", lambda: datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc))
    with SessionLocal() as db:
        assert outbox.deliver_outbox_row(db, db.get(EmailOutbox, row_id))["status"] == "sent"
        assert outbox.deliver_outbox_row(db, db.get(EmailOutbox, row_id))["status"] == "sent"
        assert db.get(EmailOutbox, row_id).attempts == 1
        assert attempts == [row_id]


def test_deactivated_support_target_cancels_pending_email(client, SessionLocal, monkeypatch):
    from booker_api.notifications import outbox

    owner = register(client, "escalation-cancel-owner@booker.test")
    admin = _promote_admin(client, "escalation-cancel-admin@booker.test", totp=TEST_TOTP_SECRET)
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "localhost")
    url = "/admin/support/notification-targets"
    body = {"recipient_user_id": admin["user_id"], "channel": "email",
            "escalation_level": "administrator", "active": True}
    headers = {**admin_totp_headers(admin["token"]), "If-Match": "0"}
    assert client.post(url, json=body, headers=headers).status_code == 200
    ticket = _ticket(client, owner, "escalation-cancel-ticket")
    at = datetime.now(timezone.utc)
    _due(SessionLocal, ticket["id"], at)
    with SessionLocal() as db:
        escalate_overdue(db, at=at)
        row_id = db.query(EmailOutbox).filter_by(template="support.first_response_overdue").one().id
    stopped = client.post(url, json={**body, "active": False}, headers=headers)
    assert stopped.status_code == 200 and stopped.json()["state_version"] == 1
    assert client.post(url, json=body, headers=headers).status_code == 409
    monkeypatch.setattr(outbox, "utcnow", lambda: datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(outbox, "_deliver", lambda _row: (_ for _ in ()).throw(AssertionError("sent")))
    with SessionLocal() as db:
        assert outbox.deliver_outbox_row(db, db.get(EmailOutbox, row_id))["status"] == "cancelled"
        assert db.get(EmailOutbox, row_id).attempts == 0
        assert db.query(SupportNotificationTarget).one().active is False


def test_ambiguous_support_email_is_not_retried_automatically(client, SessionLocal, monkeypatch):
    from booker_api.notifications import outbox

    owner = register(client, "escalation-uncertain-owner@booker.test")
    admin = _promote_admin(client, "escalation-uncertain-admin@booker.test",
                           totp=TEST_TOTP_SECRET)
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "localhost")
    configured = client.post(
        "/admin/support/notification-targets",
        json={"recipient_user_id": admin["user_id"], "channel": "email",
              "escalation_level": "administrator", "active": True},
        headers={**admin_totp_headers(admin["token"]), "If-Match": "0"},
    )
    assert configured.status_code == 200
    ticket = _ticket(client, owner, "escalation-uncertain-ticket")
    at = datetime.now(timezone.utc)
    _due(SessionLocal, ticket["id"], at)
    with SessionLocal() as db:
        assert escalate_overdue(db, at=at)["email_queued"] == 1
        row_id = db.query(EmailOutbox).filter_by(template="support.first_response_overdue").one().id
    monkeypatch.setattr(outbox, "utcnow", lambda: datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc))
    attempted = []
    monkeypatch.setattr(outbox, "_deliver", lambda row: (attempted.append(row.id) or False,
                                                         "SMTPServerDisconnected:uncertain"))
    with SessionLocal() as db:
        assert outbox.deliver_outbox_row(db, db.get(EmailOutbox, row_id))["status"] == "uncertain"
        assert outbox.retry_pending_outbox(db)["processed"] == 0
        assert outbox.deliver_outbox_row(db, db.get(EmailOutbox, row_id))["status"] == "uncertain"
        assert db.get(EmailOutbox, row_id).attempts == 1
    assert attempted == [row_id]


def test_only_admin_can_configure_one_real_primary_per_channel(client, SessionLocal):
    admin = _promote_admin(client, "target-policy-admin@booker.test", totp=TEST_TOTP_SECRET)
    first = register(client, "target-policy-first@booker.test")
    second = register(client, "target-policy-second@booker.test")
    customer = register(client, "target-policy-customer@booker.test")
    with SessionLocal() as db:
        for user_id in (first["user_id"], second["user_id"]):
            user = db.get(User, user_id)
            user.is_support_operator = True
            user.email_verified_at = now()
            user.totp_enabled = True
            user.totp_secret = TEST_TOTP_SECRET
        db.commit()
    url = "/admin/support/notification-targets"
    headers = {**admin_totp_headers(admin["token"]), "If-Match": "0"}
    primary = {"recipient_user_id": first["user_id"], "channel": "cabinet",
               "escalation_level": "primary", "active": True}
    assert client.post(url, json=primary, headers=auth_header(first["token"])).status_code == 403
    assert client.post(url, json={**primary, "recipient_user_id": customer["user_id"]},
                       headers=headers).status_code == 409
    assert client.post(url, json={**primary, "channel": "telegram"},
                       headers=headers).status_code == 409
    assert client.post(url, json={**primary, "active": "true"},
                       headers=headers).status_code == 422
    assert client.post(url, json=primary, headers=headers).status_code == 200
    assert client.post(url, json={**primary, "recipient_user_id": second["user_id"]},
                       headers=headers).status_code == 409
