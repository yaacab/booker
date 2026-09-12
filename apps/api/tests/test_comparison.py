from datetime import timedelta

from booker_api.models import (
    AvailabilitySlot,
    Booking,
    EventPlan,
    Request,
    Subscription,
    TeamMember,
    Venue,
)
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_event_readiness import hold, venue_offer
from tests.test_matching import setup_matching


def path(ctx, kind='artist', ids=None):
    ids = ids or [a['id'] for a in ctx['artists'][:3]]
    return f"/compare?target_type={kind}&ids={','.join(ids)}"


def test_comparison_uses_real_prices_facts_and_preserves_order_after_upgrade(client, SessionLocal):
    ctx = setup_matching(client)
    response = client.get(path(ctx))
    assert response.status_code == 200, response.text
    data = response.json()
    assert [c['id'] for c in data['columns']] == [a['id'] for a in ctx['artists'][:3]]
    assert [c['prices']['min_rub'] for c in data['columns']] == [60000, 90000, 120000]
    assert all(c['availability']['status'] == 'unknown' and c['facts']['deals'] == 0 for c in data['columns'])
    assert data['columns'][0]['format'] is None
    assert data['columns'][2]['format'] == 'Корпоратив'
    assert data['columns'][1]['technical']['required_equipment'] == ['CDJ']
    assert all(c['reviews']['average_rating'] is None for c in data['columns'])
    with SessionLocal() as db:
        db.add(Subscription(organization_id=ctx['supply']['id'], plan_code='artist_premium', billing_period='monthly', status='active', starts_at=now(), current_period_end=now()+timedelta(days=30))); db.commit()
    assert client.get(path(ctx)).json() == data


def test_full_window_buffers_and_pair_compatibility_are_separate_from_hints(client, SessionLocal):
    ctx = setup_matching(client)
    query = path(ctx) + f"&starts_at={ctx['start'].isoformat().replace('+00:00', 'Z')}&ends_at={ctx['end'].isoformat().replace('+00:00', 'Z')}&guest_count=100&venue_id={ctx['venue']['id']}&hall_id={ctx['venue']['hall_id']}"
    result = client.get(query).json()
    assert all(c['availability']['status'] == 'open' for c in result['columns'])
    assert not result['columns'][0]['buffers_known']
    assert result['columns'][1]['compatibility']['status'] == 'compatible'
    with SessionLocal() as db:
        db.add(AvailabilitySlot(resource_type='artist', resource_id=ctx['artists'][1]['id'], starts_at=ctx['start']-timedelta(minutes=25), ends_at=ctx['start']-timedelta(minutes=5), status='busy')); db.commit()
    result = client.get(query).json()
    assert result['columns'][1]['availability']['status'] == 'unavailable'
    assert result['columns'][1]['compatibility']['status'] == 'incompatible'
    assert result['columns'][1]['prices']['min_rub'] == 90000


def test_venue_visibility_synthetic_calendars_and_per_hall_facts(client, SessionLocal):
    ctx = setup_matching(client)
    second = client.post('/orgs', headers=ctx['headers'], json={'name': 'Вторая площадка', 'kind': 'venue', 'confirm_another_workspace': True}).json()
    venue = client.post('/venues', headers=ctx['headers'], json={'organization_id': second['id'], 'name': 'Второй зал', 'capacity': 70}).json()
    query = path(ctx, 'venue', [ctx['venue']['id'], venue['id']]) + f"&event_id={ctx['event']['id']}&artist_id={ctx['artists'][1]['id']}"
    result = client.get(query, headers=ctx['headers']).json()
    assert result['columns'][0]['availability']['status'] == 'open'
    assert result['columns'][0]['halls'][0]['technical']['equipment'] == ['CDJ']
    assert result['columns'][1]['halls'][0]['capacity_status'] == 'too_small'
    with SessionLocal() as db:
        row = db.get(Venue, venue['id']); row.availability_mode = 'synthetic'; row.is_claimed = False; db.commit()
    assert client.get(query, headers=ctx['headers']).json()['columns'][1]['availability']['status'] == 'unknown'
    with SessionLocal() as db:
        db.get(Venue, venue['id']).moderation_status = 'needs_review'; db.commit()
    denied = client.get(query, headers=ctx['headers'])
    assert denied.status_code == 404 and 'Второй зал' not in denied.text


