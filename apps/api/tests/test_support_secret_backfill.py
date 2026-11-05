import json
from datetime import datetime, timezone

import pytest

from booker_api.models import (
    SupportAgentExchange,
    SupportAgentFeedback,
    SupportAgentSession,
    SupportMessage,
    SupportOperatorNote,
    SupportTicket,
)
from booker_api.routers.trust import _fingerprint
from booker_api.support_secret_backfill import sanitize_support_scope
from tests.conftest import auth_header, register
from tests.test_support_agent import _create_org, _create_session, _send

PLAN_KEY = b"booker-test-support-backfill-key-32bytes"


def sanitize(db, **kwargs):
    return sanitize_support_scope(db, plan_key=PLAN_KEY, **kwargs)


def _ticket(client, user, org_id, key, subject, body):
    response = client.post(
        "/support/tickets",
        json={"organization_id": org_id, "category": "technical", "subject": subject, "body": body},
        headers={**auth_header(user["token"]), "Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_scoped_support_secret_backfill_dry_run_apply_and_replay(
    client, SessionLocal, monkeypatch, capsys
):
    first = register(client, "backfill-first@booker.test", "First")
    second = register(client, "backfill-second@booker.test", "Second")
    org_a = _create_org(client, first, "Backfill A")
    org_b = _create_org(client, second, "Backfill B")
    session_a = _create_session(client, first, org_a["id"], "backfill-session-a")
    session_b = _create_session(client, second, org_b["id"], "backfill-session-b")
    token = "sk_live_ABC123def456ghi789"
    raw_message = f"Не могу войти с {token}"
    exchange_a = _send(client, first, session_a["id"], raw_message, "backfill-exchange-a")
    exchange_b = _send(client, second, session_b["id"], raw_message, "backfill-exchange-b")
    escalated = client.post(
        f"/support/assistant/sessions/{session_a['id']}/escalate",
        json={"reason_code": "account_security"},
        headers={**auth_header(first["token"]), "Idempotency-Key": "backfill-escalate-a"},
    )
    assert escalated.status_code == 200, escalated.text
    manual = _ticket(
        client, first, org_a["id"], "backfill-manual-a",
        f"Помощь с {token}", f"Проблема с {token}",
    )
    with SessionLocal() as db:
        exchange = db.get(SupportAgentExchange, exchange_a["id"])
        exchange.user_message = raw_message
        exchange.assistant_message = f"Ответ про {token}"
        exchange.request_fingerprint = _fingerprint({"message": raw_message})
        db.add(SupportAgentFeedback(
            exchange_id=exchange.id, user_id=first["user_id"],
            rating="not_helpful", comment=f"Комментарий {token}",
        ))
        escalated_ticket = db.get(SupportTicket, escalated.json()["ticket"]["id"])
        escalated_ticket.body = f"Передача из помощника: {token}"
        escalated_ticket.request_fingerprint = _fingerprint({"body": escalated_ticket.body})
        manual_ticket = db.get(SupportTicket, manual["id"])
        manual_ticket.subject = f"Помощь с {token}"
        manual_ticket.body = f"Проблема с {token}"
        manual_ticket.request_fingerprint = _fingerprint({"subject": manual_ticket.subject, "body": manual_ticket.body})
        for message in db.query(SupportMessage).filter(SupportMessage.ticket_id.in_((manual["id"], escalated_ticket.id))):
            message.body = db.get(SupportTicket, message.ticket_id).body
            message.request_fingerprint = _fingerprint({"body": message.body})
        db.add(SupportOperatorNote(
            ticket_id=manual["id"], author_user_id=first["user_id"],
            body=f"Заметка {token}", idempotency_key_hash="backfill-note-key",
            request_fingerprint=_fingerprint({"body": f"Заметка {token}"}),
        ))
        other = db.get(SupportAgentExchange, exchange_b["id"])
        other.user_message = raw_message
        other.request_fingerprint = _fingerprint({"message": raw_message})
        db.commit()

    with SessionLocal() as db:
        report = sanitize(db, organization_id=org_a["id"])
        assert report["changed_fields"] > 0
        assert report["copy_mismatches_after_sanitization"] == 0
        assert token not in json.dumps(report)
        assert db.get(SupportAgentExchange, exchange_a["id"]).user_message == raw_message
    from booker_api import support_secret_backfill

    monkeypatch.setattr(support_secret_backfill, "SessionLocal", SessionLocal)
    monkeypatch.setenv("BOOKER_SUPPORT_BACKFILL_PLAN_KEY", PLAN_KEY.decode())
    assert support_secret_backfill.main(["--organization-id", org_a["id"]]) == 0
    captured = capsys.readouterr()
    assert token not in captured.out + captured.err
    assert json.loads(captured.out)["changed_fields"] == report["changed_fields"]
    with monkeypatch.context() as patch:
        def fail_with_sensitive_detail(*_args, **_kwargs):
            raise ValueError(token)

        patch.setattr(support_secret_backfill, "sanitize_support_scope", fail_with_sensitive_detail)
        assert support_secret_backfill.main(["--organization-id", org_a["id"]]) == 2
    captured = capsys.readouterr()
    assert token not in captured.out + captured.err
    with SessionLocal() as db:
        with pytest.raises(ValueError, match="reviewed plan"):
            sanitize(
                db, organization_id=org_a["id"], apply=True,
                expected_changes=report["changed_fields"] + 1,
                expected_plan_token=report["plan_token"],
            )
        assert db.get(SupportAgentExchange, exchange_a["id"]).user_message == raw_message
    with SessionLocal() as db:
        changed = db.get(SupportAgentExchange, exchange_a["id"])
        changed.assistant_message = f"Другой ответ про {token}"
        db.commit()
    with SessionLocal() as db, pytest.raises(ValueError, match="reviewed plan"):
        sanitize(
            db, organization_id=org_a["id"], apply=True,
            expected_changes=report["changed_fields"],
            expected_plan_token=report["plan_token"],
        )
    with SessionLocal() as db:
        changed = db.get(SupportAgentExchange, exchange_a["id"])
        assert token in changed.assistant_message
        changed.assistant_message = f"Ответ про {token}"
        db.commit()
    with SessionLocal() as db:
        applied = sanitize(
            db, organization_id=org_a["id"], apply=True,
            expected_changes=report["changed_fields"],
            expected_plan_token=report["plan_token"],
        )
        assert applied["changed_fields"] == report["changed_fields"]
        assert token not in json.dumps(applied)
        a = db.get(SupportAgentExchange, exchange_a["id"])
        b = db.get(SupportAgentExchange, exchange_b["id"])
        assert token not in a.user_message + a.assistant_message
        assert b.user_message == raw_message
        assert a.request_fingerprint == _fingerprint({"message": a.user_message})
        message_bodies = [
            row.body for row in db.query(SupportMessage).filter(
                SupportMessage.ticket_id.in_((manual["id"], escalated.json()["ticket"]["id"]))
            ).all()
        ]
        assert all(token not in value for value in (
            db.get(SupportTicket, manual["id"]).subject,
            db.get(SupportTicket, manual["id"]).body,
            db.get(SupportTicket, escalated.json()["ticket"]["id"]).body,
            *message_bodies,
            db.query(SupportOperatorNote).one().body,
            db.query(SupportAgentFeedback).one().comment,
        ))
        assert db.get(SupportTicket, escalated.json()["ticket"]["id"]).request_fingerprint is None
    with SessionLocal() as db:
        empty_plan = sanitize(db, organization_id=org_a["id"])
        assert empty_plan["changed_fields"] == 0
    with SessionLocal() as db:
        assert sanitize(
            db, organization_id=org_a["id"], apply=True, expected_changes=0,
            expected_plan_token=empty_plan["plan_token"],
        )["changed_fields"] == 0

    replay = client.post(
        f"/support/assistant/sessions/{session_a['id']}/messages",
        json={"message": raw_message},
        headers={**auth_header(first["token"]), "Idempotency-Key": "backfill-exchange-a"},
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == exchange_a["id"]


def test_unscoped_user_backfill_and_scope_validation(client, SessionLocal):
    user = register(client, "backfill-unscoped@booker.test", "Unscoped")
    token = "sk_live_ABC123def456ghi789"
    ticket = _ticket(client, user, None, "backfill-unscoped-ticket", "Личное обращение", "Нужна помощь")
    with SessionLocal() as db:
        row = db.get(SupportTicket, ticket["id"])
        row.body = f"Нужна помощь {token}"
        message = db.query(SupportMessage).filter_by(ticket_id=ticket["id"]).one()
        message.body = row.body
        db.commit()
    with SessionLocal() as db:
        with pytest.raises(ValueError):
            sanitize(db)
        with pytest.raises(ValueError):
            sanitize(db, organization_id="x", unscoped_user_id=user["user_id"])
        report = sanitize(db, unscoped_user_id=user["user_id"])
        assert report["changed_fields"] > 0
        sanitize(
            db, unscoped_user_id=user["user_id"], apply=True,
            expected_changes=report["changed_fields"],
            expected_plan_token=report["plan_token"],
        )
        assert token not in db.get(SupportTicket, ticket["id"]).body


def test_backfill_rejects_cross_tenant_escalation_link_without_writes(client, SessionLocal):
    first = register(client, "backfill-link-first@booker.test", "First")
    second = register(client, "backfill-link-second@booker.test", "Second")
    org_a = _create_org(client, first, "Link A")
    org_b = _create_org(client, second, "Link B")
    session = _create_session(client, first, org_a["id"], "backfill-cross-link-session")
    exchange = _send(client, first, session["id"], "Не могу войти", "backfill-cross-link-message")
    ticket = _ticket(client, second, org_b["id"], "backfill-cross-link-ticket", "Вопрос", "Нужна помощь")
    token = "sk_live_ABC123def456ghi789"
    with SessionLocal() as db:
        row = db.get(SupportAgentSession, session["id"])
        row.status = "escalated"
        row.ticket_id = ticket["id"]
        row.escalated_at = datetime.now(timezone.utc)
        db.get(SupportAgentExchange, exchange["id"]).user_message = f"Не могу войти с {token}"
        db.commit()
    with SessionLocal() as db:
        with pytest.raises(ValueError, match="cross tenant"):
            sanitize(
                db, organization_id=org_a["id"], apply=True,
                expected_changes=1, expected_plan_token="0" * 64,
            )
        db.rollback()
    with SessionLocal() as db:
        assert token in db.get(SupportAgentExchange, exchange["id"]).user_message
        assert db.get(SupportTicket, ticket["id"]).organization_id == org_b["id"]


def test_backfill_rejects_dirty_caller_session(client, SessionLocal):
    user = register(client, "backfill-dirty@booker.test", "Dirty")
    ticket = _ticket(client, user, None, "backfill-dirty-ticket", "Вопрос", "Помощь")
    with SessionLocal() as db:
        row = db.get(SupportTicket, ticket["id"])
        row.body = "Пока не коммитить"
        with pytest.raises(ValueError, match="fresh session"):
            sanitize(db, unscoped_user_id=user["user_id"])
        assert row.body == "Пока не коммитить"
        assert db.in_transaction()
        db.rollback()
    with SessionLocal() as db:
        assert db.get(SupportTicket, ticket["id"]).body == "Помощь"


def test_backfill_blocks_divergent_ticket_message_copies(client, SessionLocal):
    user = register(client, "backfill-copy@booker.test", "Copy")
    ticket = _ticket(client, user, None, "backfill-copy-ticket", "Вопрос", "Помощь")
    token = "sk_live_ABC123def456ghi789"
    with SessionLocal() as db:
        db.get(SupportTicket, ticket["id"]).body = f"Помощь {token}"
        db.commit()
    with SessionLocal() as db:
        report = sanitize(db, unscoped_user_id=user["user_id"])
        assert report["copy_mismatches_after_sanitization"] == 1
    with SessionLocal() as db, pytest.raises(ValueError, match="reviewed plan"):
        sanitize(
            db, unscoped_user_id=user["user_id"], apply=True,
            expected_changes=report["changed_fields"],
            expected_plan_token=report["plan_token"],
        )
    with SessionLocal() as db:
        assert token in db.get(SupportTicket, ticket["id"]).body
