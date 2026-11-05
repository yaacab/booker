"""W4-CLAIM / W4-SUPPORT / E21 outbox."""

from booker_api.models import (
    AuditLog,
    EmailOutbox,
    SupportMessage,
    SupportTicket,
    Venue,
    VenueOwnershipClaim,
)
from booker_api.notifications.outbox import enqueue_email, retry_pending_outbox
from tests.conftest import auth_header, register
from tests.test_admin import _promote_admin
from tests.totp_helpers import TEST_TOTP_SECRET, admin_totp_headers


def test_venue_claim_does_not_grant_ownership(client, SessionLocal):
    claimant = register(client, "claim-user@booker.test", "Площадка")
    seed_owner = register(client, "claim-seed@booker.test", "Сидинг")
    ch = auth_header(claimant["token"])
    oh = auth_header(seed_owner["token"])
    claim_org = client.post(
        "/orgs",
        json={"name": "ООО Холл", "kind": "venue"},
        headers=ch,
    ).json()
    seed_org = client.post(
        "/orgs",
        json={"name": "Open Data Seed", "kind": "venue"},
        headers=oh,
    ).json()
    venue = client.post(
        "/venues",
        json={
            "organization_id": seed_org["id"],
            "name": "Open Hall",
            "capacity": 80,
        },
        headers=oh,
    )
    assert venue.status_code in (200, 201), venue.text
    venue_id = venue.json()["id"]

    db = SessionLocal()
    try:
        from booker_api.models import Venue

        row = db.get(Venue, venue_id)
        assert row is not None
        row.listing_origin = "open_data"
        db.commit()
        owner_before = row.organization_id
    finally:
        db.close()

    claimed = client.post(
        f"/venues/{venue_id}/claims",
        json={"organization_id": claim_org["id"], "evidence_note": "Я владелец, ИНН 123"},
        headers=ch,
    )
    assert claimed.status_code == 201, claimed.text
    body = claimed.json()
    assert body["status"] == "pending"
    assert body["grants_ownership"] is False

    db = SessionLocal()
    try:
        from booker_api.models import Venue

        after = db.get(Venue, venue_id)
        assert after is not None
        assert after.organization_id == owner_before
    finally:
        db.close()

    dup = client.post(
        f"/venues/{venue_id}/claims",
        json={"organization_id": claim_org["id"], "evidence_note": "повтор"},
        headers=ch,
    )
    assert dup.status_code == 409


def test_venue_claim_requires_org_owner_or_admin_and_operator_list(client, SessionLocal):
    owner = register(client, "claim-acl-owner@booker.test", "Owner")
    viewer = register(client, "claim-acl-viewer@booker.test", "Viewer")
    outsider = register(client, "claim-acl-outsider@booker.test", "Outsider")
    owner_headers = auth_header(owner["token"])
    claim_org = client.post(
        "/orgs", json={"name": "Claim Org", "kind": "venue"}, headers=owner_headers
    ).json()
    source_org = client.post(
        "/orgs", json={"name": "Source Org", "kind": "venue"},
        headers=auth_header(outsider["token"]),
    ).json()
    venue = client.post(
        "/venues",
        json={"organization_id": source_org["id"], "name": "Claim Target"},
        headers=auth_header(outsider["token"]),
    ).json()
    with SessionLocal() as db:
        db.get(Venue, venue["id"]).listing_origin = "open_data"
        db.commit()
    claim = client.post(
        f"/venues/{venue['id']}/claims",
        json={"organization_id": claim_org["id"], "evidence_note": "Подтверждающие сведения"},
        headers=owner_headers,
    )
    assert claim.status_code == 201, claim.text
    added = client.post(
        f"/orgs/{claim_org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=owner_headers,
    )
    assert added.status_code == 200, added.text
    admin = _promote_admin(client, "claim-operator@booker.test", totp=TEST_TOTP_SECRET)
    with SessionLocal() as db:
        claim_count = db.query(VenueOwnershipClaim).count()
        audit_count = db.query(AuditLog).count()
    for headers in (auth_header(viewer["token"]), auth_header(outsider["token"])):
        denied = client.post(
            f"/venues/{venue['id']}/claims",
            json={"organization_id": claim_org["id"], "evidence_note": "Чужое заявление"},
            headers=headers,
        )
        assert denied.status_code == 403, denied.text
    assert client.get(
        f"/venues/{venue['id']}/claims", headers=owner_headers
    ).status_code == 403
    without_step_up = client.get(
        f"/venues/{venue['id']}/claims", headers=auth_header(admin["pre_promotion_token"])
    )
    assert without_step_up.status_code == 403
    wrong_code = client.get(
        f"/venues/{venue['id']}/claims",
        headers={**auth_header(admin["pre_promotion_token"]), "X-Booker-TOTP": "000000"},
    )
    assert wrong_code.status_code == 403
    with_step_up = client.get(
        f"/venues/{venue['id']}/claims",
        headers=admin_totp_headers(admin["pre_promotion_token"]),
    )
    assert with_step_up.status_code == 200
    assert with_step_up.json()["items"][0]["evidence_note"] == "Подтверждающие сведения"
    within_step_up_window = client.get(
        f"/venues/{venue['id']}/claims", headers=auth_header(admin["token"])
    )
    assert within_step_up_window.status_code == 200
    with SessionLocal() as db:
        assert db.query(VenueOwnershipClaim).count() == claim_count
        assert db.query(AuditLog).count() == audit_count


