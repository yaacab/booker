"""Staff handoff cannot steal or release another operator's ticket."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from booker_api.models import AuditLog, SupportTicket, User
from booker_api.security import aware, now
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_support_security import _ticket_payload
from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers, totp_code


def _operator(client, admin_headers, email, name):
    user = register(client, email, name)
    with client.app.state.SessionLocal() as db:
        row = db.get(User, user["user_id"])
        row.email_verified_at = now()
        db.commit()
    grant = client.post("/admin/support/operators", json={"email": email, "enabled": True},
                        headers=admin_headers)
    assert grant.status_code == 200, grant.text
    with client.app.state.SessionLocal() as db:
        row = db.get(User, user["user_id"])
        row.totp_enabled = True
        row.totp_secret = TEST_TOTP_SECRET
        db.commit()
    login = client.post("/auth/login", json={
        "email": email, "password": "password1", "totp": totp_code(),
    })
    assert login.status_code == 200, login.text
    return {**user, "token": login.json()["token"]}


def test_support_handoff_and_escalation_require_owner_eligible_target_and_cas(client):
    admin = _promote_admin(client, "handoff-admin@booker.test", totp=TEST_TOTP_SECRET)
    admin_headers = admin_totp_headers(admin["token"])
    first = _operator(client, admin_headers, "handoff-first@booker.test", "Первый оператор")
    second = _operator(client, admin_headers, "handoff-second@booker.test", "Второй оператор")
    customer = register(client, "handoff-customer@booker.test")
    ticket = client.post("/support/tickets", json=_ticket_payload(category="technical"),
                         headers={**auth_header(customer["token"]),
                                  "Idempotency-Key": "handoff-ticket-1"}).json()
    path = f"/admin/support/tickets/{ticket['id']}/assign"
    first_headers = auth_header(first["token"])
    second_headers = auth_header(second["token"])

    assert client.get("/admin/support/staff", headers=auth_header(customer["token"])).status_code == 403
    staff = client.get("/admin/support/staff", headers=first_headers)
    assert staff.status_code == 200, staff.text
    assert {row["id"] for row in staff.json()["items"]} >= {
        first["user_id"], second["user_id"], admin["user_id"]}
    assert "email" not in str(staff.json())

    taken = client.post(path, json={"action": "take"},
                        headers={**first_headers, "If-Match": str(ticket["state_version"])})
    assert taken.status_code == 200, taken.text
    assert taken.json()["accepted_by_user_id"] == first["user_id"]
    assert taken.json()["accepted_at"]
    version = taken.json()["state_version"]
    for action in ("take", "release"):
        blocked = client.post(path, json={"action": action},
                              headers={**second_headers, "If-Match": str(version)})
        assert blocked.status_code in {403, 409}
    assert client.post(path, json={"action": "transfer", "target_user_id": second["user_id"]},
                       headers={**second_headers, "If-Match": str(version)}).status_code == 403
    assert client.post(path, json={"action": "transfer", "target_user_id": customer["user_id"]},
                       headers={**first_headers, "If-Match": str(version)}).status_code == 409
    assert client.post(path, json={"action": "escalate", "target_user_id": second["user_id"]},
                       headers={**first_headers, "If-Match": str(version)}).status_code == 422
    with client.app.state.SessionLocal() as db:
        db.get(User, second["user_id"]).totp_enabled = False
        db.commit()
    assert client.post(path, json={"action": "transfer", "target_user_id": second["user_id"]},
                       headers={**first_headers, "If-Match": str(version)}).status_code == 409
    with client.app.state.SessionLocal() as db:
        db.get(User, second["user_id"]).totp_enabled = True
        db.commit()

    transferred = client.post(path, json={"action": "transfer", "target_user_id": second["user_id"]},
                              headers={**first_headers, "If-Match": str(version)})
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["assigned_to_user_id"] == second["user_id"]
    assert transferred.json()["accepted_by_user_id"] is None
    assert transferred.json()["accepted_at"] is None
    second_accepts = client.post(path, json={"action": "take"},
                                 headers={**second_headers,
                                          "If-Match": str(transferred.json()["state_version"])})
    assert second_accepts.status_code == 200, second_accepts.text
    assert second_accepts.json()["accepted_by_user_id"] == second["user_id"]
    replay = client.post(path, json={"action": "take"},
                         headers={**second_headers,
                                  "If-Match": str(second_accepts.json()["state_version"])})
    assert replay.status_code == 200 and replay.json()["idempotent"] is True
    assert replay.json()["state_version"] == second_accepts.json()["state_version"]
    assert client.post(path, json={"action": "escalate", "target_user_id": admin["user_id"]},
                       headers={**second_headers, "If-Match": str(version)}).status_code == 409
    escalated = client.post(path, json={"action": "escalate", "target_user_id": admin["user_id"]},
                            headers={**second_headers,
                                     "If-Match": str(second_accepts.json()["state_version"])})
    assert escalated.status_code == 200, escalated.text
    assert escalated.json()["assigned_to_user_id"] == admin["user_id"]
    assert escalated.json()["accepted_at"] is None
    due_at = datetime.now(timezone.utc) + timedelta(hours=2)
    with client.app.state.SessionLocal() as db:
        db.get(SupportTicket, ticket["id"]).response_due_at = due_at
        db.commit()
    priority_path = f"/admin/support/tickets/{ticket['id']}/priority"
    assert client.post(priority_path, json={"priority": "urgent"},
                       headers=auth_header(customer["token"])).status_code == 403
    priority = client.post(priority_path, json={"priority": "urgent"},
                           headers={**first_headers,
                                    "If-Match": str(escalated.json()["state_version"])})
    assert priority.status_code == 200, priority.text
    assert client.post(priority_path, json={"priority": "normal"},
                       headers={**first_headers,
                                "If-Match": str(escalated.json()["state_version"])}).status_code == 409
    with client.app.state.SessionLocal() as db:
        row = db.get(SupportTicket, ticket["id"])
        assert row.priority == "urgent"
        assert aware(row.response_due_at) == due_at
    detail = client.get(f"/admin/support/tickets/{ticket['id']}", headers=first_headers).json()
    assert {event["action"] for event in detail["system_events"]} >= {
        "support.admin.ticket.transferred", "support.admin.ticket.escalated",
        "support.admin.ticket.priority_changed", "support.admin.ticket.accepted"}
    customer_detail = client.get(f"/support/tickets/{ticket['id']}",
                                 headers=auth_header(customer["token"])).json()
    assert "assigned_to_user_id" not in customer_detail
    assert "accepted_by_user_id" not in customer_detail
    assert "accepted_at" not in customer_detail
    with client.app.state.SessionLocal() as db:
        events = db.query(AuditLog).filter(AuditLog.entity_id == ticket["id"]).all()
        actions = {row.action for row in events}
        assert "support.admin.ticket.transferred" in actions
        assert "support.admin.ticket.escalated" in actions


def test_reopened_ticket_requires_new_explicit_acceptance(client):
    admin = _promote_admin(client, "accept-reopen-admin@booker.test", totp=TEST_TOTP_SECRET)
    customer = register(client, "accept-reopen-customer@booker.test")
    ticket = client.post("/support/tickets", json=_ticket_payload(category="technical"),
                         headers={**auth_header(customer["token"]),
                                  "Idempotency-Key": "accept-reopen-ticket"}).json()
    path = f"/admin/support/tickets/{ticket['id']}"
    taken = client.post(f"{path}/assign", json={"action": "take"},
                        headers={**admin_totp_headers(admin["token"]),
                                 "If-Match": str(ticket["state_version"])})
    assert taken.status_code == 200
    closed = client.post(f"{path}/close", headers={
        **admin_totp_headers(admin["token"]),
        "If-Match": str(taken.json()["state_version"]),
    })
    assert closed.status_code == 200, closed.text
    reopened = client.post(f"{path}/reopen", headers={
        **admin_totp_headers(admin["token"]),
        "If-Match": str(closed.json()["state_version"]),
    })
    assert reopened.status_code == 200, reopened.text
    detail = client.get(path, headers=auth_header(admin["token"]))
    assert detail.status_code == 200
    assert detail.json()["assigned_to_user_id"] == admin["user_id"]
    assert detail.json()["accepted_by_user_id"] is None
    assert detail.json()["accepted_at"] is None
    accepted = client.post(f"{path}/assign", json={"action": "take"},
                           headers={**admin_totp_headers(admin["token"]),
                                    "If-Match": str(reopened.json()["state_version"])})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["accepted_by_user_id"] == admin["user_id"]


def test_sqlite_runtime_rejects_unpaired_acceptance(client, SessionLocal):
    customer = register(client, "accept-guard-customer@booker.test")
    ticket = client.post("/support/tickets", json=_ticket_payload(category="technical"),
                         headers={**auth_header(customer["token"]),
                                  "Idempotency-Key": "accept-guard-ticket"}).json()
    with SessionLocal() as db:
        triggers = {row[0] for row in db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ))}
        assert {"support_ticket_acceptance_insert", "support_ticket_acceptance_update"} <= triggers
        with pytest.raises(IntegrityError):
            db.execute(text(
                "UPDATE support_tickets SET accepted_by_user_id = :actor WHERE id = :ticket"
            ), {"actor": customer["user_id"], "ticket": ticket["id"]})
        db.rollback()
    with SessionLocal() as db:
        row = db.get(SupportTicket, ticket["id"])
        assert row.accepted_at is None and row.accepted_by_user_id is None
