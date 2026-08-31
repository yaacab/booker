from tests.conftest import auth_header, register


def test_client_event_writes_audit(client):
    user = register(client, "analytics@booker.test", "Analytics")
    res = client.post(
        "/analytics/events",
        json={"name": "event.studio.completed", "properties": {"step_count": 5}},
        headers=auth_header(user["token"]),
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_client_event_ignores_unknown_name(client):
    user = register(client, "analytics2@booker.test", "Analytics")
    res = client.post(
        "/analytics/events",
        json={"name": "not.allowed", "properties": {}},
        headers=auth_header(user["token"]),
    )
    assert res.status_code == 200
    assert res.json()["ignored"] is True


def test_client_event_requires_auth(client):
    res = client.post("/analytics/events", json={"name": "page.view", "properties": {}})
    assert res.status_code == 401


def test_cabinet_events_allowed(client):
    user = register(client, "cabinet-analytics@booker.test", "Cabinet")
    for name in (
        "cabinet.viewed",
        "cabinet.offer_sent",
        "cabinet.service_created",
        "cabinet.ical_imported",
        "cabinet.vacation_set",
    ):
        res = client.post(
            "/analytics/events",
            json={"name": name, "properties": {"kind": "artist"}},
            headers=auth_header(user["token"]),
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True
