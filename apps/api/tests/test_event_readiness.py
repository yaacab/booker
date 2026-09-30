from datetime import timedelta

import pytest

from booker_api.models import AvailabilitySlot, Booking, BookingHold, Event, TeamMember
from booker_api.security import now
from tests.conftest import auth_header, contract_otps, register
from tests.test_event_budget import offer_for
from tests.test_matching import setup_matching


def readiness(client, ctx):
    response = client.get(f"/events/{ctx['event']['id']}/readiness", headers=ctx['headers'])
    assert response.status_code == 200, response.text
    return response.json()


def venue_offer(client, SessionLocal, ctx):
    req = client.post(f"/events/{ctx['event']['id']}/requests", headers=ctx['headers'], json={'resource_type': 'hall', 'resource_id': ctx['venue']['hall_id'], 'requirement_id': ctx['event']['requirements'][1]['id']}).json()
    with SessionLocal() as db:
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.resource_id == ctx['venue']['hall_id'],
                AvailabilitySlot.starts_at <= ctx['start'],
                AvailabilitySlot.ends_at >= ctx['end'],
            )
            .one()
            .id
        )
    response = client.post(f"/requests/{req['id']}/offers", headers=ctx['headers'], json={'slot_id': slot, 'honorarium_rub': 100000})
    assert response.status_code == 200, response.text
    return response.json()


def hold(client, ctx, offer):
    for side in ['customer', 'supplier']:
        assert client.post(f"/offers/{offer['id']}/ack", headers=ctx['headers'], json={'side': side}).status_code == 200
    assert client.post(f"/bookings/{offer['booking_id']}/hold", headers=ctx['headers']).status_code == 200


def pay(client, SessionLocal, ctx, offer):
    contract = client.post(f"/bookings/{offer['booking_id']}/contract", headers=ctx['headers']).json()
    otps = contract_otps(SessionLocal, contract['id'])
    for side in ['customer', 'supplier']:
        assert client.post(f"/contracts/{contract['id']}/sign", headers=ctx['headers'], json={'side': side, 'otp': otps[f'otp_{side}']}).status_code == 200
    payment = client.post(f"/bookings/{offer['booking_id']}/payments", headers=ctx['headers'], json={'idempotency_key': offer['id']}).json()
    assert client.post(f"/payments/{payment['id']}/stub-complete", headers=ctx['headers'], json={}).status_code == 200


def test_actual_lifecycle_not_deal_room_existence_drives_readiness(client, SessionLocal):
    ctx = setup_matching(client)
    initial = readiness(client, ctx)
    assert initial['required_total'] == 2 and initial['required_confirmed'] == 0
    assert initial['next_best_action']['code'] == 'select'
    dj, venue = offer_for(client, SessionLocal, ctx, 1), venue_offer(client, SessionLocal, ctx)
    event_data = client.get(f"/events/{ctx['event']['id']}", headers=ctx['headers']).json()
    assert all(r['booking_status'] == 'Negotiation' for r in event_data['requests'])
    offered = readiness(client, ctx)
    assert offered['score'] > initial['score']
    assert not offered['event_ready'] and offered['required_confirmed'] == 0
    assert offered['next_best_action']['code'] == 'acknowledge'
    for offer in [dj, venue]:
        hold(client, ctx, offer)
    held = readiness(client, ctx)
    assert held['score'] > offered['score'] and held['required_confirmed'] == 0
    assert all(p['checks']['reserved'] for p in held['participants'])
    assert held['next_best_action']['code'] == 'contract'
    pay(client, SessionLocal, ctx, dj)
    partial = readiness(client, ctx)
    assert partial['required_confirmed'] == 1 and not partial['event_ready']
    pay(client, SessionLocal, ctx, venue)
    ready = readiness(client, ctx)
    assert ready['score'] == 100 and ready['event_ready']
    assert ready['required_confirmed'] == 2 and ready['test_payments'] == 2
    assert ready['blockers'] == []
    assert ready['next_best_action']['href'].endswith('#event-day')


