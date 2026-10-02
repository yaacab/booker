"""Narrow routing for consequential booking and event problems."""

import pytest

from booker_api.support_agent import answer_support_question
from tests.conftest import auth_header, register


@pytest.mark.parametrize(
    ("question", "intent", "required", "forbidden"),
    [
        (
            "Исполнитель отменил выступление за час до события, нужна замена",
            "performer_cancelled_event",
            ("Передать человеку", "не назначает замену"),
            ("30 минут", "срочный случай дня события"),
        ),
        (
            "С карты списали деньги, а бронь всё ещё ожидает оплаты",
            "paid_not_confirmed",
            ("Не повторяйте оплату", "проверить оператор"),
            ("банк подтвердил", "деньги поступили"),
        ),
        (
            "У меня две подтверждённые брони на один слот",
            "duplicate_confirmed_booking",
            ("Передать человеку", "Не отменяйте", "не создавайте брони заново"),
            ("отмените бронь", "забронируйте заново"),
        ),
    ],
)
def test_problem_routes_need_human_without_unsafe_advice(question, intent, required, forbidden):
    reply = answer_support_question(question)
    assert (reply.intent, reply.outcome, reply.needs_human) == (intent, "needs_human", True)
    for phrase in required:
        assert phrase in reply.assistant_message
    for phrase in forbidden:
        assert phrase not in reply.assistant_message


@pytest.mark.parametrize(
    ("question", "expected_intent"),
    [
        ("Как исполнитель может отменить выступление?", "supply_profile"),
        ("Исполнитель отменил загрузку фото профиля", "supply_profile"),
        ("Исполнитель не приехал на событие", "event_day_no_show"),
        ("Как оплатить бронь с карты?", "money_or_legal"),
        ("С карты списали деньги, где чек?", "money_or_legal"),
        ("Почему бронь ожидает оплаты?", "money_or_legal"),
        ("У меня две брони на разные слоты", "booking_flow"),
        ("Как подтвердить бронь на один слот?", "booking_flow"),
    ],
)
def test_related_faq_does_not_take_problem_route(question, expected_intent):
    assert answer_support_question(question).intent == expected_intent


@pytest.mark.parametrize(
    ("message", "expected_intent", "priority", "urgency_code"),
    [
        (
            "Исполнитель отменил выступление за час до события, нужна замена",
            "performer_cancelled_event",
            "high",
            None,
        ),
        (
            "С карты списали деньги, а бронь всё ещё ожидает оплаты",
            "paid_not_confirmed",
            "high",
            "paid_not_confirmed",
        ),
        (
            "У меня две подтверждённые брони на один слот",
            "duplicate_confirmed_booking",
            "high",
            None,
        ),
    ],
)
def test_problem_handoff_uses_existing_priority_rules(
    client, message, expected_intent, priority, urgency_code
):
    user = register(client, f"problem-{expected_intent}@booker.test", "Problem User")
    headers = auth_header(user["token"])
    org = client.post("/orgs", json={"name": "Problem Org", "kind": "customer"}, headers=headers)
    assert org.status_code in {200, 201}, org.text
    session = client.post(
        "/support/assistant/sessions",
        json={"organization_id": org.json()["id"]},
        headers={**headers, "Idempotency-Key": f"{expected_intent}-session"},
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["id"]
    exchange = client.post(
        f"/support/assistant/sessions/{session_id}/messages",
        json={"message": message},
        headers={**headers, "Idempotency-Key": f"{expected_intent}-message"},
    )
    assert exchange.status_code == 201, exchange.text
    assert exchange.json()["intent"] == expected_intent
    handoff = client.post(
        f"/support/assistant/sessions/{session_id}/escalate",
        json={"reason_code": "user_requested_human"},
        headers={**headers, "Idempotency-Key": f"{expected_intent}-handoff"},
    )
    assert handoff.status_code == 200, handoff.text
    ticket = handoff.json()["ticket"]
    assert ticket["priority"] == priority
    assert ticket["urgency_code"] == urgency_code
    assert (ticket["response_due_at"] is not None) == (urgency_code is not None)
