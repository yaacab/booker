import hashlib

import pytest

from booker_api.config import settings
from booker_api.models import SessionToken, User
from booker_api.security import now
from booker_api.totp import verify_totp_code
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers, totp_code


def test_verify_totp_accepts_valid_code():
    code = totp_code(TEST_TOTP_SECRET)
    assert verify_totp_code(TEST_TOTP_SECRET, code)


def test_verify_totp_rejects_wrong_code():
    assert not verify_totp_code(TEST_TOTP_SECRET, "000000")


def test_admin_metrics_requires_step_up_when_enforced(client, monkeypatch):
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", True)
    admin = _promote_admin(client, "2fa-stepup@booker.test", totp=TEST_TOTP_SECRET)
    with client.app.state.SessionLocal() as db:
        token_hash = hashlib.sha256(admin["token"].encode()).hexdigest()
        session = db.get(SessionToken, token_hash)
        assert session is not None
        session.admin_2fa_verified_at = None
        db.commit()
    denied = client.get("/admin/metrics", headers=auth_header(admin["token"]))
    assert denied.status_code == 403
    assert "второго фактора" in denied.json()["detail"].lower()
    ok = client.get("/admin/metrics", headers=admin_totp_headers(admin["token"]))
    assert ok.status_code == 200


def test_admin_login_sets_step_up_session(client, monkeypatch):
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", True)
    _promote_admin(client, "2fa-login@booker.test", totp=TEST_TOTP_SECRET)
    login = client.post(
        "/auth/login",
        json={
            "email": "2fa-login@booker.test",
            "password": "password1",
            "totp": totp_code(),
        },
    )
    assert login.status_code == 200
    token = login.json()["token"]
    res = client.get("/admin/metrics", headers=auth_header(token))
    assert res.status_code == 200


@pytest.mark.parametrize(
    ("role_field", "privileged_path"),
    [
        ("is_platform_admin", "/admin/metrics"),
        ("is_support_operator", "/admin/support/tickets"),
    ],
)
def test_staff_requires_totp_with_rollout_flag_off(
    client, monkeypatch, role_field, privileged_path,
):
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", False)
    email = f"{role_field}-2fa-off@booker.test"
    staff = register(client, email)
    with client.app.state.SessionLocal() as db:
        row = db.get(User, staff["user_id"])
        row.email_verified_at = now()
        setattr(row, role_field, True)
        row.totp_enabled = True
        row.totp_secret = TEST_TOTP_SECRET
        db.commit()

    # A bearer issued before promotion cannot become a privileged session by itself.
    old_headers = auth_header(staff["token"])
    assert client.get(privileged_path, headers=old_headers).status_code == 403
    assert client.post("/auth/login", json={
        "email": email, "password": "password1",
    }).status_code == 401
    assert client.post("/auth/login", json={
        "email": email, "password": "password1", "totp": "000000",
    }).status_code == 401
    logged_in = client.post("/auth/login", json={
        "email": email, "password": "password1", "totp": totp_code(),
    })
    assert logged_in.status_code == 200
    assert client.get(
        privileged_path, headers=auth_header(logged_in.json()["token"]),
    ).status_code == 200


@pytest.mark.parametrize(
    ("role_field", "privileged_path"),
    [
        ("is_platform_admin", "/admin/metrics"),
        ("is_support_operator", "/admin/support/tickets"),
    ],
)
def test_staff_without_totp_cannot_use_pre_promotion_bearer_or_login(
    client, monkeypatch, role_field, privileged_path,
):
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", False)
    email = f"{role_field}-unenrolled@booker.test"
    staff = register(client, email)
    with client.app.state.SessionLocal() as db:
        row = db.get(User, staff["user_id"])
        row.email_verified_at = now()
        setattr(row, role_field, True)
        db.commit()
    assert client.get(
        privileged_path, headers=auth_header(staff["token"]),
    ).status_code == 403
    assert client.post("/auth/login", json={
        "email": email, "password": "password1",
    }).status_code == 403


def test_ordinary_user_login_remains_available_without_totp(client, monkeypatch):
    monkeypatch.setattr(settings, "require_admin_2fa_enforced", False)
    register(client, "ordinary-no-totp@booker.test")
    res = client.post("/auth/login", json={
        "email": "ordinary-no-totp@booker.test", "password": "password1",
    })
    assert res.status_code == 200
    assert client.get("/me", headers=auth_header(res.json()["token"])).status_code == 200


def test_refund_requires_valid_totp_code(client):
    from tests.test_payments import _awaiting_payment, _sign

    ctx = _awaiting_payment(client)
    client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-totp-ref",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-totp-ref", ctx["payment_id"], "succeeded"),
        },
    )
    admin = _promote_admin(client, "totp-refund@booker.test", totp=TEST_TOTP_SECRET)
    bad = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "totp": "000000",
        },
        headers=admin_totp_headers(admin["token"]),
    )
    assert bad.status_code == 403
    ok = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "totp": totp_code(),
        },
        headers=admin_totp_headers(admin["token"]),
    )
    assert ok.status_code == 200
    other = _promote_admin(client, "totp-refund2@booker.test", totp=TEST_TOTP_SECRET)
    approve_bad = client.post(
        f"/admin/refunds/{ok.json()['id']}/approve",
        json={"totp": "000000"},
        headers=admin_totp_headers(other["token"]),
    )
    assert approve_bad.status_code == 403
    approve_ok = client.post(
        f"/admin/refunds/{ok.json()['id']}/approve",
        json={"totp": totp_code()},
        headers=admin_totp_headers(other["token"]),
    )
    assert approve_ok.status_code == 200


def test_sensitive_admin_refund_requires_enabled_totp_even_when_rollout_optional(client):
    from tests.test_payments import _awaiting_payment, _sign

    ctx = _awaiting_payment(client)
    captured = client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-no-totp-ref",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-no-totp-ref", ctx["payment_id"], "succeeded"),
        },
    )
    assert captured.status_code == 200
    admin = _promote_admin(client, "no-totp-refund@booker.test")
    denied = client.post(
        "/admin/refunds",
        json={"payment_id": ctx["payment_id"], "totp": totp_code()},
        headers=auth_header(admin["token"]),
    )
    assert denied.status_code == 403
