from booker_api.config import settings
from booker_api.totp import verify_totp_code
from tests.conftest import auth_header
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
    other = _promote_admin(client, "totp-refund2@booker.test")
    bad = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "approver_user_id": other["user_id"],
            "totp": "000000",
        },
        headers=auth_header(admin["token"]),
    )
    assert bad.status_code == 403
    ok = client.post(
        "/admin/refunds",
        json={
            "payment_id": ctx["payment_id"],
            "approver_user_id": other["user_id"],
            "totp": totp_code(),
        },
        headers=auth_header(admin["token"]),
    )
    assert ok.status_code == 200
