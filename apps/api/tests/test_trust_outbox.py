"""W4-CLAIM / W4-SUPPORT / E21 outbox."""

from booker_api.models import EmailOutbox
from booker_api.notifications.outbox import enqueue_email, retry_pending_outbox
from tests.conftest import auth_header, register


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

    after = client.get(f"/venues/{venue_id}").json()
    assert after.get("organization_id") == owner_before

    dup = client.post(
        f"/venues/{venue_id}/claims",
        json={"organization_id": claim_org["id"], "evidence_note": "повтор"},
        headers=ch,
    )
    assert dup.status_code == 409


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
            "related_type": "venue",
            "related_id": "x",
        },
        headers=h,
    )
    assert created.status_code == 201, created.text
    ticket = created.json()
    assert ticket["ticket_number"].startswith("SUP-")
    assert ticket["escalation"] == "human"

    listed = client.get("/support/tickets", headers=h)
    assert listed.status_code == 200
    assert any(i["id"] == ticket["id"] for i in listed.json()["items"])


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
