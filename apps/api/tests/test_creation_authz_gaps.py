"""Negative authorization checks for top-level catalog and event creation."""

import pytest

from booker_api.models import Artist, AuditLog, Event, Venue, VenueHall
from tests.conftest import auth_header, register


@pytest.mark.parametrize("kind", ("artist", "venue", "event"))
@pytest.mark.parametrize("actor", ("viewer", "outsider"))
def test_top_level_creation_rejects_viewer_and_foreign_owner_without_writes(
    client, SessionLocal, kind, actor
):
    owner = register(client, "create-acl-owner@booker.test", "Owner")
    viewer = register(client, "create-acl-viewer@booker.test", "Viewer")
    outsider = register(client, "create-acl-outsider@booker.test", "Outsider")
    owner_headers = auth_header(owner["token"])
    org = client.post(
        "/orgs",
        json={"name": "Create ACL", "kind": "customer" if kind == "event" else kind},
        headers=owner_headers,
    ).json()
    added = client.post(
        f"/orgs/{org['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=owner_headers,
    )
    assert added.status_code == 200, added.text
    with SessionLocal() as db:
        before = tuple(db.query(model).count() for model in (
            Artist, Venue, VenueHall, Event, AuditLog,
        ))
    path, body = {
        "artist": ("/artists", {"organization_id": org["id"], "name": "Чужой артист", "category": "dj"}),
        "venue": ("/venues", {"organization_id": org["id"], "name": "Чужая площадка", "capacity": 80}),
        "event": ("/events", {"organization_id": org["id"], "title": "Чужое событие", "event_date": "2026-11-01T18:00:00+00:00"}),
    }[kind]
    token = viewer["token"] if actor == "viewer" else outsider["token"]
    denied = client.post(path, json=body, headers=auth_header(token))
    assert denied.status_code == 403, denied.text
    with SessionLocal() as db:
        assert tuple(db.query(model).count() for model in (
            Artist, Venue, VenueHall, Event, AuditLog,
        )) == before
