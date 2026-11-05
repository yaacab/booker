import pytest

from booker_api.models import SupportMessage, SupportTicket
from booker_api.rate_limit import support_agent_limiter
from booker_api.support_agent import answer_support_question
from tests.conftest import auth_header, register


def _session(client, label):
    user = register(client, f"handoff-{label}@booker.test", "Handoff User")
    headers = auth_header(user["token"])
    org_response = client.post(
        "/orgs", json={"name": f"Handoff {label}", "kind": "customer"}, headers=headers
    )
    assert org_response.status_code in {200, 201}, org_response.text
    session_response = client.post(
        "/support/assistant/sessions",
        json={"organization_id": org_response.json()["id"]},
        headers={**headers, "Idempotency-Key": f"handoff-{label}-session"},
    )
    assert session_response.status_code == 201, session_response.text
    return user, session_response.json()["id"]


def _send(client, user, session_id, message, key):
    response = client.post(
        f"/support/assistant/sessions/{session_id}/messages",
        json={"message": message},
        headers={**auth_header(user["token"]), "Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _handoff(client, user, session_id, key):
    response = client.post(
        f"/support/assistant/sessions/{session_id}/escalate",
        json={"reason_code": "event_day_no_show"},
        headers={**auth_header(user["token"]), "Idempotency-Key": key},
    )
    assert response.status_code == 200, response.text
    return response.json()["ticket"]


def test_early_code_delivery_cue_does_not_hide_middle_no_show_in_handoff(client, SessionLocal):
    user, session_id = _session(client, "middle")
    marker = "исполнитель не приехал на событие, гости уже ждут"
    message = "Код не пришёл. " + ("подробности " * 160) + marker + (" уточнения" * 170)
    assert len(message) <= 4000
    exchange = _send(client, user, session_id, message, "handoff-middle-urgent")
    assert exchange["intent"] == "event_day_no_show"
    for index in range(5):
        if index == 4:
            support_agent_limiter.reset()
        _send(
            client, user, session_id, f"Не загружается файл {index}",
            f"handoff-middle-followup-{index}",
        )
    ticket = _handoff(client, user, session_id, "handoff-middle-escalate")
    assert ticket["priority"] == "urgent"
    with SessionLocal() as db:
        body = db.query(SupportTicket).one().body
        assert "Код не пришёл" in body
        assert marker in body
        assert "Последний вопрос" in body
        assert "середина сообщения пропущена" in body
        assert "История сокращена" in body
        assert len(body) <= 8000
        assert db.query(SupportMessage).one().body == body


@pytest.mark.parametrize(
    ("followups", "expected_priority"),
    [
        (["Он приехал, помощь больше не нужна"], "normal"),
        (["Он приехал? Помощь больше не нужна"], "urgent"),
        (["Он приехал, помощь больше не нужна", "Исполнитель не приехал на событие"], "urgent"),
    ],
)
def test_no_show_resolution_only_clears_earlier_incident(
    client, SessionLocal, followups, expected_priority
):
    label = "resolved" if expected_priority == "normal" else f"open-{len(followups)}"
    user, session_id = _session(client, label)
    first = _send(
        client, user, session_id, "Фотограф на мероприятие сегодня не приехал",
        f"handoff-{label}-first",
    )
    assert first["intent"] == "event_day_no_show"
    for index, message in enumerate(followups):
        _send(client, user, session_id, message, f"handoff-{label}-followup-{index}")
    ticket = _handoff(client, user, session_id, f"handoff-{label}-escalate")
    assert ticket["priority"] == expected_priority
    assert ticket["urgency_code"] == (
        "event_day_no_show" if expected_priority == "urgent" else None
    )
    assert (ticket["response_due_at"] is not None) == (expected_priority == "urgent")
    with SessionLocal() as db:
        assert db.query(SupportTicket).one().priority == expected_priority


def test_later_no_show_in_same_message_remains_urgent(client, SessionLocal):
    message = (
        "Фотограф не приехал, но потом приехал и выступил. "
        + ("подробности " * 130)
        + "Ведущий не пришёл на событие, гости ждут. "
        + ("уточнения " * 130)
    )
    assert len(message) < 4000
    assert answer_support_question(message).intent == "event_day_no_show"
    user, session_id = _session(client, "second-no-show")
    exchange = _send(client, user, session_id, message, "second-no-show-message")
    assert exchange["intent"] == "event_day_no_show"
    _send(client, user, session_id, "Нужна помощь с мероприятием", "second-no-show-followup")
    ticket = _handoff(client, user, session_id, "second-no-show-escalate")
    assert (ticket["priority"], ticket["urgency_code"]) == ("urgent", "event_day_no_show")
    with SessionLocal() as db:
        body = db.query(SupportTicket).one().body
        assert "Ведущий не пришёл на событие, гости ждут" in body
        assert "Нужна помощь с мероприятием" in body


def test_resolved_no_show_does_not_displace_active_payment_handoff(client, SessionLocal):
    user, session_id = _session(client, "resolved-and-paid")
    _send(client, user, session_id, "Фотограф не приехал", "resolved-paid-no-show")
    _send(client, user, session_id, "Он приехал, помощь больше не нужна", "resolved-paid-arrived")
    payment = "С карты списали деньги, а бронь всё ещё ожидает оплаты"
    _send(client, user, session_id, payment, "resolved-paid-payment")
    for index in range(5):
        if index == 2:
            support_agent_limiter.reset()
        _send(
            client,
            user,
            session_id,
            f"Не загружается файл {index}: " + ("детали " * 90),
            f"resolved-paid-followup-{index}",
        )
    latest = "Последний вопрос: не работает загрузка видео. " + ("подробности " * 300)
    assert len(latest) < 4000
    support_agent_limiter.reset()
    _send(client, user, session_id, latest, "resolved-paid-latest")
    ticket = _handoff(client, user, session_id, "resolved-paid-escalate")
    assert (ticket["priority"], ticket["urgency_code"]) == ("high", "paid_not_confirmed")
    with SessionLocal() as db:
        stored = db.query(SupportTicket).one()
        assert stored.category == "payment"
        assert payment in stored.body
        assert "Последний вопрос: не работает загрузка видео" in stored.body
        assert len(stored.body) <= 8000
        assert db.query(SupportMessage).one().body == stored.body
