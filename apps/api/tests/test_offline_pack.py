from tests.conftest import auth_header
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
