import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from booker_api.config import settings
from booker_api.models import (
    AuditLog,
    AvailabilitySlot,
    Booking,
    Conversation,
    Event,
    Message,
    Offer,
    Payment,
    Request,
    SupportMessage,
    SupportOperatorNote,
    SupportTicket,
    TeamMember,
)
from booker_api.routers.trust import _cas_ticket_status
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers


def _create_org(client, user: dict, name: str, kind: str = "customer") -> dict:
    response = client.post(
        "/orgs",
        json={"name": name, "kind": kind},
        headers=auth_header(user["token"]),
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _ticket_payload(org_id: str | None = None, **overrides) -> dict:
    payload = {
        "organization_id": org_id,
        "category": "technical",
        "subject": "Не работает сценарий",
        "body": "Нужна помощь оператора",
    }
    payload.update(overrides)
    return payload


def _create_ticket(client, user: dict, org_id: str | None, key: str = "ticket-key-0001"):
    response = client.post(
        "/support/tickets",
        json=_ticket_payload(org_id),
        headers={**auth_header(user["token"]), "Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_related_graph(SessionLocal, customer_org_id: str, supplier_org_id: str) -> dict[str, str]:
    with SessionLocal() as db:
        event = Event(
            organization_id=customer_org_id,
            title="Support ACL event",
            event_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(event)
        db.flush()
        request_row = Request(
            event_id=event.id,
            resource_type="artist",
            resource_id="support-resource",
            supplier_org_id=supplier_org_id,
        )
        db.add(request_row)
        db.flush()
        offer = Offer(request_id=request_row.id)
        slot = AvailabilitySlot(
            resource_type="artist",
            resource_id="support-resource",
            starts_at=datetime.now(timezone.utc) + timedelta(days=30),
            ends_at=datetime.now(timezone.utc) + timedelta(days=30, hours=2),
        )
        db.add_all([offer, slot])
        db.flush()
        booking = Booking(event_id=event.id, offer_id=offer.id, slot_id=slot.id)
        conversation = Conversation(
            request_id=request_row.id,
            customer_org_id=customer_org_id,
            supplier_org_id=supplier_org_id,
            customer_name_snapshot="Support customer",
            supplier_name_snapshot="Support supplier",
        )
        db.add_all([booking, conversation])
        db.flush()
        payment = Payment(
            booking_id=booking.id,
            amount_rub=10_000,
            idempotency_key="support-payment-seed",
        )
        message = Message(
            conversation_id=conversation.id,
            author_user_id=None,
            body="Контекст для обращения",
        )
        db.add_all([payment, message])
        db.commit()
        return {
            "event": event.id,
            "booking": booking.id,
            "payment": payment.id,
            "message": message.id,
        }


def test_support_ticket_requires_idempotency_and_reuses_exact_request(client, SessionLocal):
    user = register(client, "support-idem@booker.test", "Support User")
    org = _create_org(client, user, "Support Idempotency")
    headers = auth_header(user["token"])
    payload = _ticket_payload(org["id"])

    missing = client.post("/support/tickets", json=payload, headers=headers)
    assert missing.status_code == 422

    first = client.post(
        "/support/tickets",
        json=payload,
        headers={**headers, "Idempotency-Key": "same-ticket-key"},
    )
    replay = client.post(
        "/support/tickets",
        json=payload,
        headers={**headers, "Idempotency-Key": "same-ticket-key"},
    )
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]

    changed = client.post(
        "/support/tickets",
        json={**payload, "subject": "Другой текст обращения"},
        headers={**headers, "Idempotency-Key": "same-ticket-key"},
    )
    assert changed.status_code == 409

    with SessionLocal() as db:
        assert db.query(SupportTicket).count() == 1
        assert db.query(SupportMessage).count() == 1


def test_manual_support_redacts_secrets_before_fingerprint_and_persistence(client, SessionLocal):
    user = register(client, "support-redaction@booker.test", "Support Redaction")
    org = _create_org(client, user, "Support Redaction Org")
    created = client.post(
        "/support/tickets",
        json=_ticket_payload(
            org["id"],
            subject="Пароль: Hunter2 не подходит",
            body="OTP: 123456, карта 4111 1111 1111 1111, CVV: 123, sk_live_ABC123def456ghi789",
        ),
        headers={
            **auth_header(user["token"]),
            "Idempotency-Key": "manual-redaction-ticket",
        },
    )
    assert created.status_code == 201, created.text

    reply = client.post(
        f"/support/tickets/{created.json()['id']}/messages",
        json={"body": "Bearer secret-token и password=AnotherSecret"},
        headers={
            **auth_header(user["token"]),
            "Idempotency-Key": "manual-redaction-reply",
        },
    )
    assert reply.status_code == 201, reply.text

    detail = client.get(
        f"/support/tickets/{created.json()['id']}",
        headers=auth_header(user["token"]),
    )
    assert detail.status_code == 200
    serialized = detail.text.casefold()
    for secret in ("hunter2", "123456", "4111", "cvv", "secret-token", "anothersecret", "sk_live_abc123def456ghi789"):
        assert secret not in serialized
    assert "секрет удалён" in serialized
    assert "платёжные данные удалены" in serialized

    with SessionLocal() as db:
        ticket = db.query(SupportTicket).one()
        persisted = "\n".join(
            [ticket.subject, ticket.body, *[message.body for message in db.query(SupportMessage).all()]]
        ).casefold()
        for secret in ("hunter2", "123456", "4111", "cvv", "secret-token", "anothersecret", "sk_live_abc123def456ghi789"):
            assert secret not in persisted


def test_support_related_objects_are_allowlisted_and_acl_checked(client, SessionLocal):
    customer = register(client, "support-customer@booker.test", "Customer")
    supplier = register(client, "support-supplier@booker.test", "Supplier")
    outsider = register(client, "support-outsider@booker.test", "Outsider")
    customer_org = _create_org(client, customer, "Customer Org")
    supplier_org = _create_org(client, supplier, "Supplier Org", kind="artist")
    outsider_org = _create_org(client, outsider, "Outsider Org")
    related = _seed_related_graph(SessionLocal, customer_org["id"], supplier_org["id"])

    unknown = client.post(
        "/support/tickets",
        json=_ticket_payload(
            outsider_org["id"], related_type="venue", related_id="not-allowed"
        ),
        headers={**auth_header(outsider["token"]), "Idempotency-Key": "unknown-type-key"},
    )
    assert unknown.status_code == 422

    incomplete = client.post(
        "/support/tickets",
        json=_ticket_payload(outsider_org["id"], related_type="event"),
        headers={**auth_header(outsider["token"]), "Idempotency-Key": "incomplete-ref-key"},
    )
    assert incomplete.status_code == 422

    for index, (related_type, related_id) in enumerate(related.items()):
        denied = client.post(
            "/support/tickets",
            json=_ticket_payload(
                outsider_org["id"],
                related_type=related_type,
                related_id=related_id,
            ),
            headers={
                **auth_header(outsider["token"]),
                "Idempotency-Key": f"outsider-related-{index}",
            },
        )
        assert denied.status_code == 404, (related_type, denied.text)

        allowed = client.post(
            "/support/tickets",
            json=_ticket_payload(
                customer_org["id"],
                related_type=related_type,
                related_id=related_id,
            ),
            headers={
                **auth_header(customer["token"]),
                "Idempotency-Key": f"customer-related-{index}",
            },
        )
        assert allowed.status_code == 201, (related_type, allowed.text)

        supplier_allowed = client.post(
            "/support/tickets",
            json=_ticket_payload(
                supplier_org["id"],
                related_type=related_type,
                related_id=related_id,
            ),
            headers={
                **auth_header(supplier["token"]),
                "Idempotency-Key": f"supplier-related-{index}",
            },
        )
        expected_supplier_status = 404 if related_type == "event" else 201
        assert supplier_allowed.status_code == expected_supplier_status, (
            related_type,
            supplier_allowed.text,
        )


def test_user_messages_close_reopen_acl_and_cas(client, SessionLocal):
    owner = register(client, "support-owner@booker.test", "Owner")
    outsider = register(client, "support-reader@booker.test", "Reader")
    org = _create_org(client, owner, "Support Lifecycle")
    ticket = _create_ticket(client, owner, org["id"], "lifecycle-ticket-key")
    headers = auth_header(owner["token"])

    denied = client.get(
        f"/support/tickets/{ticket['id']}", headers=auth_header(outsider["token"])
    )
    assert denied.status_code == 404

    first_reply = client.post(
        f"/support/tickets/{ticket['id']}/messages",
        json={"body": "Дополнительные сведения"},
        headers={**headers, "Idempotency-Key": "reply-key-0001"},
    )
    replay = client.post(
        f"/support/tickets/{ticket['id']}/messages",
        json={"body": "Дополнительные сведения"},
        headers={**headers, "Idempotency-Key": "reply-key-0001"},
    )
    assert first_reply.status_code == replay.status_code == 201
    assert first_reply.json()["id"] == replay.json()["id"]

    conflict = client.post(
        f"/support/tickets/{ticket['id']}/messages",
        json={"body": "Изменённые сведения"},
        headers={**headers, "Idempotency-Key": "reply-key-0001"},
    )
    assert conflict.status_code == 409

    current = client.get(f"/support/tickets/{ticket['id']}", headers=headers).json()
    close_headers = {**headers, "If-Match": str(current["state_version"])}
    closed = client.post(f"/support/tickets/{ticket['id']}/close", headers=close_headers)
    closed_replay = client.post(f"/support/tickets/{ticket['id']}/close", headers=close_headers)
    assert closed.status_code == 200
    assert closed_replay.status_code == 409

    rejected = client.post(
        f"/support/tickets/{ticket['id']}/messages",
        json={"body": "Ответ после закрытия"},
        headers={**headers, "Idempotency-Key": "reply-after-close"},
    )
    assert rejected.status_code == 409

    reopened = client.post(
        f"/support/tickets/{ticket['id']}/reopen",
        headers={**headers, "If-Match": str(closed.json()["state_version"])},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"
    accepted = client.post(
        f"/support/tickets/{ticket['id']}/messages",
        json={"body": "Ответ после открытия"},
        headers={**headers, "Idempotency-Key": "reply-after-reopen"},
    )
    assert accepted.status_code == 201

    with SessionLocal() as db:
        closed_audits = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_id == ticket["id"],
                AuditLog.action == "support.ticket.closed",
            )
            .all()
        )
        assert len(closed_audits) == 1
        close_payload = json.loads(closed_audits[0].payload)
        assert close_payload == {"from": "waiting_for_support", "to": "closed", "state_version": 2}
        membership = (
            db.query(TeamMember)
            .filter(
                TeamMember.user_id == owner["user_id"],
                TeamMember.organization_id == org["id"],
            )
            .one()
        )
        db.delete(membership)
        db.commit()

    after_membership_revoked = client.get(
        f"/support/tickets/{ticket['id']}", headers=headers
    )
    assert after_membership_revoked.status_code == 404


def test_same_org_member_cannot_read_or_mutate_another_users_ticket(client, SessionLocal):
    owner = register(client, "ticket-author@booker.test", "Author")
    coworker = register(client, "ticket-coworker@booker.test", "Coworker")
    org = _create_org(client, owner, "Private Support")
    added = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": coworker["user_id"], "role": "manager"},
        headers=auth_header(owner["token"]),
    )
    assert added.status_code == 200
    ticket = _create_ticket(client, owner, org["id"], "private-ticket-key")
    url = f"/support/tickets/{ticket['id']}"
    headers = auth_header(coworker["token"])
    assert client.get(url, headers=headers).status_code == 404
    assert client.post(
        f"{url}/messages",
        json={"body": "Чужой ответ"},
        headers={**headers, "Idempotency-Key": "coworker-reply-key"},
    ).status_code == 404
    for action in ("close", "reopen"):
        assert client.post(
            f"{url}/{action}", headers={**headers, "If-Match": "0"}
        ).status_code == 404
    with SessionLocal() as db:
        stored = db.get(SupportTicket, ticket["id"])
        assert stored.status == "open"
        assert stored.state_version == 0
        messages = db.query(SupportMessage).filter_by(ticket_id=ticket["id"]).all()
        assert len(messages) == 1
        assert all(message.author_user_id != coworker["user_id"] for message in messages)


def test_admin_support_requires_2fa_and_keeps_notes_private(
    client, SessionLocal, monkeypatch
):
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", True)
    owner = register(client, "support-note-owner@booker.test", "Owner")
    org = _create_org(client, owner, "Support Notes")
    ticket = _create_ticket(client, owner, org["id"], "admin-ticket-key")
    admin = _promote_admin(client, "support-admin@booker.test", totp=TEST_TOTP_SECRET)

    denied = client.get(
        "/admin/support/tickets", headers=auth_header(admin["pre_promotion_token"])
    )
    assert denied.status_code == 403
    admin_headers = admin_totp_headers(admin["token"])
    queue = client.get("/admin/support/tickets", headers=admin_headers)
    assert queue.status_code == 200

    reply = client.post(
        f"/admin/support/tickets/{ticket['id']}/messages",
        json={"body": "Ответ оператора"},
        headers={**admin_headers, "Idempotency-Key": "operator-reply-key"},
    )
    assert reply.status_code == 201
    assert reply.json()["author_kind"] == "operator"

    note = client.post(
        f"/admin/support/tickets/{ticket['id']}/notes",
        json={"body": "Внутренняя заметка оператора"},
        headers={**admin_headers, "Idempotency-Key": "operator-note-key"},
    )
    note_replay = client.post(
        f"/admin/support/tickets/{ticket['id']}/notes",
        json={"body": "Внутренняя заметка оператора"},
        headers={**admin_headers, "Idempotency-Key": "operator-note-key"},
    )
    assert note.status_code == note_replay.status_code == 201
    assert note.json()["id"] == note_replay.json()["id"]

    user_detail = client.get(
        f"/support/tickets/{ticket['id']}", headers=auth_header(owner["token"])
    )
    assert user_detail.status_code == 200
    assert any(item["author_kind"] == "operator" for item in user_detail.json()["messages"])
    assert "notes" not in user_detail.json()
    assert "Внутренняя заметка оператора" not in user_detail.text

    notes = client.get(
        f"/admin/support/tickets/{ticket['id']}/notes", headers=admin_headers
    )
    assert notes.status_code == 200
    assert [item["id"] for item in notes.json()["items"]] == [note.json()["id"]]

    with SessionLocal() as db:
        assert db.query(SupportOperatorNote).count() == 1
        actions = {
            row.action
            for row in db.query(AuditLog)
            .filter(AuditLog.actor_user_id == admin["user_id"])
            .all()
        }
        assert "support.admin.queue.viewed" in actions
        assert "support.admin.note.created" in actions
        assert "support.admin.notes.viewed" in actions


def test_admin_support_queue_prioritizes_event_day_incident(client, monkeypatch):
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", True)
    owner = register(client, "support-priority-owner@booker.test", "Priority Owner")
    org = _create_org(client, owner, "Priority Org")
    normal = _create_ticket(client, owner, org["id"], "priority-normal-ticket")
    urgent_response = client.post(
        "/support/tickets",
        json=_ticket_payload(
            org["id"],
            category="incident",
            subject="Исполнитель не приехал",
            body="Исполнитель не приехал на событие",
        ),
        headers={
            **auth_header(owner["token"]),
            "Idempotency-Key": "priority-urgent-ticket",
        },
    )
    assert urgent_response.status_code == 201, urgent_response.text
    urgent = urgent_response.json()
    assert urgent["priority"] == "urgent"
    assert urgent["response_due_at"] is not None  # Owner-approved daily Moscow calendar.

    admin = _promote_admin(client, "support-priority-admin@booker.test", totp=TEST_TOTP_SECRET)
    queue = client.get(
        "/admin/support/tickets",
        headers=admin_totp_headers(admin["token"]),
    )
    assert queue.status_code == 200, queue.text
    ticket_ids = [item["id"] for item in queue.json()["items"]]
    assert ticket_ids.index(urgent["id"]) < ticket_ids.index(normal["id"])


def test_admin_support_queue_marks_unanswered_overdue_ticket(client, monkeypatch):
    from booker_api.routers import trust

    monkeypatch.setattr(settings, "require_admin_2fa_enforced", True)
    monkeypatch.setattr(
        settings,
        "support_sla_schedule_json",
        json.dumps(
            {
                "event_day_no_show": {
                    "timezone": "Europe/Moscow",
                    "weekdays": [0, 1, 2, 3, 4, 5, 6],
                    "start": "10:00",
                    "end": "22:00",
                    "closed_dates": [],
                }
            }
        ),
    )
    monkeypatch.setattr(trust, "now", lambda: datetime(2026, 10, 1, 6, 50, tzinfo=timezone.utc))
    owner = register(client, "support-overdue-owner@booker.test", "Overdue Owner")
    ticket = client.post(
        "/support/tickets",
        json=_ticket_payload(
            None, category="incident", subject="Исполнитель не приехал", body="Неявка"
        ),
        headers={**auth_header(owner["token"]), "Idempotency-Key": "overdue-ticket-key"},
    )
    assert ticket.status_code == 201, ticket.text
    assert ticket.json()["response_due_at"] == "2026-10-01T07:30:00+00:00"
    admin = _promote_admin(client, "support-overdue-admin@booker.test", totp=TEST_TOTP_SECRET)
    monkeypatch.setattr(trust, "now", lambda: datetime(2026, 10, 1, 7, 30, tzinfo=timezone.utc))
    queue = client.get("/admin/support/tickets", headers=admin_totp_headers(admin["token"]))
    assert queue.status_code == 200, queue.text
    item = next(item for item in queue.json()["items"] if item["id"] == ticket.json()["id"])
    assert item["response_overdue"] is True
    answered = client.post(
        f"/admin/support/tickets/{ticket.json()['id']}/messages",
        json={"body": "Проверяем инцидент"},
        headers={
            **admin_totp_headers(admin["token"]),
            "Idempotency-Key": "overdue-operator-answer",
        },
    )
    assert answered.status_code == 201, answered.text
    after = client.get("/admin/support/tickets", headers=admin_totp_headers(admin["token"]))
    item_after = next(item for item in after.json()["items"] if item["id"] == ticket.json()["id"])
    assert item_after["response_overdue"] is False
    assert item_after["first_response_late"] is True
    detail = client.get(f"/support/tickets/{ticket.json()['id']}",
                        headers=auth_header(owner["token"]))
    assert detail.status_code == 200
    closed = client.post(
        f"/support/tickets/{ticket.json()['id']}/close",
        headers={**auth_header(owner["token"]), "If-Match": str(detail.json()["state_version"])},
    )
    assert closed.status_code == 200, closed.text
    reopened = client.post(
        f"/support/tickets/{ticket.json()['id']}/reopen",
        headers={**auth_header(owner["token"]), "If-Match": str(closed.json()["state_version"])},
    )
    assert reopened.status_code == 200, reopened.text
    again = client.get("/admin/support/tickets", headers=admin_totp_headers(admin["token"]))
    reopened_item = next(row for row in again.json()["items"] if row["id"] == ticket.json()["id"])
    assert reopened_item["response_overdue"] is False
    assert reopened_item["first_response_late"] is True


def test_support_admin_step_up_is_required_even_when_global_flag_is_disabled(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", False)
    admin = _promote_admin(client, "support-admin-without-2fa@booker.test")

    denied = client.get(
        "/admin/support/tickets",
        headers=auth_header(admin["token"]),
    )
    assert denied.status_code == 403
    assert "втор" in denied.json()["detail"].casefold()
    owner = register(client, "support-stepup-owner@booker.test", "Owner")
    ticket = _create_ticket(client, owner, None, "stepup-ticket-key")
    url = f"/admin/support/tickets/{ticket['id']}"
    headers = auth_header(admin["token"])
    for path in (url, f"{url}/notes"):
        assert client.get(path, headers=headers).status_code == 403
    for path, body in ((f"{url}/messages", "Ответ"), (f"{url}/notes", "Заметка")):
        assert client.post(
            path,
            json={"body": body},
            headers={**headers, "Idempotency-Key": "stepup-negative-key"},
        ).status_code == 403
    for action in ("close", "reopen"):
        assert client.post(
            f"{url}/{action}", headers={**headers, "If-Match": "0"}
        ).status_code == 403


def test_support_state_transition_rejects_stale_version(client, SessionLocal):
    user = register(client, "support-cas@booker.test", "CAS User")
    ticket = _create_ticket(client, user, None, "cas-ticket-key")
    first = SessionLocal()
    stale = SessionLocal()
    try:
        current_row = first.get(SupportTicket, ticket["id"])
        stale_row = stale.get(SupportTicket, ticket["id"])
        assert current_row is not None and stale_row is not None
        _cas_ticket_status(
            first,
            current_row,
            target="closed",
            allowed_from={"open"},
            actor_user_id=user["user_id"],
            action="support.ticket.closed",
        )
        with pytest.raises(HTTPException) as exc:
            _cas_ticket_status(
                stale,
                stale_row,
                target="closed",
                allowed_from={"open"},
                actor_user_id=user["user_id"],
                action="support.ticket.closed",
            )
        assert exc.value.status_code == 409
    finally:
        first.close()
        stale.close()


def test_support_close_rejects_stale_client_version(client):
    user = register(client, "support-stale-tab@booker.test", "Stale Tab")
    ticket = _create_ticket(client, user, None, "stale-tab-ticket")
    headers = auth_header(user["token"])
    initial_version = ticket["state_version"]
    first_close = client.post(
        f"/support/tickets/{ticket['id']}/close",
        headers={**headers, "If-Match": str(initial_version)},
    )
    assert first_close.status_code == 200
    competing_close = client.post(
        f"/support/tickets/{ticket['id']}/close",
        headers={**headers, "If-Match": str(initial_version)},
    )
    assert competing_close.status_code == 409
    reopened = client.post(
        f"/support/tickets/{ticket['id']}/reopen",
        headers={**headers, "If-Match": str(first_close.json()["state_version"])},
    )
    assert reopened.status_code == 200
    stale_close = client.post(
        f"/support/tickets/{ticket['id']}/close",
        headers={**headers, "If-Match": str(initial_version)},
    )
    assert stale_close.status_code == 409
    detail = client.get(f"/support/tickets/{ticket['id']}", headers=headers)
    assert detail.json()["status"] == "open"


def test_support_noop_cas_rejects_stale_orm_snapshot(client, SessionLocal):
    user = register(client, "support-stale-noop@booker.test", "Stale Noop")
    ticket = _create_ticket(client, user, None, "stale-noop-ticket")
    stale = SessionLocal()
    current = SessionLocal()
    try:
        stale_row = stale.get(SupportTicket, ticket["id"])
        current_row = current.get(SupportTicket, ticket["id"])
        assert stale_row is not None and current_row is not None
        _cas_ticket_status(
            current,
            current_row,
            target="closed",
            allowed_from={"open"},
            actor_user_id=user["user_id"],
            action="support.ticket.closed",
        )
        with pytest.raises(HTTPException) as exc:
            _cas_ticket_status(
                stale,
                stale_row,
                target="open",
                allowed_from={"closed"},
                actor_user_id=user["user_id"],
                action="support.ticket.reopened",
            )
        assert exc.value.status_code == 409
    finally:
        stale.close()
        current.close()


def test_support_ticket_list_excludes_same_org_non_author(client):
    owner = register(client, "support-list-owner@booker.test", "Owner")
    teammate = register(client, "support-list-teammate@booker.test", "Teammate")
    org = _create_org(client, owner, "Support List")
    ticket = _create_ticket(client, owner, org["id"], "support-list-ticket")
    added = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": teammate["user_id"], "role": "manager"},
        headers=auth_header(owner["token"]),
    )
    assert added.status_code == 200, added.text
    listed = client.get("/support/tickets", headers=auth_header(teammate["token"]))
    assert listed.status_code == 200
    assert ticket["id"] not in {row["id"] for row in listed.json()["items"]}
