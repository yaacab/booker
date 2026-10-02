"""Support staff have a personal queue without platform administration."""

import re

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from booker_api.config import settings
from booker_api.models import AuditLog, EmailOutbox, User
from booker_api.routers.catalog import _optional_user
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.test_identity_s06 import BOOTSTRAP_TOTP_SECRET
from tests.test_support_security import _ticket_payload
from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers, totp_code


def _verify_email(client, user):
    with client.app.state.SessionLocal() as db:
        row = db.get(User, user["user_id"])
        row.email_verified_at = now()
        db.commit()


def test_operator_grant_queue_acl_and_immediate_revoke(client, monkeypatch):
    admin = _promote_admin(client, "role-admin@booker.test", totp=TEST_TOTP_SECRET)
    operator = register(client, "pavel-operator@booker.test", "Павел")
    customer = register(client, "role-customer@booker.test")
    ticket = client.post(
        "/support/tickets", json=_ticket_payload(category="technical", subject="Вопрос"),
        headers={**auth_header(customer["token"]), "Idempotency-Key": "pavel-role-ticket"},
    )
    assert ticket.status_code == 201, ticket.text
    admin_headers = admin_totp_headers(admin["token"])
    role_url = "/admin/support/operators"
    body = {"email": "pavel-operator@booker.test", "enabled": True}
    assert client.post(role_url, json=body, headers=auth_header(customer["token"])).status_code == 403
    assert client.post(role_url, json=body, headers=auth_header(admin["pre_promotion_token"])).status_code == 403
    assert client.post(role_url, json=body, headers=admin_headers).status_code == 409
    with client.app.state.SessionLocal() as db:
        with pytest.raises(IntegrityError, match="support operator email verification required"):
            db.execute(text("UPDATE users SET is_support_operator = 1 WHERE id = :user_id"),
                       {"user_id": operator["user_id"]})
        db.rollback()
    _verify_email(client, operator)
    granted = client.post(role_url, json=body, headers=admin_headers)
    assert granted.status_code == 200, granted.text
    assert granted.json()["is_support_operator"] is True
    assert client.get("/me", headers=auth_header(operator["token"])).status_code == 401
    with client.app.state.SessionLocal() as db:
        row = db.get(User, operator["user_id"])
        row.totp_enabled = True
        row.totp_secret = TEST_TOTP_SECRET
        db.commit()
    missing_totp = client.post("/auth/login", json={
        "email": "pavel-operator@booker.test", "password": "password1",
    })
    assert missing_totp.status_code == 401
    logged_in = client.post("/auth/login", json={
        "email": "pavel-operator@booker.test", "password": "password1",
        "totp": totp_code(),
    })
    assert logged_in.status_code == 200, logged_in.text
    token = logged_in.json()["token"]
    assert logged_in.json()["is_support_operator"] is True
    assert client.get("/me", headers=auth_header(token)).json()["is_support_operator"] is True
    # The freshly issued session already carries verified TOTP assurance.
    assert client.get("/admin/support/tickets", headers=auth_header(token)).status_code == 200
    operator_headers = admin_totp_headers(token)
    assert client.get("/admin/support/tickets", headers=operator_headers).status_code == 200
    assert client.post("/orgs", json={"name": "Нельзя", "kind": "customer", "city": "Москва"},
                       headers=operator_headers).status_code == 403
    assert client.get("/support/tickets", headers=operator_headers).status_code == 403
    customer_org = client.post("/orgs", json={
        "name": "Команда заказчика", "kind": "customer", "city": "Москва",
    }, headers=auth_header(customer["token"]))
    assert customer_org.status_code == 200, customer_org.text
    assert client.post(f"/orgs/{customer_org.json()['id']}/members", json={
        "user_id": operator["user_id"], "role": "viewer",
    }, headers=auth_header(customer["token"])).status_code == 409
    detail = client.get(f"/admin/support/tickets/{ticket.json()['id']}", headers=operator_headers)
    assert detail.status_code == 200
    assert client.post(
        f"/admin/support/tickets/{ticket.json()['id']}/assign",
        json={"action": "take"},
        headers={**operator_headers, "If-Match": str(detail.json()["state_version"])},
    ).status_code == 200
    note = client.post(
        f"/admin/support/tickets/{ticket.json()['id']}/notes",
        json={"body": "Только для оператора"},
        headers={**operator_headers, "Idempotency-Key": "pavel-note-1"},
    )
    assert note.status_code == 201, note.text
    assert "Только для оператора" not in str(client.get(
        f"/support/tickets/{ticket.json()['id']}", headers=auth_header(customer["token"])
    ).json())
    for path in ("/admin/metrics", "/admin/audit", "/admin/disputes",
                 "/admin/verifications", "/admin/support/operators"):
        assert client.get(path, headers=operator_headers).status_code == 403, path
    assert client.post(role_url, json={"email": body["email"], "enabled": False},
                       headers=admin_headers).status_code == 200
    assert client.get("/admin/support/tickets", headers=operator_headers).status_code == 401
    with client.app.state.SessionLocal() as db:
        events = db.query(AuditLog).filter(AuditLog.entity_type == "user",
                                           AuditLog.entity_id == operator["user_id"]).all()
        assert {event.action for event in events} >= {
            "support.operator.granted", "support.operator.revoked"
        }


