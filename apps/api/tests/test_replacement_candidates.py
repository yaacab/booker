from datetime import timedelta

from booker_api.models import AvailabilitySlot, Booking, Event, Offer, Request, TeamMember, Venue
from tests.conftest import activate_venue, auth_header, register
from tests.test_event_budget import offer_for
from tests.test_event_readiness import hold, venue_offer
from tests.test_matching import setup_matching


def setup(client, SessionLocal):
    ctx = setup_matching(client)
    failed = offer_for(client, SessionLocal, ctx, 0)
    assert client.post(f"/bookings/{failed['booking_id']}/cancel", headers=ctx['headers']).status_code == 200
    ctx['failed'] = failed
    ctx['url'] = f"/events/{ctx['event']['id']}/requirements/{ctx['event']['requirements'][0]['id']}/replacement"
    return ctx


def plan(client, ctx, headers=None):
    response = client.get(ctx['url'], headers=headers or ctx['headers'])
    assert response.status_code == 200, response.text
    return response.json()


def command(ctx, candidate, key='replacement-once'):
    return {'resource_type': 'hall' if candidate.get('hall_id') else candidate['resource_type'],
        'resource_id': candidate.get('hall_id') or candidate['resource_id'],
        'requirement_id': ctx['event']['requirements'][0]['id'], 'idempotency_key': key}


def test_full_window_buffers_and_authoritative_cancelled_booking(client, SessionLocal):
    ctx = setup(client, SessionLocal)
    with SessionLocal() as db:
        offer = db.get(Offer, ctx['failed']['id'])
        db.get(Request, offer.request_id).status = 'Confirmed'
        db.commit()
    data = plan(client, ctx)
    assert data['needs_replacement'] and data['filled'] == 0
    assert {c['resource_id'] for c in data['candidates']} == {a['id'] for a in ctx['artists'][1:3]}
    with SessionLocal() as db:
        db.add(AvailabilitySlot(resource_type='artist', resource_id=ctx['artists'][1]['id'], starts_at=ctx['start']-timedelta(minutes=25), ends_at=ctx['start']-timedelta(minutes=10), status='busy'))
        db.query(AvailabilitySlot).filter_by(resource_id=ctx['artists'][2]['id']).one().ends_at = ctx['end']-timedelta(minutes=1)
        db.commit()
    assert plan(client, ctx)['state'] == 'empty'


def test_actual_held_hall_rider_and_unknown_are_distinguished(client, SessionLocal):
    ctx = setup(client, SessionLocal)
    venue = venue_offer(client, SessionLocal, ctx)
    hold(client, ctx, venue)
    assert len(plan(client, ctx)['candidates']) == 2
    path = f"/halls/{ctx['venue']['hall_id']}/technical"
    tech = client.get(path, headers=ctx['headers']).json()
    assert client.put(path, headers=ctx['headers'], json={**tech['data'], 'expected_version': tech['version'], 'equipment': []}).status_code == 200
    assert plan(client, ctx)['candidates'] == []
    tech = client.get(path, headers=ctx['headers']).json()
    assert client.put(path, headers=ctx['headers'], json={**tech['data'], 'expected_version': tech['version'], 'equipment': None}).status_code == 200
    data = plan(client, ctx)
    assert len(data['candidates']) == 2
    assert all(c['warnings'] for c in data['candidates'])


def test_request_rechecks_calendar_replays_without_new_deal_and_rejects_changed_body(client, SessionLocal):
    ctx = setup(client, SessionLocal)
    candidate = plan(client, ctx)['candidates'][0]
    body = command(ctx, candidate)
    with SessionLocal() as db:
        slot = db.query(AvailabilitySlot).filter_by(resource_id=candidate['resource_id']).one()
        slot.status = 'busy'; db.commit()
    assert client.post(ctx['url']+'-requests', headers=ctx['headers'], json=body).status_code == 409
    with SessionLocal() as db:
        db.query(AvailabilitySlot).filter_by(resource_id=candidate['resource_id']).one().status = 'open'; db.commit()
    first = client.post(ctx['url']+'-requests', headers=ctx['headers'], json=body)
    assert first.status_code == 200, first.text
    replay = client.post(ctx['url']+'-requests', headers=ctx['headers'], json=body).json()
    assert replay['id'] == first.json()['id'] and replay['reused']
    assert candidate['resource_id'] not in {c['resource_id'] for c in plan(client, ctx)['candidates']}
    assert client.post(ctx['url']+'-requests', headers=ctx['headers'], json={**body, 'resource_id': ctx['artists'][0]['id']}).status_code == 409
    assert client.post(ctx['url']+'-requests', headers=ctx['headers'], json={**body, 'idempotency_key': 'different'}).status_code == 409
    with SessionLocal() as db:
        assert db.query(Request).filter_by(event_id=ctx['event']['id']).count() == 2
        assert db.query(Booking).count() == db.query(Offer).count() == 1
        assert db.query(AvailabilitySlot).filter_by(resource_id=candidate['resource_id']).one().status == 'open'


