import json
from datetime import timedelta

from booker_api.models import (
    AuditLog,
    AvailabilitySlot,
    Booking,
    BookingHold,
    Event,
    EventPlan,
    OfferVersion,
    TeamMember,
)
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_matching import setup_matching


def offer_for(client, SessionLocal, ctx, index=0, price=70000, requirement=None):
    headers = ctx['headers']
    req = client.post(f"/events/{ctx['event']['id']}/requests", headers=headers, json={
        'resource_type': 'artist', 'resource_id': ctx['artists'][index]['id'],
        'requirement_id': requirement or ctx['event']['requirements'][0]['id'],
    }).json()
    with SessionLocal() as db:
        slot = db.query(AvailabilitySlot).filter_by(resource_type='artist', resource_id=ctx['artists'][index]['id']).one().id
    result = client.post(f"/requests/{req['id']}/offers", headers=headers, json={'honorarium_rub': price, 'slot_id': slot})
    assert result.status_code == 200, result.text
    return result.json()


def budget(client, ctx):
    result = client.get(f"/events/{ctx['event']['id']}/budget-summary", headers=ctx['headers'])
    assert result.status_code == 200, result.text
    return result.json()


def save_choice(SessionLocal, ctx, index=0, position=0):
    with SessionLocal() as db:
        row = db.get(EventPlan, ctx['event']['id']) or EventPlan(event_id=ctx['event']['id'])
        row.selections_json = json.dumps([{'requirement_id': ctx['event']['requirements'][0]['id'], 'position': position,
            'resource_type': 'artist', 'resource_id': ctx['artists'][index]['id'], 'hall_id': None}])
        db.add(row); db.commit()


def test_budget_without_quotes_keeps_hints_separate(client, SessionLocal):
    ctx = setup_matching(client)
    save_choice(SessionLocal, ctx)
    result = budget(client, ctx)
    assert result['confirmed_total'] == result['active_offers_total'] == 0
    assert result['estimated_remaining'] == result['declared_budget'] == 250000
    assert result['orientation']['min_rub'] == 60000
    assert result['state'] == 'partial'
    assert len(result['uncovered_requirements']) == 3
    assert result['lines'] == []


def test_competing_offers_are_not_added_without_choice(client, SessionLocal):
    ctx = setup_matching(client)
    first = offer_for(client, SessionLocal, ctx, 0, 70000)
    second = offer_for(client, SessionLocal, ctx, 1, 100000)
    result = budget(client, ctx)
    assert result['active_offers_total'] == 0 and len(result['lines']) == 2
    assert all(not l['included'] for l in result['lines'])
    save_choice(SessionLocal, ctx, 1)
    result = budget(client, ctx)
    assert result['active_offers_total'] == second['version']['customer_total_rub'] == 106000
    assert result['estimated_remaining'] == 144000
    assert result['orientation']['min_rub'] is None
    assert next(l for l in result['lines'] if l['booking_id'] == first['booking_id'])['included'] is False
    # Current immutable quote, not a tariff or a frontend multiplier.
    changed = client.post(f"/offers/{second['id']}/versions", headers=ctx['headers'], json={'honorarium_rub': 110000})
    assert changed.status_code == 200
    result = budget(client, ctx)
    assert result['active_offers_total'] == 116600
    assert next(l for l in result['lines'] if l['included'])['quote_id'] == changed.json()['quote_id']
    with SessionLocal() as db:
        assert db.get(OfferVersion, second['version']['quote_id']).customer_total_rub == 106000


def test_all_confirmed_and_live_holds_count_even_beyond_role_quantity(client, SessionLocal):
    ctx = setup_matching(client)
    first = offer_for(client, SessionLocal, ctx, 0, 70000)
    second = offer_for(client, SessionLocal, ctx, 1, 100000)
    with SessionLocal() as db:
        db.get(Booking, first['booking_id']).status = 'Confirmed'; db.commit()
    for side in ['customer', 'supplier']:
        assert client.post(f"/offers/{second['id']}/ack", headers=ctx['headers'], json={'side': side}).status_code == 200
    assert client.post(f"/bookings/{second['booking_id']}/hold", headers=ctx['headers']).status_code == 200
    result = budget(client, ctx)
    assert result['confirmed_total'] == 74200 and result['active_offers_total'] == 106000
    assert len([l for l in result['lines'] if l['included']]) == 2
    assert any('сверх состава' in w for w in result['warnings'])
    with SessionLocal() as db:
        hold = db.query(BookingHold).filter_by(booking_id=second['booking_id']).one()
        hold.expires_at = now() - timedelta(seconds=1); db.commit()
    after = budget(client, ctx)
    assert after['active_offers_total'] == 0 and after['confirmed_total'] == 74200
    assert any('удержания' in w for w in after['warnings'])
    # Read-only calculation must not pretend the expiry worker has run.
    with SessionLocal() as db:
        assert db.get(Booking, second['booking_id']).status == 'DateHeld'


