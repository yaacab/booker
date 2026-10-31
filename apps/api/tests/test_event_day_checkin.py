from tests.conftest import auth_header, register
from tests.test_payments import _awaiting_payment


def _confirmed_booking(client, offer_overrides=None, before_contract=None):
    ctx = _awaiting_payment(client, offer_overrides, before_contract)
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


def test_incomplete_required_composition_blocks_event_and_booking_check_in(client):
    changed = {}

    def require_two(before_client, before_ctx):
        headers = auth_header(before_ctx["customer"]["token"])
        event = before_client.get(
            f"/events/{before_ctx['event']['id']}", headers=headers
        ).json()
        requirement = event["requirements"][0]
        changed["requirement"] = requirement
        replaced = before_client.put(
            f"/events/{before_ctx['event']['id']}/requirements",
            json={"items": [{
                "id": requirement["id"],
                "category_code": requirement["category_code"],
                "role_label": requirement["role_label"],
                "qty": 2,
                "required": True,
            }]},
            headers=headers,
        )
        assert replaced.status_code == 200, replaced.text

    ctx = _confirmed_booking(client, before_contract=require_two)
    requirement = changed["requirement"]

    day = client.get(f"/events/{ctx['event_id']}/day-status", headers=ctx["ch"])
    assert day.status_code == 200, day.text
    assert day.json()["can_event_check_in"] is False
    assert day.json()["readiness"] == {
        "state": "incomplete",
        "required_total": 2,
        "ready_total": 1,
        "missing_total": 1,
        "positions": [
            {
                "requirement_id": requirement["id"],
                "category_code": requirement["category_code"],
                "role_label": requirement["role_label"],
                "required": 2,
                "ready": 1,
                "missing": 1,
                "blocker": "no_request",
            }
        ],
        "payment_blockers": [],
    }

    event_check_in = client.post(
        f"/events/{ctx['event_id']}/check-in", headers=ctx["ch"]
    )
    assert event_check_in.status_code == 409
    booking_check_in = client.post(
        f"/bookings/{ctx['booking_id']}/check-in", headers=ctx["ch"]
    )
    assert booking_check_in.status_code == 409

    unchanged_event = client.get(
        f"/events/{ctx['event_id']}", headers=ctx["ch"]
    ).json()
    unchanged_room = client.get(
        f"/deal-room/{ctx['booking_id']}", headers=ctx["ch"]
    ).json()
    assert unchanged_event["status"] != "InProgress"
    assert unchanged_room["status"] == "Confirmed"


def test_unfilled_optional_requirement_does_not_block_event_check_in(client):
    def add_optional(before_client, before_ctx):
        headers = auth_header(before_ctx["customer"]["token"])
        event = before_client.get(
            f"/events/{before_ctx['event']['id']}", headers=headers
        ).json()
        requirement = event["requirements"][0]
        replaced = before_client.put(
            f"/events/{before_ctx['event']['id']}/requirements",
            json={"items": [
                {
                    "id": requirement["id"],
                    "category_code": requirement["category_code"],
                    "role_label": requirement["role_label"],
                    "qty": 1,
                    "required": True,
                },
                {
                    "category_code": "photographer",
                    "role_label": "Фотограф",
                    "qty": 1,
                    "required": False,
                },
            ]},
            headers=headers,
        )
        assert replaced.status_code == 200, replaced.text

    ctx = _confirmed_booking(client, before_contract=add_optional)

    day = client.get(f"/events/{ctx['event_id']}/day-status", headers=ctx["ch"])
    assert day.status_code == 200, day.text
    assert day.json()["readiness"]["state"] == "ready"
    assert day.json()["readiness"]["required_total"] == 1
    assert day.json()["can_event_check_in"] is True

    check_in = client.post(f"/events/{ctx['event_id']}/check-in", headers=ctx["ch"])
    assert check_in.status_code == 200, check_in.text
    assert check_in.json()["event_status"] == "InProgress"


