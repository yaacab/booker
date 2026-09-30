from datetime import timedelta

from booker_api.models import (
    AuditLog,
    Booking,
    EventPlan,
    Request,
    SharedShortlist,
    ShortlistFeedback,
    ShortlistGuest,
    TeamMember,
    Venue,
)
from booker_api.security import now
from tests.conftest import activate_venue, auth_header, register
from tests.test_shortlists import _seed

SECRET = 'a' * 64
OTHER = 'b' * 64


def setup(client, *, collaborative=True):
    ctx = _seed(client)
    event = client.post('/events', headers=ctx['cust_h'], json={'organization_id': ctx['cust_org']['id'], 'title': 'PRIVATE EVENT', 'event_date': (now()+timedelta(days=10)).isoformat(), 'budget_rub': 987654}).json()
    body = {'organization_id': ctx['cust_org']['id'], 'event_id': event['id'], 'target_type': 'artist', 'title': 'Обсуждаем артистов', 'favorite_ids': ctx['fav_ids'][:2], 'collaborative': collaborative}
    response = client.post('/shortlists', headers={**ctx['cust_h'], 'Idempotency-Key': 'create-share-once'}, json=body)
    assert response.status_code == 201, response.text
    ctx.update(share=response.json(), body=body, event=event)
    ctx['path'] = f"/shared/{ctx['share']['token']}"
    return ctx


def join(client, ctx, secret=SECRET, name='Анна'):
    response = client.post(ctx['path']+'/guests', json={'display_name': name, 'guest_secret': secret})
    assert response.status_code == 200, response.text
    return response.json()


def feedback(client, ctx, *, secret=SECRET, index=0, reaction='favorite', comment='', revision=0):
    return client.put(ctx['path']+f"/items/{ctx['artists'][index]['id']}/feedback", headers={'X-Shortlist-Guest': secret}, json={'reaction': reaction, 'comment': comment, 'expected_revision': revision})


def test_guest_reactions_comments_edit_and_replays_are_scoped_facts(client, SessionLocal):
    ctx = setup(client)
    assert join(client, ctx)['guest_name'] == 'Анна'
    join(client, ctx)
    first = feedback(client, ctx, comment='Подходит по программе')
    assert first.status_code == 200, first.text
    first_item = first.json()['items'][0]
    assert first_item['counts'] == {'vote': 0, 'favorite': 1, 'reject': 0}
    assert feedback(client, ctx, comment='Подходит по программе').json()['items'][0] == first_item
    join(client, ctx, OTHER, 'Коллега')
    assert feedback(client, ctx, secret=OTHER, reaction='vote').status_code == 200
    changed = feedback(client, ctx, reaction='reject', comment='Нужно проверить технику', revision=1)
    assert changed.status_code == 200
    assert changed.json()['items'][0]['counts'] == {'vote': 1, 'favorite': 0, 'reject': 1}
    assert feedback(client, ctx, reaction='vote', revision=1).status_code == 409
    cleared = feedback(client, ctx, reaction=None, comment='', revision=2)
    assert cleared.status_code == 200
    assert cleared.json()['items'][0]['counts'] == {'vote': 1, 'favorite': 0, 'reject': 0}
    assert len(cleared.json()['items'][0]['feedback']) == 1
    with SessionLocal() as db:
        assert db.query(ShortlistGuest).count() == 2
        assert db.query(ShortlistFeedback).count() == 2
        assert db.query(AuditLog).filter_by(action='shortlist.feedback_updated').count() == 4
        assert db.query(Booking).count() == db.query(Request).count() == db.query(EventPlan).count() == 0
        assert db.query(ShortlistGuest).first().secret_hash != SECRET


