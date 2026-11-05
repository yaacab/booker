"""Two-approver recovery: OFF by default, fail-closed contract tests."""

from __future__ import annotations

from booker_api.config import settings
from booker_api.models import StaffRecoveryCode, User
from booker_api.two_approver_recovery import (
    evaluate_staff_totp_recovery,
    two_approver_feature_enabled,
)
from tests.conftest import auth_header, register
from tests.test_identity_s06 import NEW_TOTP_SECRET, _promote_admin
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def test_two_approver_flag_off_by_default():
    assert settings.two_approver_recovery_enabled is False
    assert two_approver_feature_enabled() is False


def test_evaluate_denies_multi_admin_when_flag_off(client, SessionLocal):
    first = _promote_admin(client, "ta-off-a@booker.test", totp=TEST_TOTP_SECRET)
    _promote_admin(client, "ta-off-b@booker.test", totp=TEST_TOTP_SECRET)
    with SessionLocal() as db:
        subject = db.get(User, first["user_id"])
        decision = evaluate_staff_totp_recovery(db, subject=subject)
        assert not decision.allowed
        assert decision.code == "two_approver_disabled"


def test_evaluate_allows_sole_admin_path_marker(client, SessionLocal):
    only = _promote_admin(client, "ta-sole@booker.test", totp=TEST_TOTP_SECRET)
    with SessionLocal() as db:
        subject = db.get(User, only["user_id"])
        decision = evaluate_staff_totp_recovery(db, subject=subject)
        assert decision.allowed
        assert decision.code == "sole_admin"


def test_http_multi_admin_recover_still_403_when_flag_off(client, SessionLocal):
    first = _promote_admin(client, "ta-http-a@booker.test", totp=TEST_TOTP_SECRET)
    _promote_admin(client, "ta-http-b@booker.test", totp=TEST_TOTP_SECRET)
    credentials = {"email": "ta-http-a@booker.test", "password": "password1"}
    kit = client.post(
        "/auth/admin-totp/recovery-codes/regenerate",
        json={**credentials, "totp": totp_code()},
    )
    assert kit.status_code == 200, kit.text
    denied = client.post(
        "/auth/admin-totp/recover",
        json={
            **credentials,
            "recovery_code": kit.json()["recovery_codes"][0],
            "secret": NEW_TOTP_SECRET,
            "code": totp_code(NEW_TOTP_SECRET),
        },
    )
    assert denied.status_code == 403
    with SessionLocal() as db:
        assert db.get(User, first["user_id"]).totp_secret == TEST_TOTP_SECRET
        assert db.query(StaffRecoveryCode).filter_by(user_id=first["user_id"]).count() == 10


def test_flag_on_still_fail_closed_without_armed_procedure(client, SessionLocal, monkeypatch):
    monkeypatch.setattr(settings, "two_approver_recovery_enabled", True)
    assert two_approver_feature_enabled() is True
    first = _promote_admin(client, "ta-on-a@booker.test", totp=TEST_TOTP_SECRET)
    second = _promote_admin(client, "ta-on-b@booker.test", totp=TEST_TOTP_SECRET)
    with SessionLocal() as db:
        subject = db.get(User, first["user_id"])
        missing = evaluate_staff_totp_recovery(db, subject=subject)
        assert not missing.allowed
        assert missing.code == "approver_missing"

        same = evaluate_staff_totp_recovery(
            db, subject=subject, approver_user_id=first["user_id"], approver_totp_ok=True
        )
        assert not same.allowed
        assert same.code == "approver_same_as_subject"

        no_totp = evaluate_staff_totp_recovery(
            db, subject=subject, approver_user_id=second["user_id"], approver_totp_ok=False
        )
        assert not no_totp.allowed
        assert no_totp.code == "approver_totp_required"

        # Even with distinct approver + TOTP, execution stays disarmed until owner GO.
        armed = evaluate_staff_totp_recovery(
            db, subject=subject, approver_user_id=second["user_id"], approver_totp_ok=True
        )
        assert not armed.allowed
        assert armed.code == "procedure_not_armed"

    # HTTP path still 403 — recover endpoint does not pass approver proofs yet.
    credentials = {"email": "ta-on-a@booker.test", "password": "password1"}
    kit = client.post(
        "/auth/admin-totp/recovery-codes/regenerate",
        json={**credentials, "totp": totp_code()},
    )
    assert kit.status_code == 200
    assert client.post(
        "/auth/admin-totp/recover",
        json={
            **credentials,
            "recovery_code": kit.json()["recovery_codes"][0],
            "secret": NEW_TOTP_SECRET,
            "code": totp_code(NEW_TOTP_SECRET),
        },
    ).status_code == 403


def test_outsider_cannot_read_admin_recovery_count(client):
    _promote_admin(client, "ta-count-admin@booker.test", totp=TEST_TOTP_SECRET)
    outsider = register(client, "ta-count-out@booker.test", "Out")
    denied = client.get(
        "/auth/admin-totp/recovery-codes/count",
        headers=auth_header(outsider["token"]),
    )
    assert denied.status_code in {401, 403}