def test_unknown_technical_facts_cannot_become_ready_after_payment(client, SessionLocal):
    ctx = setup_matching(client)
    dj, venue = offer_for(client, SessionLocal, ctx, 0), venue_offer(client, SessionLocal, ctx)
    for offer in [dj, venue]:
        hold(client, ctx, offer); pay(client, SessionLocal, ctx, offer)
    result = readiness(client, ctx)
    assert result['required_confirmed'] == 2 and result['score'] < 100
    assert not result['event_ready'] and result['next_best_action']['code'] == 'compatibility'
    assert result['compatibility'][0]['to_resolve']


@pytest.mark.parametrize("captured_amount", [1, 74200])
def test_expired_hold_is_read_only_and_late_capture_needs_operator(client, SessionLocal, captured_amount):
    ctx = setup_matching(client)
    dj = offer_for(client, SessionLocal, ctx, 1)
    hold(client, ctx, dj)
    with SessionLocal() as db:
        db.query(BookingHold).filter_by(booking_id=dj['booking_id']).one().expires_at = now() - timedelta(seconds=1); db.commit()
    result = readiness(client, ctx)
    assert result['next_best_action']['code'] == 'hold_expired'
    assert not result['participants'][0]['checks']['reserved']
    with SessionLocal() as db:
        assert db.get(Booking, dj['booking_id']).status == 'DateHeld'
        from booker_api.models import Payment
        db.add(Payment(booking_id=dj['booking_id'], amount_rub=captured_amount, status='succeeded', provider='stub', idempotency_key='late'))
        db.get(Booking, dj['booking_id']).status = 'Cancelled'; db.commit()
    result = readiness(client, ctx)
    assert result['next_best_action']['code'] == 'operator' and not result['event_ready']


def test_wrong_booked_window_is_not_hidden_by_another_open_slot(client, SessionLocal):
    ctx = setup_matching(client)
    dj = offer_for(client, SessionLocal, ctx, 1)
    hold(client, ctx, dj)
    with SessionLocal() as db:
        booked = db.get(AvailabilitySlot, db.get(Booking, dj['booking_id']).slot_id)
        booked.starts_at -= timedelta(days=1); booked.ends_at -= timedelta(days=1)
        db.add(AvailabilitySlot(resource_type='artist', resource_id=ctx['artists'][1]['id'], starts_at=ctx['start']-timedelta(hours=1), ends_at=ctx['end']+timedelta(hours=1), status='open')); db.commit()
    result = readiness(client, ctx)
    assert result['participants'][0]['calendar_status'] == 'incompatible'
    assert result['next_best_action']['code'] == 'calendar'


def test_readiness_object_auth_and_org_overview_do_not_expose_other_events(client, SessionLocal):
    ctx = setup_matching(client)
    outsider = register(client, 'readiness-outsider@booker.test')
    viewer = register(client, 'readiness-viewer@booker.test')
    with SessionLocal() as db:
        db.add(TeamMember(organization_id=ctx['customer']['id'], user_id=viewer['user_id'], role='viewer')); db.commit()
    detail = f"/events/{ctx['event']['id']}/readiness"
    overview = f"/orgs/{ctx['customer']['id']}/event-readiness"
    for path in [detail, overview]:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=auth_header(outsider['token'])).status_code == 403
        assert client.get(path, headers=auth_header(viewer['token'])).status_code == 200
    items = client.get(overview, headers=ctx['headers']).json()['items']
    assert [i['event_id'] for i in items] == [ctx['event']['id']]
    assert 'participants' not in items[0]
    with SessionLocal() as db:
        db.get(Event, ctx['event']['id']).status = 'Completed'; db.commit()
    assert client.get(overview, headers=ctx['headers']).json()['items'] == []
    result = readiness(client, ctx)
    assert result['state'] == 'completed' and result['score'] is None and not result['event_ready']


def test_empty_window_and_no_required_roles_have_explicit_next_actions(client, SessionLocal):
    ctx = setup_matching(client)
    with SessionLocal() as db:
        db.get(Event, ctx['event']['id']).ends_at = None; db.commit()
    result = readiness(client, ctx)
    assert result['next_best_action']['code'] == 'event_window'
    assert not result['event_ready']
    with SessionLocal() as db:
        from booker_api.models import EventTeamRequirement
        db.get(Event, ctx['event']['id']).ends_at = ctx['end']
        for r in db.query(EventTeamRequirement).filter_by(event_id=ctx['event']['id']):
            r.required = False
        db.commit()
    result = readiness(client, ctx)
    assert result['required_total'] == 0 and result['score'] == 0 and result['next_best_action']['code'] == 'requirements'
    assert not result['event_ready']


