import hashlib
from datetime import timedelta

from booker_api.config import settings
from booker_api.models import AuditLog, EmailOutbox, OrganizationInvitation, TeamMember
from booker_api.security import now
from tests.conftest import auth_header, register


def _organization(client, owner: dict) -> dict:
    response = client.post(
        "/orgs",
        json={"name": "Приглашающая команда", "kind": "artist"},
        headers=auth_header(owner["token"]),
    )
    assert response.status_code == 200
    return response.json()


def test_invitation_accept_is_email_bound_and_idempotent(client, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "dev")
    token = "fixed-invitation-token-with-enough-entropy-for-test"
    monkeypatch.setattr("booker_api.routers.identity.issue_invitation_token", lambda: token)
    owner = register(client, "invite-owner@booker.test", "Владелец")
    recipient = register(client, "invite-recipient@booker.test", "Участник")
    outsider = register(client, "invite-outsider@booker.test", "Чужой")
    org = _organization(client, owner)
    created = client.post(
        f"/orgs/{org['id']}/invitations",
        json={
            "email": "INVITE-RECIPIENT@booker.test",
            "role": "manager",
            "can_confirm_offer": True,
            "idempotency_key": "invite-recipient-once",
        },
        headers=auth_header(owner["token"]),
    )
    assert created.status_code == 200
    replay = client.post(
        f"/orgs/{org['id']}/invitations",
        json={
            "email": "invite-recipient@booker.test",
            "role": "manager",
            "can_confirm_offer": True,
            "idempotency_key": "invite-recipient-once",
        },
        headers=auth_header(owner["token"]),
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == created.json()["id"]
    assert replay.json()["idempotent"] is True
    db = client.app.state.SessionLocal()
    try:
        invitation = db.get(OrganizationInvitation, created.json()["id"])
        assert invitation.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in invitation.token_hash
        audit_payloads = "\n".join(row.payload for row in db.query(AuditLog).all())
        assert token not in audit_payloads
        assert "invite-recipient@booker.test" not in audit_payloads
    finally:
        db.close()

    denied = client.post(
        "/organization-invitations/accept",
        json={"token": token},
        headers=auth_header(outsider["token"]),
    )
    assert denied.status_code == 403
    accepted = client.post(
        "/organization-invitations/accept",
        json={"token": token},
        headers=auth_header(recipient["token"]),
    )
    assert accepted.status_code == 200
    assert accepted.json()["idempotent"] is False
    repeated = client.post(
        "/organization-invitations/accept",
        json={"token": token},
        headers=auth_header(recipient["token"]),
    )
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    db = client.app.state.SessionLocal()
    try:
        member = db.query(TeamMember).filter_by(user_id=recipient["user_id"]).one()
        assert member.role == "manager"
        assert member.can_confirm_offer is True
    finally:
        db.close()


def test_invitation_mutations_require_org_role_and_replay_payload(client, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "dev")
    monkeypatch.setattr(
        "booker_api.routers.identity.issue_invitation_token",
        lambda: "role-bound-invitation-token-with-enough-entropy",
    )
    owner = register(client, "invite-role-owner@booker.test", "Owner")
    outsider = register(client, "invite-role-outsider@booker.test", "Outsider")
    viewer = register(client, "invite-role-viewer@booker.test", "Viewer")
    manager = register(client, "invite-role-manager@booker.test", "Manager")
    recipient = register(client, "invite-role-recipient@booker.test", "Recipient")
    org = _organization(client, owner)
    other_org = _organization(client, outsider)
    owner_headers = auth_header(owner["token"])
    for actor, role in ((viewer, "viewer"), (manager, "manager")):
        assert client.post(
            f"/orgs/{org['id']}/members",
            json={"user_id": actor["user_id"], "role": role},
            headers=owner_headers,
        ).status_code == 200
    payload = {
        "email": "invite-role-recipient@booker.test",
        "role": "viewer",
        "idempotency_key": "role-bound-once",
    }
    for actor in (outsider, viewer, manager):
        denied = client.post(
            f"/orgs/{org['id']}/invitations",
            json=payload,
            headers=auth_header(actor["token"]),
        )
        assert denied.status_code == 403
    created = client.post(
        f"/orgs/{org['id']}/invitations", json=payload, headers=owner_headers
    )
    assert created.status_code == 200
    changed = client.post(
        f"/orgs/{org['id']}/invitations",
        json={**payload, "role": "owner", "can_confirm_offer": True},
        headers=owner_headers,
    )
    assert changed.status_code == 409
    wrong_org = client.post(
        f"/orgs/{other_org['id']}/invitations/{created.json()['id']}/revoke",
        headers=auth_header(outsider["token"]),
    )
    assert wrong_org.status_code == 404
    for actor in (viewer, manager):
        denied = client.post(
            f"/orgs/{org['id']}/invitations/{created.json()['id']}/revoke",
            headers=auth_header(actor["token"]),
        )
        assert denied.status_code == 403
    assert client.post(
        "/organization-invitations/accept",
        json={"token": "role-bound-invitation-token-with-enough-entropy"},
        headers=auth_header(recipient["token"]),
    ).status_code == 200


def test_invitation_revoke_and_expiry_fail_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "dev")
    tokens = iter(("revoked-invitation-token-with-enough-entropy", "expired-invitation-token-with-enough-entropy"))
    monkeypatch.setattr("booker_api.routers.identity.issue_invitation_token", lambda: next(tokens))
    owner = register(client, "invite-owner2@booker.test", "Владелец")
    recipient = register(client, "invite-recipient2@booker.test", "Участник")
    org = _organization(client, owner)
    headers = auth_header(owner["token"])
    first = client.post(
        f"/orgs/{org['id']}/invitations",
        json={
            "email": "invite-recipient2@booker.test",
            "role": "viewer",
            "idempotency_key": "revoke-once",
        },
        headers=headers,
    )
    assert first.status_code == 200
    revoked = client.post(
        f"/orgs/{org['id']}/invitations/{first.json()['id']}/revoke",
        headers=headers,
    )
    assert revoked.status_code == 200
    assert client.post(
        "/organization-invitations/accept",
        json={"token": "revoked-invitation-token-with-enough-entropy"},
        headers=auth_header(recipient["token"]),
    ).status_code == 409

    second = client.post(
        f"/orgs/{org['id']}/invitations",
        json={
            "email": recipient.get("email", "invite-recipient2@booker.test"),
            "role": "viewer",
            "idempotency_key": "expire-once",
        },
        headers=headers,
    )
    assert second.status_code == 200
    db = client.app.state.SessionLocal()
    try:
        invitation = db.get(OrganizationInvitation, second.json()["id"])
        invitation.expires_at = now() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    expired = client.post(
        "/organization-invitations/accept",
        json={"token": "expired-invitation-token-with-enough-entropy"},
        headers=auth_header(recipient["token"]),
    )
    assert expired.status_code == 410