def test_auth_window_and_closed_event(client, SessionLocal):
    ctx = setup(client, SessionLocal)
    candidate = plan(client, ctx)['candidates'][0]
    outsider = register(client, 'replacement-outsider@booker.test')
    outsider_headers = auth_header(outsider['token'])
    assert client.get(ctx['url'], headers=outsider_headers).status_code == 403
    assert client.post(ctx['url']+'-requests', headers=outsider_headers, json=command(ctx, candidate)).status_code == 403
    with SessionLocal() as db:
        db.add(TeamMember(organization_id=ctx['customer']['id'], user_id=outsider['user_id'], role='viewer'))
        db.commit()
    assert not plan(client, ctx, outsider_headers)['can_manage']
    assert client.post(ctx['url']+'-requests', headers=outsider_headers, json=command(ctx, candidate)).status_code == 403
    with SessionLocal() as db:
        event = db.get(Event, ctx['event']['id']); event.ends_at = None
        event.event_date = ctx['start'].replace(hour=22); db.commit()
    data = plan(client, ctx)
    assert data['state'] == 'needs_window' and data['candidates'] == []
    assert data['search']['date'] == (ctx['start']+timedelta(days=1)).date().isoformat()
    with SessionLocal() as db:
        db.get(Event, ctx['event']['id']).status = 'Completed'; db.commit()
    assert plan(client, ctx)['state'] == 'closed'
    assert client.post(ctx['url']+'-requests', headers=ctx['headers'], json=command(ctx, candidate)).status_code == 409


def test_venue_replacement_uses_hall_calendar_and_actual_artist_rider(client, SessionLocal):
    ctx = setup_matching(client)
    artist_offer = offer_for(client, SessionLocal, ctx, 1)
    hold(client, ctx, artist_offer)
    failed = venue_offer(client, SessionLocal, ctx)
    assert client.post(f"/bookings/{failed['booking_id']}/cancel", headers=ctx['headers']).status_code == 200
    requirement_id = ctx['event']['requirements'][1]['id']
    ctx['url'] = f"/events/{ctx['event']['id']}/requirements/{requirement_id}/replacement"
    with SessionLocal() as db:
        org_id = db.get(Venue, ctx['venue']['id']).organization_id
    venues = []
    for name, capacity, equipment in [('Подходящий зал', 150, ['CDJ']), ('Нет оборудования', 150, []), ('Маленький зал', 30, ['CDJ']), ('Неизвестное оборудование', 150, None)]:
        venue = client.post('/venues', headers=ctx['headers'], json={'organization_id': org_id, 'name': name, 'capacity': capacity}).json()
        venues.append(venue)
        assert client.post('/slots', headers=ctx['headers'], json={'resource_type': 'hall', 'resource_id': venue['hall_id'], 'starts_at': (ctx['start']-timedelta(hours=1)).isoformat(), 'ends_at': (ctx['end']+timedelta(hours=1)).isoformat()}).status_code == 200
        assert client.put(f"/halls/{venue['hall_id']}/technical", headers=ctx['headers'], json={'expected_version': 0, 'capacity': capacity, 'stage_area_m2': 20, 'power_kw': 5, 'basic_sound': True, 'microphones': 3, 'equipment': equipment, 'restrictions': ''}).status_code == 200
        activate_venue(client, venue['id'])
    data = plan(client, ctx)
    assert data['cancelled_requests'][0]['resource_name'].startswith('Зал ·')
    assert {i['resource_id'] for i in data['candidates']} == {venues[0]['id'], venues[3]['id']}
    with SessionLocal() as db:
        db.get(Venue, venues[3]['id']).availability_mode = 'synthetic'
        db.get(Event, ctx['event']['id']).status = 'InProgress'
        db.commit()
    data = plan(client, ctx)
    assert len(data['candidates']) == 1
    target = data['candidates'][0]
    body = {**command(ctx, target), 'requirement_id': requirement_id}
    result = client.post(ctx['url']+'-requests', headers=ctx['headers'], json=body)
    assert result.status_code == 200, result.text
    with SessionLocal() as db:
        assert db.get(Event, ctx['event']['id']).status == 'InProgress'
        req = db.get(Request, result.json()['id'])
        assert req.resource_type == 'hall' and req.resource_id == venues[0]['hall_id']
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.resource_id == venues[0]['hall_id'],
                AvailabilitySlot.starts_at <= ctx['start'],
                AvailabilitySlot.ends_at >= ctx['end'],
            )
            .one()
            .id
        )
    offered = client.post(f"/requests/{result.json()['id']}/offers", headers=ctx['headers'], json={'slot_id': slot, 'honorarium_rub': 100000})
    assert offered.status_code == 200, offered.text
    with SessionLocal() as db:
        assert db.get(Event, ctx['event']['id']).status == 'InProgress'