def test_unambiguous_offer_partial_quantity_and_explicit_later_position(client, SessionLocal):
    ctx = setup_matching(client)
    role = ctx['event']['requirements'][0]['id']
    assert client.put(f"/events/{ctx['event']['id']}/requirements", headers=ctx['headers'], json={'items': [{'id': role, 'category_code': 'dj', 'qty': 2}]}).status_code == 200
    first = offer_for(client, SessionLocal, ctx, 0)
    assert budget(client, ctx)['active_offers_total'] == 74200
    second = offer_for(client, SessionLocal, ctx, 1, 100000)
    save_choice(SessionLocal, ctx, 0, position=1)
    result = budget(client, ctx)
    assert result['state'] == 'within_budget'
    assert result['active_offers_total'] == 180200
    assert {l['booking_id']: l['position'] for l in result['lines']} == {first['booking_id']: 1, second['booking_id']: 0}
    assert result['uncovered_requirements'] == []


def test_cancelled_disputed_over_budget_and_zero_budget(client, SessionLocal):
    ctx = setup_matching(client)
    first = offer_for(client, SessionLocal, ctx)
    with SessionLocal() as db:
        db.get(Booking, first['booking_id']).status = 'Dispute'
        db.get(Event, ctx['event']['id']).budget_rub = 0; db.commit()
    result = budget(client, ctx)
    assert result['state'] == 'over_budget' and result['estimated_remaining'] == -74200
    assert result['confirmed_total'] == 74200 and result['warnings']
    with SessionLocal() as db:
        db.get(Booking, first['booking_id']).status = 'Cancelled'; db.commit()
    result = budget(client, ctx)
    assert result['confirmed_total'] == result['active_offers_total'] == 0
    assert result['warnings'] and result['lines'][0]['group'] == 'excluded'
    with SessionLocal() as db:
        db.get(Event, ctx['event']['id']).budget_rub = None; db.commit()
    assert budget(client, ctx)['estimated_remaining'] is None
    assert budget(client, ctx)['state'] == 'no_budget'


def test_budget_object_access_viewer_and_private_audit(client, SessionLocal):
    ctx = setup_matching(client)
    outsider = register(client, 'budget-outsider@booker.test')
    viewer = register(client, 'budget-viewer@booker.test')
    with SessionLocal() as db:
        db.add(TeamMember(organization_id=ctx['customer']['id'], user_id=viewer['user_id'], role='viewer')); db.commit()
    path = f"/events/{ctx['event']['id']}/budget-summary"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth_header(outsider['token'])).status_code == 403
    assert client.get(path, headers=auth_header(viewer['token'])).status_code == 200
    assert client.get('/events/not-an-event/budget-summary', headers=ctx['headers']).status_code == 404
    with SessionLocal() as db:
        logs = db.query(AuditLog).filter_by(action='event.budget_viewed').all()
        assert len(logs) == 1
        assert json.loads(logs[0].payload) == {'state': 'partial'}


def test_historic_snapshot_and_missing_quote_never_use_current_fee(client, SessionLocal):
    from booker_api.models import Offer
    ctx = setup_matching(client)
    offer = offer_for(client, SessionLocal, ctx)
    with SessionLocal() as db:
        historical = OfferVersion(offer_id=offer['id'], honorarium_rub=70000, commission_rate=0.1, commission_rub=7000, total_rub=77000)
        db.add(historical); db.flush()
        db.get(Offer, offer['id']).active_version_id = historical.id
        db.get(Booking, offer['booking_id']).status = 'Confirmed'; db.commit()
    assert budget(client, ctx)['confirmed_total'] == 77000
    with SessionLocal() as db:
        db.get(Offer, offer['id']).active_version_id = None; db.commit()
    result = budget(client, ctx)
    assert result['confirmed_total'] is None and result['estimated_remaining'] is None
    assert result['state'] == 'partial' and result['warnings']


def test_multiple_halls_do_not_multiply_one_venue_tariff(client, SessionLocal):
    ctx = setup_matching(client)
    venue = ctx['venue']
    hall = client.post(f"/venues/{venue['id']}/halls", headers=ctx['headers'], json={'name': 'Второй зал', 'capacity': 100}).json()
    role = ctx['event']['requirements'][1]['id']
    assert client.put(f"/events/{ctx['event']['id']}/requirements", headers=ctx['headers'], json={'items': [{'id': role, 'category_code': 'venue', 'qty': 2}]}).status_code == 200
    with SessionLocal() as db:
        db.add(EventPlan(event_id=ctx['event']['id'], selections_json=json.dumps([
            {'requirement_id': role, 'position': i, 'resource_type': 'venue', 'resource_id': venue['id'], 'hall_id': h}
            for i, h in enumerate([venue['hall_id'], hall['id']])
        ]))); db.commit()
    result = budget(client, ctx)
    assert result['orientation']['selected_count'] == 2
    assert result['orientation']['min_rub'] is None
    assert result['orientation']['priced_count'] == 0


def test_stub_payment_moves_quote_between_buckets_without_double_count(client):
    from tests.test_payments import _awaiting_payment
    ctx = _awaiting_payment(client)
    headers = auth_header(ctx['customer']['token'])
    room = client.get(f"/deal-room/{ctx['booking_id']}", headers=headers).json()
    path = f"/events/{room['event_id']}/budget-summary"
    before = client.get(path, headers=headers).json()
    assert before['active_offers_total'] == room['quote']['total_rub']
    assert before['confirmed_total'] == 0
    assert client.post(f"/payments/{ctx['payment_id']}/stub-complete", headers=headers, json={}).status_code == 200
    after = client.get(path, headers=headers).json()
    assert after['confirmed_total'] == before['active_offers_total']
    assert after['active_offers_total'] == 0
    assert after['estimated_remaining'] == before['estimated_remaining']
