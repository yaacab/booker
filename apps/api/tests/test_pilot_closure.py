from tests.conftest import auth_header
from tests.test_offers import ack_both, setup_negotiation
from tests.test_payments import _awaiting_payment


def test_confirmed_booking_is_not_a_completed_performance(client):
    ctx = _awaiting_payment(client)
    ch = auth_header(ctx["customer"]["token"])
    assert (
        client.post(
            f"/payments/{ctx['payment_id']}/stub-complete",
            json={"status": "succeeded"},
            headers=ch,
        ).status_code
        == 200
    )
    artist = client.get(f"/artists/{ctx['artist']['id']}").json()
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=ch).json()
    assert room["status"] == "Confirmed"
    assert artist["facts"]["deals"] == 0


def test_deal_room_links_event_and_lists_documents(client):
    ctx = setup_negotiation(client)
    ack_both(client, ctx)
    ch = auth_header(ctx["customer"]["token"])
    assert client.post(f"/bookings/{ctx['booking_id']}/hold", headers=ch).status_code == 200
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=ch).json()
    assert room["event_id"]
    assert room["workspace_kind"] == "customer"
    assert room["documents"]
    assert room["documents"][0]["kind"] == "offer"
    assert room["documents"][0]["quote_id"]
