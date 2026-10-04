"""W3-PROMO: organic share funnel events via audit log (no new tables)."""

def test_promo_event_writes_audit(client, SessionLocal):
    res = client.post(
        "/promo/events",
        json={
            "name": "promo.profile.open",
            "profile_kind": "artist",
            "profile_id": "artist-1",
            "medium": "qr",
            "source": "booker_share",
        },
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True

    from booker_api.models import AuditLog

    with SessionLocal() as db:
        row = (
            db.query(AuditLog)
            .filter(AuditLog.action == "promo.event", AuditLog.entity_id == "artist-1")
            .one()
        )
        assert row.entity_type == "artist"
        assert row.actor_user_id is None
        assert '"name": "promo.profile.open"' in row.payload
        assert '"medium": "qr"' in row.payload


def test_promo_event_no_auth_required(client):
    res = client.post(
        "/promo/events",
        json={
            "name": "promo.link.copy",
            "profile_kind": "venue",
            "profile_id": "venue-9",
            "medium": "link",
        },
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_promo_event_ignores_unknown_name(client, SessionLocal):
    from booker_api.models import AuditLog

    with SessionLocal() as db:
        before = db.query(AuditLog).count()
    res = client.post(
        "/promo/events",
        json={
            "name": "promo.paid.boost",
            "profile_kind": "artist",
            "profile_id": "x",
        },
    )
    assert res.status_code == 200
    assert res.json()["ignored"] is True
    with SessionLocal() as db:
        assert db.query(AuditLog).count() == before


def test_promo_event_rejects_invalid_kind(client):
    res = client.post(
        "/promo/events",
        json={
            "name": "promo.share.view",
            "profile_kind": "customer",
            "profile_id": "x",
        },
    )
    assert res.status_code == 422
