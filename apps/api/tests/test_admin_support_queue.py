"""Bounded operator queue, assignment CAS, and private detail contract."""

from datetime import datetime, timedelta, timezone

from booker_api.models import SupportTicket
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_support_security import _ticket_payload
from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers


def _create(client, user, key: str, subject: str):
    response = client.post(
        "/support/tickets",
        json=_ticket_payload(category="incident", subject=subject),
        headers={**auth_header(user["token"]), "Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_queue_filters_paginates_assigns_and_preserves_private_history(client):
    owner = register(client, "support-queue-owner@booker.test")
    admin = _promote_admin(client, "support-queue-admin@booker.test", totp=TEST_TOTP_SECRET)
    first = _create(client, owner, "queue-ticket-first", "Срочно: исполнитель не приехал")
    second = _create(client, owner, "queue-ticket-second", "Обычный вопрос")
    with client.app.state.SessionLocal() as db:
        urgent = db.get(SupportTicket, first["id"])
        urgent.priority = "urgent"
        urgent.response_due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        regular = db.get(SupportTicket, second["id"])
        regular.priority = "normal"
        db.commit()

    assert client.get("/admin/support/tickets", headers=auth_header(owner["token"])).status_code == 403
    assert client.get(
        "/admin/support/tickets",
        headers=auth_header(admin["pre_promotion_token"]),
    ).status_code == 403
    headers = admin_totp_headers(admin["token"])
    page = client.get("/admin/support/tickets?limit=1&offset=0", headers=headers)
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 2 and page.json()["overdue_count"] == 1
    assert page.json()["items"][0]["id"] == first["id"]
    next_page = client.get("/admin/support/tickets?limit=1&offset=1", headers=headers)
    assert next_page.json()["items"][0]["id"] == second["id"]
    overdue = client.get(
        "/admin/support/tickets?state=active&overdue_only=true&priority=urgent&category=incident",
        headers=headers,
    )
    assert overdue.json()["total"] == 1
    assert overdue.json()["items"][0]["response_overdue"] is True
    assert client.get("/admin/support/tickets?limit=51", headers=headers).status_code == 422

    assigned = client.post(
        f"/admin/support/tickets/{first['id']}/assign", json={"action": "take"},
        headers={**headers, "If-Match": str(first["state_version"])},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assigned_to_user_id"] == admin["user_id"]
    assert client.post(f"/admin/support/tickets/{first['id']}/assign",
                       json={"action": "release"},
                       headers={**headers, "If-Match": str(first["state_version"])}).status_code == 409
    mine = client.get("/admin/support/tickets?assigned_to_me=true", headers=headers).json()
    assert mine["total"] == 1 and mine["items"][0]["id"] == first["id"]
    user_detail = client.get(f"/support/tickets/{first['id']}",
                             headers=auth_header(owner["token"])).json()
    assert "assigned_to_user_id" not in user_detail

    reply_headers = {**headers, "If-Match": str(assigned.json()["state_version"]),
                     "Idempotency-Key": "queue-operator-reply-1"}
    reply_url = f"/admin/support/tickets/{first['id']}/messages"
    reply = client.post(reply_url, json={"body": "Проверяем инцидент"}, headers=reply_headers)
    assert reply.status_code == 201, reply.text
    replay = client.post(reply_url, json={"body": "Проверяем инцидент"}, headers=reply_headers)
    assert replay.status_code == 201 and replay.json()["id"] == reply.json()["id"]
    assert client.post(reply_url, json={"body": "Новое сообщение"},
                       headers={**reply_headers, "Idempotency-Key": "queue-operator-reply-2"}
                       ).status_code == 409
    note = client.post(
        f"/admin/support/tickets/{first['id']}/notes",
        json={"body": "Внутренняя проверка"},
        headers={**headers, "Idempotency-Key": "queue-private-note-1"},
    )
    assert note.status_code == 201, note.text
    detail = client.get(f"/admin/support/tickets/{first['id']}", headers=headers).json()
    assert any(row["actor_user_id"] == admin["user_id"] for row in detail["messages"])
    assert any(row["action"] == "support.admin.ticket.assigned" for row in detail["system_events"])
    assert detail["system_events_truncated"] is False
    customer_detail = client.get(f"/support/tickets/{first['id']}",
                                 headers=auth_header(owner["token"])).json()
    assert any(row["body"] == "Проверяем инцидент" for row in customer_detail["messages"])
    assert "Внутренняя проверка" not in str(customer_detail)
    assert client.get(f"/admin/support/tickets/{first['id']}/notes",
                      headers=auth_header(owner["token"])).status_code == 403

    closed = client.post(f"/admin/support/tickets/{first['id']}/close",
                         headers={**headers, "If-Match": str(detail["state_version"])})
    assert closed.status_code == 200, closed.text
    assert client.post(f"/admin/support/tickets/{first['id']}/reopen",
                       headers={**headers, "If-Match": str(detail["state_version"])}).status_code == 409
    reopened = client.post(f"/admin/support/tickets/{first['id']}/reopen",
                           headers={**headers, "If-Match": str(closed.json()["state_version"])})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["state_version"] == closed.json()["state_version"] + 1
