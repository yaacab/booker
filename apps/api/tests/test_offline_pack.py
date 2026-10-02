from tests.conftest import auth_header, register
from tests.test_offers import setup_negotiation


def test_event_offline_pack(client):
    ctx = setup_negotiation(client)
    events = client.get(
        f"/events?organization_id={ctx['cust_org']['id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    event_id = events["items"][0]["id"]
    res = client.get(
        f"/events/{event_id}/offline-pack",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["event"]["id"] == event_id
    assert "requirements" in body
    assert "requests" in body
    assert body["generated_at"]


def test_private_event_offline_pack_and_day_status_deny_foreign_member(client):
    ctx = setup_negotiation(client)
    outsider = register(client, "offline-pack-outsider@booker.test", "Outsider")
    foreign_org = client.post(
        "/orgs", json={"name": "Foreign Event Viewer", "kind": "customer"},
        headers=auth_header(outsider["token"]),
    )
    assert foreign_org.status_code == 200
    event_id = ctx["event"]["id"]
    for suffix in ("offline-pack", "day-status"):
        url = f"/events/{event_id}/{suffix}"
        assert client.get(url).status_code == 401
        denied = client.get(url, headers=auth_header(outsider["token"]))
        assert denied.status_code == 403
        assert "Корпоратив".encode() not in denied.content


def test_replacement_plan_checks_event_and_requirement_binding(client):
    ctx = setup_negotiation(client)
    event_id = ctx["event"]["id"]
    requirement_id = ctx["event"]["requirements"][0]["id"]
    outsider = register(client, "replacement-outsider@booker.test", "Outsider")
    path = f"/events/{event_id}/requirements/{requirement_id}/replacement"
    assert client.get(path, headers=auth_header(outsider["token"])).status_code == 403

    other_event = client.post(
        "/events",
        json={
            "organization_id": ctx["cust_org"]["id"],
            "title": "Другая приватная программа",
            "event_date": "2030-01-01T18:00:00+00:00",
            "requirements": [{"category_code": "dj", "qty": 1, "required": True}],
        },
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert other_event.status_code == 200, other_event.text
    foreign_requirement_id = other_event.json()["requirements"][0]["id"]
    mismatch = client.get(
        f"/events/{event_id}/requirements/{foreign_requirement_id}/replacement",
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert mismatch.status_code == 404
