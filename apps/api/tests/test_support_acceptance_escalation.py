from datetime import datetime, timedelta, timezone

from booker_api.models import SupportTicket, UserNotification
from booker_api.support_escalation import escalate_unaccepted
from tests.conftest import register
from tests.test_admin import _promote_admin
from tests.test_support_escalation import _ticket
from tests.totp_helpers import TEST_TOTP_SECRET


def test_unaccepted_escalates_once_per_cycle_without_changing_response(client, SessionLocal):
    owner = register(client, "acceptance-owner@booker.test")
    admin = _promote_admin(client, "acceptance-admin@booker.test", totp=TEST_TOTP_SECRET)
    ticket = _ticket(client, owner, "acceptance-clock")
    start = datetime(2026, 10, 2, 18, 59, tzinfo=timezone.utc)
    deadline = datetime(2026, 10, 3, 7, 14, tzinfo=timezone.utc)
    response = deadline + timedelta(minutes=15)
    with SessionLocal() as db:
        row = db.get(SupportTicket, ticket["id"])
        row.priority = "urgent"
        row.created_at = start
        row.response_due_at = response
        db.commit()
        assert escalate_unaccepted(db, at=deadline-timedelta(seconds=1))["escalated"] == 0
        assert escalate_unaccepted(db, at=deadline)["escalated"] == 1
        db.refresh(row)
        assert row.status == "open"
        assert row.assigned_to_user_id == admin["user_id"]
        assert row.response_due_at.replace(tzinfo=timezone.utc) == response
        assert row.overdue_escalated_at is None
        assert escalate_unaccepted(db, at=deadline)["escalated"] == 0
        row.status = "open"
        row.reopened_at = deadline
        row.acceptance_escalated_at = None
        row.state_version += 1
        db.commit()
        assert escalate_unaccepted(db, at=deadline+timedelta(minutes=14))["escalated"] == 0
        assert escalate_unaccepted(db, at=deadline+timedelta(minutes=15))["escalated"] == 1
        assert db.query(UserNotification).filter_by(
            recipient_user_id=admin["user_id"], template="support.acceptance_overdue",
        ).count() == 2


def test_accepted_closed_normal_and_no_admin_do_not_escalate(client, SessionLocal):
    owner = register(client, "acceptance-skip@booker.test")
    ticket = _ticket(client, owner, "acceptance-skip")
    at = datetime(2026, 10, 3, 10, tzinfo=timezone.utc)
    with SessionLocal() as db:
        row = db.get(SupportTicket, ticket["id"])
        row.created_at = at-timedelta(hours=1)
        row.priority = "urgent"
        db.commit()
        assert escalate_unaccepted(db, at=at)["no_admin"] == 1
    admin = _promote_admin(client, "acceptance-skip-admin@booker.test", totp=TEST_TOTP_SECRET)
    with SessionLocal() as db:
        row = db.get(SupportTicket, ticket["id"])
        row.assigned_to_user_id = admin["user_id"]
        row.accepted_by_user_id = admin["user_id"]
        row.accepted_at = at-timedelta(minutes=50)
        db.commit()
        assert escalate_unaccepted(db, at=at)["escalated"] == 0
        row.accepted_at = row.accepted_by_user_id = None
        row.status = "closed"
        db.commit()
        assert escalate_unaccepted(db, at=at)["escalated"] == 0
        row.status = "open"
        row.priority = "normal"
        db.commit()
        assert escalate_unaccepted(db, at=at)["escalated"] == 0


def test_stale_worker_cannot_override_acceptance(client, SessionLocal, monkeypatch):
    from sqlalchemy import update
    from sqlalchemy.sql.dml import Update

    owner = register(client, "acceptance-race@booker.test")
    admin = _promote_admin(client, "acceptance-race-admin@booker.test", totp=TEST_TOTP_SECRET)
    ticket = _ticket(client, owner, "acceptance-race")
    at = datetime(2026, 10, 3, 10, tzinfo=timezone.utc)
    with SessionLocal() as db:
        row = db.get(SupportTicket, ticket["id"])
        row.created_at = at-timedelta(hours=1)
        row.priority = "urgent"
        db.commit()
        execute = db.execute
        interleaved = False

        def accept_before_cas(statement, *args, **kwargs):
            nonlocal interleaved
            if isinstance(statement, Update) and not interleaved:
                interleaved = True
                execute(update(SupportTicket).where(SupportTicket.id == row.id).values(
                    assigned_to_user_id=admin["user_id"], accepted_by_user_id=admin["user_id"],
                    accepted_at=at, state_version=SupportTicket.state_version+1,
                ))
                db.commit()
            return execute(statement, *args, **kwargs)

        monkeypatch.setattr(db, "execute", accept_before_cas)
        assert escalate_unaccepted(db, at=at)["escalated"] == 0
        assert interleaved
        db.refresh(row)
        assert row.accepted_by_user_id == admin["user_id"]
        assert row.acceptance_escalated_at is None
        assert db.query(UserNotification).filter_by(template="support.acceptance_overdue").count() == 0


def test_reopen_api_resets_acceptance_escalation_and_hides_staff_marker(client, SessionLocal):
    from tests.conftest import auth_header
    from tests.totp_helpers import admin_totp_headers

    owner = register(client, "acceptance-reopen@booker.test")
    admin = _promote_admin(client, "acceptance-reopen-admin@booker.test", totp=TEST_TOTP_SECRET)
    ticket = _ticket(client, owner, "acceptance-reopen")
    at = datetime(2026, 10, 3, 10, tzinfo=timezone.utc)
    with SessionLocal() as db:
        row = db.get(SupportTicket, ticket["id"])
        row.created_at = at-timedelta(hours=1)
        row.priority = "urgent"
        db.commit()
        assert escalate_unaccepted(db, at=at)["escalated"] == 1
    path = f"/admin/support/tickets/{ticket['id']}"
    headers = admin_totp_headers(admin["token"])
    detail = client.get(path, headers=headers).json()
    assert detail["acceptance_due_at"]
    assert detail["acceptance_escalated_at"]
    queue = client.get("/admin/support/tickets?escalated_only=true", headers=headers)
    assert queue.status_code == 200, queue.text
    assert ticket["id"] in {item["id"] for item in queue.json()["items"]}
    closed = client.post(path+"/close", headers={**headers, "If-Match": str(detail["state_version"])})
    assert closed.status_code == 200, closed.text
    reopened = client.post(path+"/reopen", headers={**headers, "If-Match": str(closed.json()["state_version"])})
    assert reopened.status_code == 200, reopened.text
    assert client.get(path, headers=headers).json()["acceptance_escalated_at"] is None
    customer = client.get(f"/support/tickets/{ticket['id']}", headers=auth_header(owner["token"])).json()
    assert "acceptance_escalated_at" not in customer
