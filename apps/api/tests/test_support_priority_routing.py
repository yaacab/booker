"""Sensitive support handoffs are visible without inventing an SLA."""

import pytest

from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_support_agent import _create_org, _create_session, _send
from tests.test_support_security import _ticket_payload
from tests.totp_helpers import TEST_TOTP_SECRET


@pytest.mark.parametrize(
    ("message", "intent", "category"),
    [
        ("Фотограф внезапно отменил выступление", "performer_cancelled_event", "incident"),
        ("Две подтверждённые брони на один и тот же слот",
         "duplicate_confirmed_booking", "incident"),
        ("Мой аккаунт взломали", "account_security", "profile"),
    ],
)
def test_sensitive_handoff_is_high_priority_without_unapproved_due_date(
    client, message, intent, category,
):
    admin = _promote_admin(client, f"priority-admin-{intent}@booker.test",
                           totp=TEST_TOTP_SECRET)
    customer = register(client, f"priority-customer-{intent}@booker.test")
    org = _create_org(client, customer, f"Priority {intent}")
    session = _create_session(client, customer, org["id"], f"priority-session-{intent}")
    exchange = _send(client, customer, session["id"], message, f"priority-message-{intent}")
    assert exchange["intent"] == intent
    assert exchange["needs_human"] is True
    result = client.post(
        f"/support/assistant/sessions/{session['id']}/escalate",
        json={"reason_code": "user_requested_human"},
        headers={**auth_header(customer["token"]),
                 "Idempotency-Key": f"priority-escalate-{intent}"},
    )
    assert result.status_code == 200, result.text
    ticket = result.json()["ticket"]
    assert ticket["category"] == category
    assert ticket["priority"] == "high"
    assert ticket["urgency_code"] is None
    assert ticket["response_due_at"] is None
    inbox = client.get("/notifications", headers=auth_header(admin["token"]))
    assert any(item["template"] == "support.ticket.urgent"
               and item["entity_id"] == ticket["id"] for item in inbox.json()["items"])


def test_manual_duplicate_booking_ticket_gets_high_priority_without_sla(client):
    customer = register(client, "priority-manual-customer@booker.test")
    result = client.post(
        "/support/tickets",
        json=_ticket_payload(body="Две подтверждённые брони на один и тот же слот"),
        headers={**auth_header(customer["token"]),
                 "Idempotency-Key": "priority-manual-duplicate"},
    )
    assert result.status_code == 201, result.text
    assert result.json()["priority"] == "high"
    assert result.json()["response_due_at"] is None