def test_invitation_email_and_idempotency_scope_are_fail_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "dev")
    tokens = iter(("scope-token-one-with-enough-entropy", "scope-token-two-with-enough-entropy"))
    monkeypatch.setattr("booker_api.routers.identity.issue_invitation_token", lambda: next(tokens))
    first_owner = register(client, "scope-owner-1@booker.test", "Первый")
    second_owner = register(client, "scope-owner-2@booker.test", "Второй")
    first_org = _organization(client, first_owner)
    second_org = _organization(client, second_owner)

    for index, invalid_email in enumerate(
        (
            "victim@example.com, attacker@example.com",
            ".foo@example.com",
            "foo.@example.com",
            "foo..bar@example.com",
        )
    ):
        malformed = client.post(
            f"/orgs/{first_org['id']}/invitations",
            json={
                "email": invalid_email,
                "role": "viewer",
                "idempotency_key": f"malformed-address-{index}",
            },
            headers=auth_header(first_owner["token"]),
        )
        assert malformed.status_code == 400

    payload = {
        "email": "shared-recipient@example.com",
        "role": "viewer",
        "idempotency_key": "same-client-operation",
    }
    first = client.post(
        f"/orgs/{first_org['id']}/invitations",
        json=payload,
        headers=auth_header(first_owner["token"]),
    )
    second = client.post(
        f"/orgs/{second_org['id']}/invitations",
        json=payload,
        headers=auth_header(second_owner["token"]),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]

    monkeypatch.setattr(settings, "email_provider", "disabled")
    disabled = client.post(
        f"/orgs/{first_org['id']}/invitations",
        json={
            "email": "not-delivered@example.com",
            "role": "viewer",
            "idempotency_key": "disabled-provider",
        },
        headers=auth_header(first_owner["token"]),
    )
    assert disabled.status_code == 503
    db = client.app.state.SessionLocal()
    try:
        assert (
            db.query(OrganizationInvitation)
            .filter_by(idempotency_key="disabled-provider")
            .one_or_none()
            is None
        )
    finally:
        db.close()


def test_invitation_and_smtp_outbox_commit_before_delivery(
    client, SessionLocal, monkeypatch
):
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_smtp_host", "smtp.example.test")
    monkeypatch.setattr(
        "booker_api.routers.identity.issue_invitation_token",
        lambda: "smtp-invitation-token-with-enough-entropy",
    )
    observed = {"committed": False}

    def fake_deliver(row):
        with SessionLocal() as verification:
            invitation = verification.get(OrganizationInvitation, row.entity_id)
            outbox = verification.get(EmailOutbox, row.id)
            observed["committed"] = bool(invitation and outbox and outbox.status == "sending")
        return True, "sent"

    monkeypatch.setattr("booker_api.notifications.outbox._deliver", fake_deliver)
    owner = register(client, "smtp-owner@booker.test", "SMTP Owner")
    org = _organization(client, owner)
    created = client.post(
        f"/orgs/{org['id']}/invitations",
        json={
            "email": "smtp-recipient@example.com",
            "role": "viewer",
            "idempotency_key": "smtp-atomic-outbox",
        },
        headers=auth_header(owner["token"]),
    )
    assert created.status_code == 200, created.text
    assert created.json()["delivery_status"] == "sent"
    assert observed["committed"] is True
    with SessionLocal() as db:
        outbox = db.query(EmailOutbox).filter_by(entity_id=created.json()["id"]).one()
        assert outbox.status == "sent"
        assert outbox.attempts == 1