def test_support_ticket_create_list(client):
    user = register(client, "support-user@booker.test", "Клиент")
    h = auth_header(user["token"])
    org = client.post(
        "/orgs",
        json={"name": "Клиент SUP", "kind": "customer"},
        headers=h,
    ).json()
    created = client.post(
        "/support/tickets",
        json={
            "organization_id": org["id"],
            "category": "profile",
            "subject": "Неточность профиля",
            "body": "Адрес указан неверно",
        },
        headers={**h, "Idempotency-Key": "support-ticket-create-1"},
    )
    assert created.status_code == 201, created.text
    ticket = created.json()
    assert ticket["ticket_number"].startswith("SUP-")
    assert ticket["escalation"] == "human"

    listed = client.get("/support/tickets", headers=h)
    assert listed.status_code == 200
    assert any(i["id"] == ticket["id"] for i in listed.json()["items"])


def test_support_ticket_cannot_be_created_for_foreign_organization(client, SessionLocal):
    owner = register(client, "support-foreign-owner@booker.test", "Owner")
    outsider = register(client, "support-foreign-outsider@booker.test", "Outsider")
    org = client.post(
        "/orgs", json={"name": "Private Support", "kind": "customer"},
        headers=auth_header(owner["token"]),
    ).json()
    with SessionLocal() as db:
        before = (
            db.query(SupportTicket).count(),
            db.query(SupportMessage).count(),
            db.query(AuditLog).count(),
        )
    denied = client.post(
        "/support/tickets",
        json={
            "organization_id": org["id"], "category": "technical",
            "subject": "Чужое обращение", "body": "Проверка доступа",
        },
        headers={**auth_header(outsider["token"]), "Idempotency-Key": "foreign-support-ticket"},
    )
    assert denied.status_code == 403, denied.text
    with SessionLocal() as db:
        assert (
            db.query(SupportTicket).count(),
            db.query(SupportMessage).count(),
            db.query(AuditLog).count(),
        ) == before


def test_email_outbox_retry_idempotent(SessionLocal, monkeypatch):
    db = SessionLocal()
    try:
        row = enqueue_email(
            db,
            idempotency_key="tpl:entity:id:a@b.test",
            recipient_email="a@b.test",
            subject="Ping",
            body="hello",
            template="tpl",
            entity_type="entity",
            entity_id="id",
        )
        db.commit()
        row_id = row.id

        calls = {"n": 0}

        def fake_deliver(outbox_row):
            calls["n"] += 1
            return True, "sent"

        monkeypatch.setattr("booker_api.notifications.outbox._deliver", fake_deliver)
        first = retry_pending_outbox(db, actor_user_id=None, limit=10)
        assert first["sent"] == 1
        assert calls["n"] == 1

        again = enqueue_email(
            db,
            idempotency_key="tpl:entity:id:a@b.test",
            recipient_email="a@b.test",
            subject="Ping",
            body="hello",
        )
        assert again.id == row_id
        assert again.status == "sent"

        second = retry_pending_outbox(db, actor_user_id=None, limit=10)
        assert second["sent"] == 0
        assert calls["n"] == 1

        refreshed = db.get(EmailOutbox, row_id)
        assert refreshed is not None
        assert refreshed.status == "sent"
        assert refreshed.attempts == 1
    finally:
        db.close()