def test_guest_secret_cannot_access_account_other_list_or_nonmember_candidate(client):
    ctx = setup(client); join(client, ctx)
    assert feedback(client, ctx, index=2).status_code == 404
    assert feedback(client, ctx, secret=OTHER).status_code == 401
    assert client.get('/events', headers=auth_header(SECRET)).status_code == 401
    other = client.post('/shortlists', headers=ctx['cust_h'], json={**ctx['body'], 'title': 'Другая подборка'}).json()
    wrong = {**ctx, 'path': f"/shared/{other['token']}"}
    assert feedback(client, wrong).status_code == 401
    assert client.get(wrong['path'], headers={'X-Shortlist-Guest': SECRET}).json()['guest_name'] is None
    assert client.post(ctx['path']+'/guests', json={'display_name': 'Не Анна', 'guest_secret': SECRET}).status_code == 409


def test_public_payload_audit_and_cache_do_not_disclose_private_event_or_guest_credentials(client, SessionLocal):
    ctx = setup(client); join(client, ctx)
    assert feedback(client, ctx, comment='Проверим программу').status_code == 200
    response = client.get(ctx['path'])
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['referrer-policy'] == 'no-referrer'
    public = response.json()
    assert public['guest_name'] is None and public['items'][0]['mine']['revision'] == 0
    for value in (ctx['event']['id'], ctx['cust_org']['id'], 'PRIVATE EVENT', '987654', SECRET, 'secret_hash', 'owner_user_id', 'phone', 'email'):
        assert value not in response.text
    with SessionLocal() as db:
        audit = '\n'.join(r.payload for r in db.query(AuditLog).filter(AuditLog.action.like('shortlist.%')).all())
        assert 'Проверим программу' not in audit and 'Анна' not in audit and SECRET not in audit and ctx['share']['token'] not in audit


def test_revoke_and_expiry_close_all_guest_operations_but_owner_keeps_results(client, SessionLocal):
    ctx = setup(client); join(client, ctx); feedback(client, ctx)
    with SessionLocal() as db:
        db.get(SharedShortlist, ctx['share']['id']).expires_at = now()-timedelta(seconds=1); db.commit()
    assert client.get(ctx['path']).status_code == 404
    assert feedback(client, ctx).status_code == 404
    assert client.post(ctx['path']+'/guests', json={'display_name': 'Друг', 'guest_secret': OTHER}).status_code == 404
    with SessionLocal() as db:
        db.get(SharedShortlist, ctx['share']['id']).expires_at = now()+timedelta(days=1); db.commit()
    assert client.post(f"/shortlists/{ctx['share']['id']}/revoke", headers=ctx['cust_h']).status_code == 200
    assert client.post(f"/shortlists/{ctx['share']['id']}/revoke", headers=ctx['cust_h']).status_code == 200
    assert client.get(ctx['path']).status_code == feedback(client, ctx).status_code == 404
    result = client.get('/shortlists', params={'organization_id': ctx['cust_org']['id'], 'event_id': ctx['event']['id']}, headers=ctx['cust_h']).json()
    assert not result['items'][0]['active']
    assert result['items'][0]['items'][0]['counts']['favorite'] == 1
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action='shortlist.revoked').count() == 1


def test_creation_replay_object_auth_and_viewer_cannot_share_or_revoke(client, SessionLocal):
    ctx = setup(client)
    replay = client.post('/shortlists', headers={**ctx['cust_h'], 'Idempotency-Key': 'create-share-once'}, json=ctx['body'])
    assert replay.json()['id'] == ctx['share']['id'] and replay.json()['reused']
    changed = client.post('/shortlists', headers={**ctx['cust_h'], 'Idempotency-Key': 'create-share-once'}, json={**ctx['body'], 'title': 'Изменено'})
    assert changed.status_code == 409
    assert client.get('/shortlists', params={'organization_id': ctx['cust_org']['id']}, headers=ctx['stranger']).status_code == 403
    assert client.post('/shortlists', json=ctx['body'], headers=ctx['stranger']).status_code == 403
    viewer = register(client, 'share-viewer@booker.test')
    with SessionLocal() as db:
        db.add(TeamMember(user_id=viewer['user_id'], organization_id=ctx['cust_org']['id'], role='viewer')); db.commit()
    headers = auth_header(viewer['token'])
    result = client.get('/shortlists', params={'organization_id': ctx['cust_org']['id']}, headers=headers).json()
    assert not result['can_manage'] and 'share_path' not in result['items'][0] and 'token' not in result['items'][0]
    assert client.post('/shortlists', headers=headers, json=ctx['body']).status_code == 403
    assert client.post(f"/shortlists/{ctx['share']['id']}/revoke", headers=headers).status_code == 403
    assert client.post('/shortlists', headers=ctx['cust_h'], json={**ctx['body'], 'event_id': ctx['artists'][0]['id']}).status_code == 404


