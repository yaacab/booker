from datetime import timedelta

from booker_api.models import ArtistTariff, AvailabilitySlot, Event
from booker_api.security import aware
from tests.test_matching import setup_matching


def test_request_suggestions_use_actual_tariff_and_complete_window(client, SessionLocal):
    ctx = setup_matching(client)
    resource = ctx['artists'][0]['id']
    req = client.post(f"/events/{ctx['event']['id']}/requests", headers=ctx['headers'], json={'resource_type': 'artist', 'resource_id': resource}).json()

    def item():
        response = client.get('/requests', headers=ctx['headers'])
        assert response.status_code == 200
        return next(r for r in response.json()['items'] if r['id'] == req['id'])

    with SessionLocal() as db:
        event = db.get(Event, ctx['event']['id'])
        good = db.query(AvailabilitySlot).filter_by(resource_id=resource).one()
        good_id = good.id
        db.add(AvailabilitySlot(resource_type='artist', resource_id=resource, starts_at=aware(event.event_date)-timedelta(days=5), ends_at=aware(event.event_date)-timedelta(days=4), status='open'))
        db.commit()
    assert item()['slot_id'] == good_id
    assert item()['honorarium_rub'] == 60000
    with SessionLocal() as db:
        db.query(ArtistTariff).filter_by(artist_id=resource).delete()
        event = db.get(Event, ctx['event']['id'])
        db.get(AvailabilitySlot, good_id).ends_at = aware(event.ends_at)-timedelta(minutes=1)
        db.commit()
    assert item()['honorarium_rub'] is None
    assert item()['slot_id'] is None
    with SessionLocal() as db:
        event = db.get(Event, ctx['event']['id'])
        db.get(AvailabilitySlot, good_id).ends_at = event.ends_at
        busy = AvailabilitySlot(resource_type='artist', resource_id=resource, starts_at=event.event_date, ends_at=event.ends_at, status='busy')
        db.add(busy); db.commit()
    assert item()['slot_id'] is None
    with SessionLocal() as db:
        db.query(AvailabilitySlot).filter_by(resource_id=resource, status='busy').delete()
        db.get(Event, ctx['event']['id']).ends_at = None
        db.commit()
    assert item()['slot_id'] is None


def test_request_suggestions_respect_declared_setup_and_teardown(client, SessionLocal):
    ctx = setup_matching(client)
    resource = ctx['artists'][1]['id']
    req = client.post(f"/events/{ctx['event']['id']}/requests", headers=ctx['headers'], json={'resource_type': 'artist', 'resource_id': resource}).json()
    with SessionLocal() as db:
        event = db.get(Event, ctx['event']['id'])
        slot = db.query(AvailabilitySlot).filter_by(resource_id=resource).one()
        slot.starts_at = event.event_date; slot.ends_at = event.ends_at
        slot.buffer_before_min = 0; slot.buffer_after_min = 0
        db.commit()
    rows = client.get('/requests', headers=ctx['headers']).json()['items']
    assert next(r for r in rows if r['id'] == req['id'])['slot_id'] is None


def test_quick_request_preserves_selected_slot_window(client, SessionLocal):
    ctx = setup_matching(client)
    resource = ctx['artists'][0]['id']
    with SessionLocal() as db:
        slot = db.query(AvailabilitySlot).filter_by(resource_id=resource).one()
        slot_id, start, end = slot.id, aware(slot.starts_at), aware(slot.ends_at)
    response = client.post('/quick-request', headers=ctx['headers'], json={'artist_id': resource, 'slot_id': slot_id})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        from booker_api.models import Request
        req = db.get(Request, response.json()['request_id'])
        event = db.get(Event, req.event_id)
        assert aware(event.event_date) == start and aware(event.ends_at) == end
    items = client.get('/requests', headers=ctx['headers']).json()['items']
    assert next(r for r in items if r['id'] == req.id)['slot_id'] == slot_id
