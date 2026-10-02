"""Sensitive support handoffs are visible without inventing an SLA."""

import pytest

from booker_api.support_agent import answer_support_question
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


@pytest.mark.parametrize(
    ("message", "intent", "category", "priority"),
    [
        ("Меня взломали, нужен оператор", "account_security", "profile", "high"),
        ("Нужен возврат оплаты и оператор", "money_or_legal", "payment", "normal"),
        ("Не могу войти, нужен оператор", "account_access", "profile", "normal"),
    ],
)
def test_explicit_human_request_preserves_issue_and_routes_handoff(
    client, message, intent, category, priority,
):
    customer = register(client, f"human-intent-{intent}@booker.test")
    org = _create_org(client, customer, f"Human {intent}")
    session = _create_session(client, customer, org["id"], f"human-session-{intent}")
    exchange = _send(client, customer, session["id"], message, f"human-message-{intent}")
    assert exchange["intent"] == intent
    assert exchange["needs_human"] is True
    assert exchange["outcome"] == "needs_human"
    result = client.post(
        f"/support/assistant/sessions/{session['id']}/escalate",
        json={"reason_code": "user_requested_human"},
        headers={**auth_header(customer["token"]),
                 "Idempotency-Key": f"human-escalate-{intent}"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["ticket"]["category"] == category
    assert result.json()["ticket"]["priority"] == priority


def test_standalone_human_request_keeps_explicit_handoff():
    reply = answer_support_question("Позовите оператора")
    assert reply.intent == "human_request"
    assert reply.needs_human is True


@pytest.mark.parametrize(
    ("message", "intent", "category"),
    [
        ("Не пришёл код для входа, нужен оператор", "code_delivery", "profile"),
        ("Не открывается документ, нужен оператор", "deal_documents", "technical"),
        ("Не вижу профиль площадки, нужен оператор", "supply_profile", "profile"),
        ("Не работает приглашение в организацию, нужен оператор",
         "organization_invitation", "profile"),
        ("Курьер не приехал, нужен оператор", "arrival_unclear", "incident"),
    ],
)
def test_known_support_issues_keep_categories_on_explicit_handoff(
    client, message, intent, category,
):
    customer = register(client, f"known-intent-{intent}@booker.test")
    org = _create_org(client, customer, f"Known {intent}")
    session = _create_session(client, customer, org["id"], f"known-session-{intent}")
    exchange = _send(client, customer, session["id"], message, f"known-message-{intent}")
    assert exchange["intent"] == intent
    assert exchange["needs_human"] is True
    result = client.post(
        f"/support/assistant/sessions/{session['id']}/escalate",
        json={"reason_code": "user_requested_human"},
        headers={**auth_header(customer["token"]),
                 "Idempotency-Key": f"known-escalate-{intent}"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["ticket"]["category"] == category