def test_legacy_read_only_input_bounds_contacts_and_request_rate_limit(client, monkeypatch):
    from booker_api.rate_limit import messaging_limiter
    ctx = setup(client, collaborative=False)
    assert not client.get(ctx['path']).json()['collaborative']
    assert client.post(ctx['path']+'/guests', json={'display_name': 'Анна', 'guest_secret': SECRET}).status_code == 403
    assert feedback(client, ctx).status_code == 403
    live = client.post('/shortlists', headers=ctx['cust_h'], json={**ctx['body'], 'collaborative': True}).json()
    ctx['path'] = f"/shared/{live['token']}"; join(client, ctx)
    assert feedback(client, ctx, comment='Телефон +7 (999) 123-45-67').status_code == 422
    assert feedback(client, ctx, comment='artist@example.org').status_code == 422
    assert feedback(client, ctx, comment='https://external.test').status_code == 422
    assert feedback(client, ctx, comment='я'*1001).status_code == 422
    messaging_limiter.reset(); monkeypatch.setattr(messaging_limiter, 'max_requests', 1)
    assert feedback(client, ctx).status_code == 200
    # Supplying a different forwarding header cannot evade the direct-peer limiter.
    response = client.put(ctx['path']+f"/items/{ctx['artists'][0]['id']}/feedback", headers={'X-Shortlist-Guest': SECRET, 'X-Real-IP': '1.2.3.4'}, json={'reaction': None, 'comment': '', 'expected_revision': 1})
    assert response.status_code == 429


def test_hidden_venue_snapshot_and_feedback_are_not_disclosed(client, SessionLocal):
    ctx = _seed(client)
    org = client.post('/orgs', headers=ctx['cust_h'], json={'name': 'Залы', 'kind': 'venue'}).json()
    venues, favorites = [], []
    for name in ('Зал первый', 'Зал второй'):
        venue = client.post('/venues', headers=ctx['cust_h'], json={'organization_id': org['id'], 'name': name, 'capacity': 100}).json(); venues.append(venue)
        activate_venue(client, venue['id'])
        favorites.append(client.post('/favorites', headers=ctx['cust_h'], json={'organization_id': ctx['cust_org']['id'], 'target_type': 'venue', 'target_id': venue['id']}).json()['id'])
    body = {'organization_id': ctx['cust_org']['id'], 'target_type': 'venue', 'favorite_ids': favorites, 'collaborative': True}
    share = client.post('/shortlists', headers=ctx['cust_h'], json=body).json()
    with SessionLocal() as db:
        db.get(Venue, venues[0]['id']).moderation_status = 'needs_review'; db.commit()
    result = client.get(f"/shared/{share['token']}")
    assert len(result.json()['items']) == 1 and venues[0]['id'] not in result.text and 'Зал первый' not in result.text
    assert client.post('/shortlists', headers=ctx['cust_h'], json=body).status_code == 404


def test_collaboration_flag_stops_mutations_keeps_read_and_revocation(client, monkeypatch):
    from booker_api.config import settings
    ctx = setup(client); join(client, ctx); feedback(client, ctx)
    monkeypatch.setattr(settings, 'collaborative_events', False)
    result = client.get(ctx['path']).json()
    assert not result['collaborative'] and result['items'][0]['counts']['favorite'] == 1
    assert feedback(client, ctx).status_code == 503
    assert client.post(ctx['path']+'/guests', json={'display_name': 'Друг', 'guest_secret': OTHER}).status_code == 503
    assert client.post('/shortlists', headers=ctx['cust_h'], json=ctx['body']).status_code == 503
    assert client.post(f"/shortlists/{ctx['share']['id']}/revoke", headers=ctx['cust_h']).status_code == 200