def test_event_auth_window_authority_and_own_hold_context(client, SessionLocal):
    from tests.test_event_budget import offer_for
    ctx = setup_matching(client)
    offer = offer_for(client, SessionLocal, ctx, 1)
    hold(client, ctx, offer)
    query = path(ctx) + f"&event_id={ctx['event']['id']}"
    assert client.get(query).status_code == 401
    outsider = register(client, 'compare-outsider@booker.test')
    assert client.get(query, headers=auth_header(outsider['token'])).status_code == 403
    viewer = register(client, 'compare-viewer@booker.test')
    with SessionLocal() as db:
        db.add(TeamMember(organization_id=ctx['customer']['id'], user_id=viewer['user_id'], role='viewer')); db.commit()
    result = client.get(query + '&starts_at=2000-01-01T00:00:00Z&ends_at=2000-01-02T00:00:00Z', headers=auth_header(viewer['token'])).json()
    assert result['columns'][1]['availability']['status'] == 'open'
    assert result['guest_count'] == 100 and result['starts_at'].startswith(ctx['start'].date().isoformat())
    public = client.get(path(ctx) + f"&starts_at={ctx['start'].isoformat().replace('+00:00','Z')}&ends_at={ctx['end'].isoformat().replace('+00:00','Z')}").json()
    assert public['columns'][1]['availability']['status'] == 'unavailable'


def test_hall_deals_count_as_facts_of_their_venue(client, SessionLocal):
    ctx = setup_matching(client)
    offer = venue_offer(client, SessionLocal, ctx)
    other_org = client.post('/orgs', headers=ctx['headers'], json={'name': 'Другая', 'kind': 'venue', 'confirm_another_workspace': True}).json()
    other = client.post('/venues', headers=ctx['headers'], json={'organization_id': other_org['id'], 'name': 'Другая', 'capacity': 100}).json()
    with SessionLocal() as db:
        db.get(Booking, offer['booking_id']).status = 'Completed'; db.commit()
    result = client.get(path(ctx, 'venue', [ctx['venue']['id'], other['id']])).json()
    assert result['columns'][0]['facts']['deals'] == 1
    assert result['columns'][0]['facts']['response_metrics']['sample_size'] == 1
    assert result['columns'][1]['facts']['deals'] == 0


def test_compare_input_validation_and_no_automatic_domain_commands(client, SessionLocal):
    ctx = setup_matching(client)
    assert client.get('/compare?target_type=artist&ids=bad,bad2').status_code == 422
    assert client.get(path(ctx, ids=[ctx['artists'][0]['id']]*2)).status_code == 422
    assert client.get(path(ctx) + '&starts_at=2026-01-01T00:00:00Z').status_code == 422
    assert client.get(path(ctx) + f"&hall_id={ctx['venue']['hall_id']}").status_code == 422
    assert client.get(path(ctx)).status_code == 200
    with SessionLocal() as db:
        assert db.query(Booking).count() == db.query(Request).count() == db.query(EventPlan).count() == 0


def test_compare_reviews_require_completed_profile_and_threshold_without_author_data(client, SessionLocal):
    from booker_api.models import Review
    from tests.test_event_budget import offer_for

    ctx = setup_matching(client)
    ids = []
    for index in range(6):
        offer = offer_for(client, SessionLocal, ctx, 1)
        ids.append(offer['booking_id'])
        with SessionLocal() as db:
            db.get(Booking, offer['booking_id']).status = 'Completed' if index < 4 else 'Negotiation'
            db.add(Review(booking_id=offer['booking_id'], author_user_id=ctx['owner']['user_id'], org_id=ctx['supply']['id'], rating=4, text='PRIVATE_REVIEW_BODY'))
            db.commit()
    first = client.get(path(ctx)).json()['columns']
    assert first[1]['reviews']['count'] == 4
    assert first[1]['reviews']['average_rating'] is None
    assert first[0]['reviews']['count'] == first[2]['reviews']['count'] == 0
    with SessionLocal() as db:
        db.get(Booking, ids[4]).status = 'Completed'; db.commit()
    response = client.get(path(ctx))
    assert response.json()['columns'][1]['reviews']['average_rating'] == 4
    assert response.json()['columns'][1]['reviews']['count'] == 5
    assert 'PRIVATE_REVIEW_BODY' not in response.text and ctx['owner']['user_id'] not in response.text
