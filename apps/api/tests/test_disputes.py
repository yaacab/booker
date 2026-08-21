from tests.conftest import auth_header
from tests.test_payments import _awaiting_payment, _sign


def _confirm(client):
    ctx = _awaiting_payment(client)
    client.post(
        "/payments/webhook",
        json={
            "event_id": "evt-dispute",
            "payment_id": ctx["payment_id"],
            "status": "succeeded",
            "signature": _sign("evt-dispute", ctx["payment_id"], "succeeded"),
        },
    )
    return ctx


def test_dispute_requires_category_from_list(client):
    ctx = _confirm(client)
    free = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "whatever", "notes": "текст"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert free.status_code == 400
    ok = client.post(
        f"/bookings/{ctx['booking_id']}/disputes",
        json={"category": "no_show", "notes": "артист не приехал"},
        headers=auth_header(ctx["customer"]["token"]),
    )
    assert ok.status_code == 200
    assert ok.json()["ai_decides"] is False
    room = client.get(
        f"/deal-room/{ctx['booking_id']}",
        headers=auth_header(ctx["customer"]["token"]),
    ).json()
    assert room["status"] == "Dispute"