def test_overdue_required_balance_blocks_check_in_until_satisfied(client):
    overdue_due = "2020-01-01T10:00:00+00:00"
    overdue_grace = "2020-01-01T12:00:00+00:00"
    ctx = _confirmed_booking(
        client,
        {
            "advance_rub": 40000,
            "payment_terms": {
                "balance": {
                    "due_at": overdue_due,
                    "grace_until": overdue_grace,
                    "required_before_check_in": True,
                }
            },
        },
    )
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=ctx["ch"]).json()
    balance = next(row for row in room["payment_obligations"] if row["kind"] == "balance")
    assert balance["effective_state"] == "overdue"
    assert balance["blocks_check_in"] is True

    day = client.get(f"/events/{ctx['event_id']}/day-status", headers=ctx["ch"]).json()
    assert day["can_event_check_in"] is False
    assert day["readiness"]["payment_blockers"][0]["booking_id"] == ctx["booking_id"]
    assert client.post(
        f"/events/{ctx['event_id']}/check-in", headers=ctx["ch"]
    ).status_code == 409
    assert client.post(
        f"/bookings/{ctx['booking_id']}/check-in", headers=ctx["ch"]
    ).status_code == 409

    payment = client.post(
        f"/bookings/{ctx['booking_id']}/payments",
        json={"idempotency_key": "balance-for-event-day", "obligation_id": balance["id"]},
        headers=ctx["ch"],
    )
    assert payment.status_code == 200, payment.text
    completed = client.post(
        f"/payments/{payment.json()['id']}/stub-complete",
        json={"status": "succeeded"},
        headers=ctx["ch"],
    )
    assert completed.status_code == 200, completed.text
    allowed = client.post(f"/events/{ctx['event_id']}/check-in", headers=ctx["ch"])
    assert allowed.status_code == 200, allowed.text


def test_booking_check_out_auto_completes_event(client):
    ctx = _confirmed_booking(client)
    client.post(f"/events/{ctx['event_id']}/check-in", headers=ctx["ch"])
    res = client.post(f"/bookings/{ctx['booking_id']}/check-out", headers=ctx["ch"])
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "Completed"
    assert res.json()["event_status"] == "Completed"
    event = client.get(f"/events/{ctx['event_id']}", headers=ctx["ch"]).json()
    assert event["status"] == "Completed"


def test_booking_viewer_cannot_check_out(client):
    ctx = _confirmed_booking(client)
    viewer = register(client, "checkout-viewer@booker.test", "Наблюдатель")
    added = client.post(
        f"/orgs/{ctx['cust_org']['id']}/members",
        json={"user_id": viewer["user_id"], "role": "viewer"},
        headers=ctx["ch"],
    )
    assert added.status_code == 200
    assert client.post(
        f"/bookings/{ctx['booking_id']}/check-in", headers=ctx["ch"]
    ).status_code == 200
    denied = client.post(
        f"/bookings/{ctx['booking_id']}/check-out",
        headers=auth_header(viewer["token"]),
    )
    assert denied.status_code == 403


def test_check_in_forbidden_for_stranger(client):
    ctx = _confirmed_booking(client)
    stranger = register(client, "stranger@booker.test", "Чужой")
    res = client.post(
        f"/events/{ctx['event_id']}/check-in",
        headers=auth_header(stranger["token"]),
    )
    assert res.status_code in {403, 404}


def test_check_out_event_preserves_in_progress_when_confirmed_remain(monkeypatch):
    """Event must not become Completed while a Confirmed booking is still open."""
    from types import SimpleNamespace

    from booker_api import event_day

    event = SimpleNamespace(id="evt-1", status="InProgress")
    in_progress = SimpleNamespace(id="b-ip", status="InProgress")
    confirmed = SimpleNamespace(id="b-cf", status="Confirmed")

    def fake_bookings(_db, _event_id):
        return [(None, in_progress), (None, confirmed)]

    monkeypatch.setattr(event_day, "event_bookings", fake_bookings)
    result = event_day.check_out_event(db=None, event=event)
    assert result["checked_out_bookings"] == ["b-ip"]
    assert result["remaining_active_bookings"] == ["b-cf"]
    assert result["event_status"] == "InProgress"
    assert event.status == "InProgress"
    assert in_progress.status == "Completed"
    assert confirmed.status == "Confirmed"
