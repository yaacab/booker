"""Automatic first-response escalation is durable, private, and repeat-safe."""

from datetime import datetime, timedelta, timezone

from booker_api.models import AuditLog, SupportTicket, User, UserNotification
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
        assert escalate_overdue(db, at=at) == {"escalated": 0, "no_admin": 1, "notices": 0}
        assert db.get(SupportTicket, ticket["id"]).overdue_escalated_at is None

    admin = _promote_admin(client, "escalation-admin@booker.test", totp=TEST_TOTP_SECRET)
    second = _promote_admin(client, "escalation-second@booker.test", totp=TEST_TOTP_SECRET)
    with SessionLocal() as db:
        assert escalate_overdue(db, at=at) == {"escalated": 1, "no_admin": 0, "notices": 2}
        assert escalate_overdue(db, at=at) == {"escalated": 0, "no_admin": 0, "notices": 0}
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
        assert escalate_overdue(db, at=at) == {"escalated": 0, "no_admin": 0, "notices": 0}
        assert all(db.get(SupportTicket, row["id"]).overdue_escalated_at is None
                   for row in (replied, closed, future))
