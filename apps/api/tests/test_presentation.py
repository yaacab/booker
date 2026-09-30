import json
from datetime import timedelta

import pytest

from booker_api.models import (
    Artist,
    ArtistPresentation,
    AuditLog,
    AvailabilitySlot,
    Subscription,
    TeamMember,
)
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_offers import setup_negotiation


def editor(client, ctx):
    response = client.get(f"/artists/{ctx['artist']['id']}/presentation", headers=auth_header(ctx["owner"]["token"]))
    assert response.status_code == 200, response.text
    return {**response.json()["data"], "expected_version": response.json()["version"]}


def save(client, ctx, body):
    return client.put(f"/artists/{ctx['artist']['id']}/presentation", json=body, headers=auth_header(ctx["owner"]["token"]))


def test_free_presentation_is_complete_versioned_and_does_not_change_money_or_trust(client, SessionLocal):
    ctx = setup_negotiation(client)
    body = editor(client, ctx)
    body.update(name="Живой концерт", cover_url="https://media.example.org/cover.jpg", primary_video_url="https://video.example.org/live", gallery=["https://media.example.org/photo.jpg"],
                links=[{"kind": "audio", "label": "Концерт", "url": "https://media.example.org/audio.mp3"}], media_rights_confirmed=True,
                format="Камерный концерт", lineup="Вокал и гитара", program="Два отделения", genres=["Джаз"], duration_minutes=90, travel_cities=["Тула"],
                technical={"stage_area_m2": 12, "microphones": 2, "supplied_equipment": ["Микшер"]})
    first = save(client, ctx, body)
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    replay = save(client, ctx, body)
    assert replay.json()["idempotent"] is True
    assert save(client, ctx, {**body, "name": "Устаревшая правка"}).status_code == 409
    profile = client.get(f"/artists/{ctx['artist']['id']}").json()
    assert profile["presentation"]["program"] == "Два отделения"
    assert profile["rider"]["equipment"] == ["Микшер"]
    assert profile["name"] == "Живой концерт" and not profile["verified"]
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=auth_header(ctx["customer"]["token"])).json()
    assert room["quote"]["honorarium_rub"] == 100000
    with SessionLocal() as db:
        assert db.query(ArtistPresentation).count() == 1
        assert db.query(AuditLog).filter_by(action="artist.presentation_updated").count() == 1


@pytest.mark.parametrize("url", ["javascript:alert(1)", "http://example.org/photo", "https://localhost/file", "https://127.0.0.1/file", "https://user:pass@example.org/x"])
def test_unsafe_presentation_media_rejected(client, url):
    ctx = setup_negotiation(client)
    assert save(client, ctx, {**editor(client, ctx), "cover_url": url, "media_rights_confirmed": True}).status_code == 422


def test_presentation_ownership_readonly_and_media_rights(client, SessionLocal):
    ctx = setup_negotiation(client)
    body = editor(client, ctx)
    assert save(client, ctx, {**body, "cover_url": "https://example.org/photo"}).status_code == 422
    assert save(client, ctx, {**body, "verified": True}).status_code == 422
    path = f"/artists/{ctx['artist']['id']}/presentation"
    assert client.get(path, headers=auth_header(ctx["customer"]["token"])).status_code == 403
    assert client.put(path, json=body, headers=auth_header(ctx["customer"]["token"])).status_code == 403
    viewer = register(client, "epk-viewer@booker.test")
    with SessionLocal() as db:
        db.add(TeamMember(organization_id=ctx["artist_org"]["id"], user_id=viewer["user_id"], role="viewer"))
        db.commit()
    assert client.get(path, headers=auth_header(viewer["token"])).status_code == 200
    assert client.put(path, json=body, headers=auth_header(viewer["token"])).status_code == 403


def test_paid_volume_downgrade_preserves_content_without_authorizing_expansion(client, SessionLocal):
    ctx = setup_negotiation(client)
    body = editor(client, ctx)
    body.update(gallery=[f"https://example.org/{i}.jpg" for i in range(7)], media_rights_confirmed=True, layout="gallery_first")
    assert save(client, ctx, body).status_code == 403
    with SessionLocal() as db:
        db.add(Subscription(organization_id=ctx["artist_org"]["id"], plan_code="artist_pro", status="active", starts_at=now()-timedelta(days=1), current_period_end=now()+timedelta(days=1), billing_period="monthly"))
        db.commit()
    assert save(client, ctx, body).status_code == 200
    with SessionLocal() as db:
        db.query(Subscription).filter_by(organization_id=ctx["artist_org"]["id"]).one().current_period_end = now()-timedelta(seconds=1)
        db.commit()
    data = editor(client, ctx)
    assert len(data["gallery"]) == 7
    data["program"] = "Обновлённая программа"
    assert save(client, ctx, data).status_code == 200
    data = editor(client, ctx)
    assert save(client, ctx, {**data, "gallery": [*data["gallery"], "https://example.org/new.jpg"]}).status_code == 403
    public = client.get(f"/artists/{ctx['artist']['id']}").json()["presentation"]
    assert len(public["gallery"]) == 7 and public["layout"] == "standard"


def test_profile_open_slot_masks_busy_overlay_and_invalid_tariffs(client, SessionLocal):
    ctx = setup_negotiation(client)
    with SessionLocal() as db:
        slot = db.get(AvailabilitySlot, ctx["slot"]["id"])
        db.add(AvailabilitySlot(resource_type="artist", resource_id=ctx["artist"]["id"], starts_at=slot.starts_at, ends_at=slot.ends_at, status="busy"))
        db.commit()
    profile = client.get(f"/artists/{ctx['artist']['id']}").json()
    assert all(s["status"] != "open" for s in profile["slots"])
    for amount in [-1, True, 1.5, 1000000001]:
        assert client.post(f"/artists/{ctx['artist']['id']}/tariffs", json={"title": "Пакет", "honorarium_rub": amount}, headers=auth_header(ctx["owner"]["token"])).status_code == 422


def test_profile_reviews_do_not_import_other_artists_reputation(client, SessionLocal):
    from tests.test_reviews import _completed_booking
    ctx = _completed_booking(client)
    assert client.post(f"/bookings/{ctx['booking_id']}/reviews", json={"rating": 5, "text": "Спасибо"}, headers=ctx["ch"]).status_code == 200
    with SessionLocal() as db:
        other = Artist(organization_id=ctx["artist_org"]["id"], name="Другой артист", category="dj")
        db.add(other); db.commit(); other_id = other.id
    original = client.get(f"/artists/{ctx['artist']['id']}/reviews").json()
    assert original["count"] == 1 and original["average_rating"] is None
    assert "booking_id" not in json.dumps(original) and "author_user_id" not in json.dumps(original)
    assert client.get(f"/artists/{other_id}/reviews").json()["count"] == 0
