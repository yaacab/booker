"""Staff handoff cannot steal or release another operator's ticket."""

from datetime import datetime, timedelta, timezone

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
    assert client.post(path, json={"action": "escalate", "target_user_id": admin["user_id"]},
                       headers={**second_headers, "If-Match": str(version)}).status_code == 409
    escalated = client.post(path, json={"action": "escalate", "target_user_id": admin["user_id"]},
                            headers={**second_headers,
                                     "If-Match": str(transferred.json()["state_version"])})
    assert escalated.status_code == 200, escalated.text
    assert escalated.json()["assigned_to_user_id"] == admin["user_id"]
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
        "support.admin.ticket.priority_changed"}
    customer_detail = client.get(f"/support/tickets/{ticket['id']}",
                                 headers=auth_header(customer["token"])).json()
    assert "assigned_to_user_id" not in customer_detail
    with client.app.state.SessionLocal() as db:
        events = db.query(AuditLog).filter(AuditLog.entity_id == ticket["id"]).all()
        actions = {row.action for row in events}
        assert "support.admin.ticket.transferred" in actions
        assert "support.admin.ticket.escalated" in actions
