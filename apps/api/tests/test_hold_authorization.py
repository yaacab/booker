import pytest

from booker_api.models import AuditLog, AvailabilitySlot, Booking, BookingHold, Event, TeamMember
from tests.conftest import auth_header, register
from tests.test_event_budget import offer_for
from tests.test_event_readiness import venue_offer
from tests.test_matching import setup_matching


def acknowledged(client, ctx, offer):
    for side in ['customer', 'supplier']:
        response = client.post(f"/offers/{offer['id']}/ack", headers=ctx['headers'], json={'side': side})
        assert response.status_code == 200, response.text


def assert_unheld(SessionLocal, offers):
    with SessionLocal() as db:
        assert db.query(BookingHold).count() == 0
        assert db.query(AuditLog).filter_by(action='hold.created').count() == 0
        for offer in offers:
            booking = db.get(Booking, offer['booking_id'])
            assert booking.status == 'Negotiation'
            assert db.get(AvailabilitySlot, booking.slot_id).status == 'open'


@pytest.mark.parametrize('closed', ['Completed', 'Cancelled'])
@pytest.mark.parametrize('atomic', [False, True])
def test_closed_event_cannot_acquire_holds(client, SessionLocal, closed, atomic):
    ctx = setup_matching(client)
    offers = [offer_for(client, SessionLocal, ctx), venue_offer(client, SessionLocal, ctx)]
    for offer in offers:
        acknowledged(client, ctx, offer)
    with SessionLocal() as db:
        db.get(Event, ctx['event']['id']).status = closed
        db.commit()
    path = f"/events/{ctx['event']['id']}/holds/atomic" if atomic else f"/bookings/{offers[0]['booking_id']}/hold"
    response = client.post(path, headers=ctx['headers'], json={'booking_ids': [o['booking_id'] for o in offers]})
    assert response.status_code == 409, response.text
    assert 'Событие закрыто' in response.json()['detail']
    assert_unheld(SessionLocal, offers)
    assert client.get(f"/deal-room/{offers[0]['booking_id']}", headers=ctx['headers']).json()['can_hold'] is False


@pytest.mark.parametrize('side', ['supplier', 'customer'])
def test_viewer_cannot_hold_even_with_confirm_flag(client, SessionLocal, side):
    ctx = setup_matching(client)
    offer = offer_for(client, SessionLocal, ctx)
    acknowledged(client, ctx, offer)
    viewer = register(client, 'hold-viewer@booker.test')
    organization_id = ctx['supply']['id'] if side == 'supplier' else ctx['customer']['id']
    with SessionLocal() as db:
        db.add(TeamMember(user_id=viewer['user_id'], organization_id=organization_id, role='viewer', can_confirm_offer=True))
        db.commit()
    room = client.get(f"/deal-room/{offer['booking_id']}", headers=auth_header(viewer['token'])).json()
    assert room['can_hold'] is False
    response = client.post(f"/bookings/{offer['booking_id']}/hold", headers=auth_header(viewer['token']))
    assert response.status_code == 403, response.text
    assert_unheld(SessionLocal, [offer])
    with SessionLocal() as db:
        db.query(TeamMember).filter_by(user_id=viewer['user_id']).one().role = 'manager'
        db.commit()
    response = client.post(f"/bookings/{offer['booking_id']}/hold", headers=auth_header(viewer['token']))
    assert response.status_code == 200, response.text
