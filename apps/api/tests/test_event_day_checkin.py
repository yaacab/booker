from tests.conftest import auth_header, register
from tests.test_payments import _awaiting_payment


def _confirmed_booking(client):
    ctx = _awaiting_payment(client)
    ch = auth_header(ctx["customer"]["token"])
    res = client.post(
        f"/payments/{ctx['payment_id']}/stub-complete",
        json={"status": "succeeded"},
        headers=ch,
    )
    assert res.status_code == 200, res.text
    assert res.json()["booking_status"] == "Confirmed"
    events = client.get(
        f"/events?organization_id={ctx['cust_org']['id']}",
        headers=ch,
    ).json()
    ctx["event_id"] = events["items"][0]["id"]
    ctx["ch"] = ch
    return ctx


def test_day_status_before_checkin(client):
    ctx = _confirmed_booking(client)
    res = client.get(f"/events/{ctx['event_id']}/day-status", headers=ctx["ch"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["can_event_check_in"] is True
    assert body["can_event_check_out"] is False
    assert body["summary"]["confirmed"] == 1
    assert len(body["bookings"]) == 1
    assert body["bookings"][0]["can_check_in"] is True


def test_event_check_in_and_out(client):
    ctx = _confirmed_booking(client)
    check_in = client.post(f"/events/{ctx['event_id']}/check-in", headers=ctx["ch"])
    assert check_in.status_code == 200, check_in.text
    data = check_in.json()
    assert data["event_status"] == "InProgress"
    assert len(data["checked_in_bookings"]) == 1
    assert data["day_status"]["summary"]["in_progress"] == 1

    bad = client.post(f"/events/{ctx['event_id']}/check-in", headers=ctx["ch"])
    assert bad.status_code == 409

    check_out = client.post(f"/events/{ctx['event_id']}/check-out", headers=ctx["ch"])
    assert check_out.status_code == 200, check_out.text
    out = check_out.json()
    assert out["event_status"] == "Completed"
    assert out["day_status"]["summary"]["completed"] == 1


def test_booking_check_in_supplier(client):
    ctx = _confirmed_booking(client)
    oh = auth_header(ctx["owner"]["token"])
    res = client.post(f"/bookings/{ctx['booking_id']}/check-in", headers=oh)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "InProgress"
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=oh).json()
    assert room["status"] == "InProgress"


def test_booking_check_out_auto_completes_event(client):
    ctx = _confirmed_booking(client)
    client.post(f"/events/{ctx['event_id']}/check-in", headers=ctx["ch"])
    res = client.post(f"/bookings/{ctx['booking_id']}/check-out", headers=ctx["ch"])
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "Completed"
    assert res.json()["event_status"] == "Completed"
    event = client.get(f"/events/{ctx['event_id']}", headers=ctx["ch"]).json()
    assert event["status"] == "Completed"


def test_check_in_forbidden_for_stranger(client):
    ctx = _confirmed_booking(client)
    stranger = register(client, "stranger@booker.test", "Чужой")
    res = client.post(
        f"/events/{ctx['event_id']}/check-in",
        headers=auth_header(stranger["token"]),
    )
    assert res.status_code in {403, 404}
