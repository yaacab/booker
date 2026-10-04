"""Offline recovery must not turn mailbox access into staff-account access."""

from booker_api.models import AuditLog, SessionToken, StaffRecoveryCode, User
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_identity_s06 import (
    BOOTSTRAP_TOTP_SECRET,
    NEW_TOTP_SECRET,
    _admin_proof,
    _capture_admin_proofs,
    _promote_admin,
)
from tests.totp_helpers import TEST_TOTP_SECRET, totp_code


def _bootstrap_admin(client, monkeypatch):
    delivered = _capture_admin_proofs(monkeypatch)
    admin = _promote_admin(client, "offline-kit-admin@booker.test")
    credentials = {"email": "offline-kit-admin@booker.test", "password": "password1"}
    assert client.post("/auth/admin-totp/challenge", json=credentials).status_code == 200
    assert len(delivered) == 1
    enrolled = client.post("/auth/admin-totp/confirm", json={
        **credentials, "proof": _admin_proof(delivered[0]),
        "secret": BOOTSTRAP_TOTP_SECRET, "code": totp_code(BOOTSTRAP_TOTP_SECRET),
    })
    assert enrolled.status_code == 200, enrolled.text
    return admin, credentials, enrolled


def test_sole_admin_offline_kit_is_one_time_and_rotates_factor(client, SessionLocal, monkeypatch):
    admin, credentials, enrolled = _bootstrap_admin(client, monkeypatch)
    kit = enrolled.json()["recovery_codes"]
    assert len(kit) == len(set(kit)) == 10
    assert enrolled.headers["Cache-Control"] == "no-store"
    login = client.post("/auth/login", json={
        **credentials, "totp": totp_code(BOOTSTRAP_TOTP_SECRET),
    })
    assert login.status_code == 200
    old_session = login.json()["token"]
    count = client.get("/auth/admin-totp/recovery-codes/count", headers=auth_header(old_session))
    assert count.status_code == 200 and count.json() == {"remaining": 10}
    with SessionLocal() as db:
        rows = db.query(StaffRecoveryCode).filter_by(user_id=admin["user_id"]).all()
        assert len(rows) == 10
        assert all(code not in str([row.code_hash for row in rows]) for code in kit)
        assert all(code not in str([event.payload for event in db.query(AuditLog).all()]) for code in kit)

    recovered = client.post("/auth/admin-totp/recover", json={
        **credentials, "recovery_code": kit[0], "secret": NEW_TOTP_SECRET,
        "code": totp_code(NEW_TOTP_SECRET),
    })
    assert recovered.status_code == 200, recovered.text
    assert recovered.headers["Cache-Control"] == "no-store"
    assert len(recovered.json()["recovery_codes"]) == 10
    assert kit[0] not in recovered.json()["recovery_codes"]
    assert client.get("/me", headers=auth_header(old_session)).status_code == 401
    assert client.post("/auth/login", json={
        **credentials, "totp": totp_code(BOOTSTRAP_TOTP_SECRET),
    }).status_code == 401
    assert client.post("/auth/login", json={
        **credentials, "totp": totp_code(NEW_TOTP_SECRET),
    }).status_code == 200
    assert client.post("/auth/admin-totp/recover", json={
        **credentials, "recovery_code": kit[0], "secret": BOOTSTRAP_TOTP_SECRET,
        "code": totp_code(BOOTSTRAP_TOTP_SECRET),
    }).status_code == 403
    with SessionLocal() as db:
        actions = {event.action for event in db.query(AuditLog).all()}
        assert {"auth.staff_recovery_code_used", "auth.staff_totp_recovered"} <= actions
        assert db.get(User, admin["user_id"]).totp_secret == NEW_TOTP_SECRET
        assert all(code not in str([row.code_hash for row in db.query(StaffRecoveryCode).all()])
                   for code in kit)


def test_multiple_admins_cannot_self_recover_with_offline_code(client, SessionLocal):
    first = _promote_admin(client, "offline-multi-first@booker.test", totp=TEST_TOTP_SECRET)
    _promote_admin(client, "offline-multi-second@booker.test", totp=TEST_TOTP_SECRET)
    credentials = {"email": "offline-multi-first@booker.test", "password": "password1"}
    kit = client.post("/auth/admin-totp/recovery-codes/regenerate", json={
        **credentials, "totp": totp_code(),
    })
    assert kit.status_code == 200, kit.text
    denied = client.post("/auth/admin-totp/recover", json={
        **credentials, "recovery_code": kit.json()["recovery_codes"][0],
        "secret": NEW_TOTP_SECRET, "code": totp_code(NEW_TOTP_SECRET),
    })
    assert denied.status_code == 403
    with SessionLocal() as db:
        assert db.get(User, first["user_id"]).totp_secret == TEST_TOTP_SECRET
        assert db.query(StaffRecoveryCode).filter_by(user_id=first["user_id"]).count() == 10


def test_operator_can_recover_and_regeneration_invalidates_old_kit(client, SessionLocal):
    operator = register(client, "offline-operator@booker.test")
    with SessionLocal() as db:
        row = db.get(User, operator["user_id"])
        row.email_verified_at = now()
        row.is_support_operator = True
        row.totp_enabled = True
        row.totp_secret = TEST_TOTP_SECRET
        db.commit()
    credentials = {"email": "offline-operator@booker.test", "password": "password1"}
    first = client.post("/auth/admin-totp/recovery-codes/regenerate", json={
        **credentials, "totp": totp_code(),
    })
    assert first.status_code == 200, first.text
    operator_login = client.post("/auth/login", json={
        **credentials, "totp": totp_code(),
    })
    assert operator_login.status_code == 200, operator_login.text
    operator_token = operator_login.json()["token"]
    count = client.get("/auth/admin-totp/recovery-codes/count", headers=auth_header(operator_token))
    assert count.status_code == 200 and count.json() == {"remaining": 10}
    assert client.get("/admin/support/operators", headers=auth_header(operator_token)).status_code == 403
    second = client.post("/auth/admin-totp/recovery-codes/regenerate", json={
        **credentials, "totp": totp_code(),
    })
    assert second.status_code == 200, second.text
    old_code = first.json()["recovery_codes"][0]
    new_code = second.json()["recovery_codes"][0]
    assert client.post("/auth/admin-totp/recover", json={
        **credentials, "recovery_code": old_code, "secret": NEW_TOTP_SECRET,
        "code": totp_code(NEW_TOTP_SECRET),
    }).status_code == 403
    assert client.post("/auth/admin-totp/recover", json={
        **credentials, "recovery_code": new_code, "secret": NEW_TOTP_SECRET,
        "code": "000000",
    }).status_code == 403
    recovered = client.post("/auth/admin-totp/recover", json={
        **credentials, "recovery_code": new_code, "secret": NEW_TOTP_SECRET,
        "code": totp_code(NEW_TOTP_SECRET),
    })
    assert recovered.status_code == 200, recovered.text
    assert client.post("/auth/login", json={
        **credentials, "totp": totp_code(NEW_TOTP_SECRET),
    }).status_code == 200
    with SessionLocal() as db:
        assert db.query(SessionToken).filter_by(user_id=operator["user_id"]).count() == 1