def test_busy_overlay_and_dispute_are_not_prepared(client, SessionLocal):
    ctx = setup_matching(client)
    dj, venue = offer_for(client, SessionLocal, ctx, 1), venue_offer(client, SessionLocal, ctx)
    for offer in [dj, venue]:
        hold(client, ctx, offer); pay(client, SessionLocal, ctx, offer)
    with SessionLocal() as db:
        db.add(AvailabilitySlot(resource_type='artist', resource_id=ctx['artists'][1]['id'], starts_at=ctx['start'], ends_at=ctx['end'], status='busy')); db.commit()
    result = readiness(client, ctx)
    assert result['required_confirmed'] == 2 and not result['event_ready']
    assert result['next_best_action']['code'] == 'calendar'
    with SessionLocal() as db:
        db.get(Booking, dj['booking_id']).status = 'Dispute'
        db.get(Event, ctx['event']['id']).status = 'InProgress'; db.commit()
    result = readiness(client, ctx)
    assert result['required_confirmed'] == 1 and result['next_best_action']['code'] == 'operator'


def test_one_expired_deal_cannot_fill_multiple_positions(client, SessionLocal):
    ctx = setup_matching(client)
    role_id = ctx['event']['requirements'][0]['id']
    assert client.put(f"/events/{ctx['event']['id']}/requirements", headers=ctx['headers'], json={'items': [{'id': role_id, 'category_code': 'dj', 'qty': 2}]}).status_code == 200
    dj = offer_for(client, SessionLocal, ctx, 1)
    hold(client, ctx, dj)
    with SessionLocal() as db:
        db.query(BookingHold).filter_by(booking_id=dj['booking_id']).one().expires_at = now() - timedelta(seconds=1); db.commit()
    result = readiness(client, ctx)
    assert len([p for p in result['participants'] if p['booking_id'] == dj['booking_id']]) == 1
    assert result['required_total'] == 2 and result['required_confirmed'] == 0


def test_confirmed_status_without_documents_or_payment_requires_operator(client, SessionLocal):
    ctx = setup_matching(client)
    dj = offer_for(client, SessionLocal, ctx, 1)
    with SessionLocal() as db:
        db.get(Booking, dj['booking_id']).status = 'Confirmed'; db.commit()
    result = readiness(client, ctx)
    assert not result['event_ready'] and result['next_best_action']['code'] == 'operator'
    assert result['next_best_action']['href'] == f"/deals/{dj['booking_id']}"


def test_historic_missing_end_can_be_filled_within_existing_slots_only(client, SessionLocal):
    from booker_api.models import OfferVersion
    ctx = setup_matching(client)
    dj = offer_for(client, SessionLocal, ctx, 1)
    hold(client, ctx, dj)
    with SessionLocal() as db:
        db.get(Event, ctx['event']['id']).ends_at = None; db.commit()
    matching = client.get(ctx['path'], headers=ctx['headers']).json()
    assert matching['can_adjust_end']
    path = f"/events/{ctx['event']['id']}/planning-context"
    assert client.patch(path, headers=ctx['headers'], json={'expected_context': matching['context_token'], 'ends_at': (ctx['end']+timedelta(hours=2)).isoformat()}).status_code == 409
    filled = client.patch(path, headers=ctx['headers'], json={'expected_context': matching['context_token'], 'ends_at': ctx['end'].isoformat()})
    assert filled.status_code == 200 and not filled.json()['can_adjust_end']
    assert readiness(client, ctx)['next_best_action']['code'] != 'event_window'
    with SessionLocal() as db:
        assert db.get(OfferVersion, dj['version']['quote_id']).total_rub == dj['version']['total_rub']
        assert db.get(Booking, dj['booking_id']).status == 'DateHeld'