def test_operator_role_rejects_existing_membership_and_route_gate_blocks_legacy_membership(client):
    admin = _promote_admin(client, "role-existing-admin@booker.test", totp=TEST_TOTP_SECRET)
    member = register(client, "role-existing-member@booker.test")
    _verify_email(client, member)
    org = client.post("/orgs", json={"name": "Организация", "kind": "customer", "city": "Москва"},
                      headers=auth_header(member["token"]))
    assert org.status_code == 200, org.text
    role = client.post("/admin/support/operators", json={
        "email": "role-existing-member@booker.test", "enabled": True,
    }, headers=admin_totp_headers(admin["token"]))
    assert role.status_code == 409
    # A legacy/direct role flag must still be unable to act through its old memberships.
    with client.app.state.SessionLocal() as db:
        row = db.get(User, member["user_id"])
        row.is_support_operator = True
        row.totp_enabled = True
        row.totp_secret = TEST_TOTP_SECRET
        db.commit()
    headers = admin_totp_headers(member["token"])
    assert client.get("/me", headers=headers).status_code == 200
    assert client.get("/admin/support/tickets", headers=headers).status_code == 200
    with client.app.state.SessionLocal() as db:
        request = Request({"type": "http", "method": "GET", "path": "/catalog/search",
                           "headers": [], "query_string": b""})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=member["token"])
        assert _optional_user(request, credentials, db) is None
    assert client.post("/orgs", json={"name": "Вторая", "kind": "customer", "city": "Москва"},
                       headers=headers).status_code == 403
    assert client.post(f"/orgs/{org.json()['id']}/members", json={
        "email": "role-existing-admin@booker.test", "role": "manager",
    }, headers=headers).status_code == 403


def test_operator_totp_bootstrap_requires_password_mail_and_new_code(client, monkeypatch):
    admin = _promote_admin(client, "role-bootstrap-admin@booker.test", totp=TEST_TOTP_SECRET)
    operator = register(client, "pavel-bootstrap@booker.test", "Павел")
    _verify_email(client, operator)
    grant = client.post("/admin/support/operators", json={
        "email": "pavel-bootstrap@booker.test", "enabled": True,
    }, headers=admin_totp_headers(admin["token"]))
    assert grant.status_code == 200
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", True)
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "in_app_provider", "disabled")
    deliveries = []
    monkeypatch.setattr("booker_api.notifications.transports.smtp._deliver",
                        lambda mail: (deliveries.append(mail) or True, "sent"))
    assert client.post("/auth/login", json={
        "email": "pavel-bootstrap@booker.test", "password": "password1",
    }).status_code == 403
    challenge = client.post("/auth/admin-totp/challenge", json={
        "email": "pavel-bootstrap@booker.test", "password": "password1",
    })
    assert challenge.json() == {"ok": True}
    assert len(deliveries) == 1
    match = re.search(r"настройки второго фактора:\n([A-Za-z0-9_-]+)\n", deliveries[0].body)
    assert match
    proof = match.group(1)
    confirmed = client.post("/auth/admin-totp/confirm", json={
        "email": "pavel-bootstrap@booker.test", "password": "password1",
        "proof": proof, "secret": BOOTSTRAP_TOTP_SECRET,
        "code": totp_code(BOOTSTRAP_TOTP_SECRET),
    })
    assert confirmed.status_code == 200, confirmed.text
    login = client.post("/auth/login", json={
        "email": "pavel-bootstrap@booker.test", "password": "password1",
        "totp": totp_code(BOOTSTRAP_TOTP_SECRET),
    })
    assert login.status_code == 200, login.text
    assert client.get("/admin/support/tickets", headers=auth_header(login.json()["token"])).status_code == 200
    assert client.get("/admin/metrics", headers=auth_header(login.json()["token"])).status_code == 403
    with client.app.state.SessionLocal() as db:
        assert db.query(EmailOutbox).filter_by(template="auth.admin_totp_proof").count() == 0
        assert all(proof not in row.payload for row in db.query(AuditLog).all())
