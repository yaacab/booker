"""HTTP authorization checks for the customer event surface."""

import pytest

from booker_api.models import AuditLog, Event, EventTeamRequirement, Request
from tests.conftest import auth_header, register
from tests.test_quick_request_event import _setup


def _actors(client):
    ctx = _setup(client)
    outsider = register(client, "event-gap-outsider@booker.test", "Чужой")
    outsider_header = auth_header(outsider["token"])
    other_org = client.post(
        "/orgs", json={"name": "Другой заказчик", "kind": "customer"}, headers=outsider_header
    )
    assert other_org.status_code == 200, other_org.text
    other_event = client.post(
        "/events",
        json={
            "organization_id": other_org.json()["id"],
            "title": "Чужое событие",
            "event_date": "2026-11-01T18:00:00+00:00",
        },
        headers=outsider_header,
    )
    assert other_event.status_code == 200, other_event.text
    return ctx, outsider_header, other_org.json()["id"], other_event.json()["id"]


def _state(SessionLocal, event_id):
    with SessionLocal() as db:
        event = db.get(Event, event_id)
        return (
            event.status,
            event.title,
            tuple(
                (r.id, r.category_code, r.qty, r.notes)
                for r in db.query(EventTeamRequirement)
                .filter_by(event_id=event_id)
                .order_by(EventTeamRequirement.id)
            ),
            tuple(r.id for r in db.query(Request).filter_by(event_id=event_id).order_by(Request.id)),
            db.query(AuditLog).count(),
            db.query(Event).count(),
            db.query(Request).count(),
        )


def test_event_list_is_tenant_scoped_and_foreign_filter_is_denied(client, SessionLocal):
    ctx, outsider_header, other_org_id, other_event_id = _actors(client)
    own_event_id = ctx["event"]["id"]
    before = _state(SessionLocal, own_event_id)

    viewer_list = client.get("/events", headers=ctx["vh"])
    assert viewer_list.status_code == 200
    assert own_event_id in {row["id"] for row in viewer_list.json()["items"]}
    assert other_event_id not in {row["id"] for row in viewer_list.json()["items"]}

    outsider_list = client.get("/events", headers=outsider_header)
    assert outsider_list.status_code == 200
    assert other_event_id in {row["id"] for row in outsider_list.json()["items"]}
    assert own_event_id not in {row["id"] for row in outsider_list.json()["items"]}

    for headers, foreign_org_id in ((ctx["vh"], other_org_id), (outsider_header, ctx["cust_org"]["id"])):
        denied = client.get("/events", params={"organization_id": foreign_org_id}, headers=headers)
        assert denied.status_code == 403
    assert _state(SessionLocal, own_event_id) == before


def test_event_detail_denies_outsider_but_allows_org_viewer(client, SessionLocal):
    ctx, outsider_header, _, other_event_id = _actors(client)
    own_event_id = ctx["event"]["id"]
    before = _state(SessionLocal, own_event_id)
    allowed = client.get(f"/events/{own_event_id}", headers=ctx["vh"])
    assert allowed.status_code == 200
    assert allowed.json()["id"] == own_event_id
    for event_id, headers in ((own_event_id, outsider_header), (other_event_id, ctx["vh"])):
        denied = client.get(f"/events/{event_id}", headers=headers)
        assert denied.status_code == 403
    assert _state(SessionLocal, own_event_id) == before


@pytest.mark.parametrize("route", ["check-out", "requirements", "requests"])
def test_event_mutations_deny_viewer_and_foreign_tenant_without_writes(client, SessionLocal, route):
    ctx, outsider_header, _, other_event_id = _actors(client)
    own_event_id = ctx["event"]["id"]
    own_before = _state(SessionLocal, own_event_id)
    other_before = _state(SessionLocal, other_event_id)

    for event_id, headers in ((own_event_id, ctx["vh"]), (own_event_id, outsider_header), (other_event_id, ctx["vh"])):
        url = f"/events/{event_id}/{route}"
        if route == "check-out":
            denied = client.post(url, headers=headers)
        elif route == "requirements":
            denied = client.put(url, json={"items": [{"category_code": "host", "qty": 2}]}, headers=headers)
        else:
            denied = client.post(
                url,
                json={"resource_type": "artist", "resource_id": ctx["artist"]["id"]},
                headers=headers,
            )
        assert denied.status_code == 403, (url, denied.text)
        assert _state(SessionLocal, own_event_id) == own_before
        assert _state(SessionLocal, other_event_id) == other_before


def test_quick_request_with_event_denies_viewer_and_foreign_tenant_without_writes(client, SessionLocal):
    ctx, outsider_header, _, other_event_id = _actors(client)
    own_event_id = ctx["event"]["id"]
    own_before = _state(SessionLocal, own_event_id)
    other_before = _state(SessionLocal, other_event_id)
    for event_id, headers in ((own_event_id, ctx["vh"]), (own_event_id, outsider_header), (other_event_id, ctx["vh"])):
        denied = client.post(
            "/quick-request",
            json={
                "artist_id": ctx["artist"]["id"],
                "slot_id": ctx["slot"]["id"],
                "event_id": event_id,
            },
            headers=headers,
        )
        assert denied.status_code == 403, denied.text
        assert _state(SessionLocal, own_event_id) == own_before
        assert _state(SessionLocal, other_event_id) == other_before
