from datetime import timedelta

from booker_api.models import (
    AvailabilitySlot,
    Booking,
    Event,
    EventPlan,
    EventRepeatPreference,
    EventTeamRequirement,
    Request,
    TeamMember,
)
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_event_budget import offer_for, save_choice
from tests.test_event_readiness import venue_offer
from tests.test_matching import setup_matching


def source(client, SessionLocal, pending=False):
    ctx = setup_matching(client)
    offers = [offer_for(client, SessionLocal, ctx, 1), venue_offer(client, SessionLocal, ctx)]
    if pending:
        ctx['pending'] = client.post(f"/events/{ctx['event']['id']}/requests", headers=ctx['headers'], json={'resource_type': 'artist', 'resource_id': ctx['artists'][2]['id'], 'requirement_id': ctx['event']['requirements'][0]['id']}).json()
    save_choice(SessionLocal, ctx, 1)
    with SessionLocal() as db:
        event = db.get(Event, ctx['event']['id']); event.status = 'Completed'; event.event_type = 'Корпоратив'; event.notes = 'Private old notes'
        for offer in offers:
            db.get(Booking, offer['booking_id']).status = 'Completed'
        for role in db.query(EventTeamRequirement).filter_by(event_id=event.id):
            role.status = 'closed'; role.notes = 'Old agreement'
        db.commit()
    ctx['url'] = f"/events/{ctx['event']['id']}/repeat"
    return ctx


def payload(ctx, participants=()):
    return {'title': 'Новый корпоратив', 'event_date': (ctx['start']+timedelta(days=10)).isoformat(), 'ends_at': (ctx['end']+timedelta(days=10)).isoformat(), 'preferred_request_ids': list(participants)}


def repeat(client, ctx, body):
    return client.post(ctx['url'], headers={**ctx['headers'], 'Idempotency-Key': 'repeat-once'}, json=body)


def test_clean_draft_preserves_source_and_checks_new_calendar(client, SessionLocal):
    ctx = source(client, SessionLocal)
    options = client.get(ctx['url']+'-options', headers=ctx['headers']).json()
    assert len(options['participants']) == 2
    result = repeat(client, ctx, payload(ctx, [p['source_request_id'] for p in options['participants']]))
    assert result.status_code == 201, result.text
    new_id = result.json()['id']
    details = client.get(f'/events/{new_id}', headers=ctx['headers']).json()
    assert details['status'] == 'Draft' and details['requests'] == [] and details['budget_rub'] is None
    assert details['event_type'] == 'Корпоратив' and details['guest_count'] == 100 and details['city'] == 'Москва'
    with SessionLocal() as db:
        assert db.get(Event, new_id).notes == ''
        original = db.get(Event, ctx['event']['id'])
        assert original.status == 'Completed' and original.notes == 'Private old notes'
        old_roles = db.query(EventTeamRequirement).filter_by(event_id=original.id).all()
        roles = db.query(EventTeamRequirement).filter_by(event_id=new_id).all()
        assert {(r.category_code, r.qty, r.required) for r in roles} == {(r.category_code, r.qty, r.required) for r in old_roles}
        assert all(r.status == 'open' and r.notes == '' and r.id not in {o.id for o in old_roles} for r in roles)
        assert db.query(EventRepeatPreference).filter_by(event_id=new_id).count() == 2
        assert db.get(EventPlan, new_id) is None
        assert db.query(Request).filter_by(event_id=new_id).count() == db.query(Booking).filter_by(event_id=new_id).count() == 0
        assert db.query(Booking).count() == 2
    prefs = client.get(f'/events/{new_id}/repeat-preferences', headers=ctx['headers']).json()
    assert all(not p['can_add'] and p['problems'] for p in prefs['items'])
    assert prefs['saved_selections'] == []
    with SessionLocal() as db:
        for pref in db.query(EventRepeatPreference).filter_by(event_id=new_id):
            db.add(AvailabilitySlot(resource_type='artist' if pref.resource_type == 'artist' else 'hall', resource_id=pref.resource_id if pref.resource_type == 'artist' else pref.hall_id, starts_at=ctx['start']+timedelta(days=10,hours=-1), ends_at=ctx['end']+timedelta(days=10,hours=1), status='open'))
        db.commit()
    prefs = client.get(f'/events/{new_id}/repeat-preferences', headers=ctx['headers']).json()
    assert all(p['can_add'] for p in prefs['items'])
    assert client.put(f'/events/{new_id}/plan', headers=ctx['headers'], json={'expected_revision': prefs['revision'], 'expected_context': prefs['context_token'], 'selections': [p['selection'] for p in prefs['items']]}).status_code == 200
    assert client.get(f'/events/{new_id}', headers=ctx['headers']).json()['requests'] == []


def test_no_preferences_replay_and_body_conflict(client, SessionLocal):
    ctx = source(client, SessionLocal); body = payload(ctx)
    first = repeat(client, ctx, body); second = repeat(client, ctx, body)
    assert first.status_code == second.status_code == 201
    assert first.json()['id'] == second.json()['id'] and second.json()['reused']
    assert repeat(client, ctx, {**body, 'title': 'Изменено'}).status_code == 409
    assert client.get(f"/events/{first.json()['id']}/repeat-preferences", headers=ctx['headers']).json()['items'] == []
    with SessionLocal() as db:
        assert db.query(Event).count() == 2 and db.query(EventRepeatPreference).count() == 0


def test_completed_future_dates_and_writer_required(client, SessionLocal):
    ctx = setup_matching(client); ctx['url'] = f"/events/{ctx['event']['id']}/repeat"
    assert repeat(client, ctx, payload(ctx)).status_code == 409
    with SessionLocal() as db:
        db.get(Event, ctx['event']['id']).status = 'Completed'; db.commit()
    assert repeat(client, ctx, {**payload(ctx), 'event_date': (now()-timedelta(days=1)).isoformat()}).status_code == 422
    assert repeat(client, ctx, {**payload(ctx), 'ends_at': ctx['start'].isoformat()}).status_code == 422
    assert repeat(client, ctx, {**payload(ctx), 'quote_id': 'old'}).status_code == 422
    outsider = register(client, 'repeat-outsider@booker.test'); viewer = register(client, 'repeat-viewer@booker.test')
    with SessionLocal() as db:
        db.add(TeamMember(organization_id=ctx['customer']['id'], user_id=viewer['user_id'], role='viewer')); db.commit()
    for path in (ctx['url']+'-options', f"/events/{ctx['event']['id']}/repeat-preferences"):
        assert client.get(path, headers=auth_header(outsider['token'])).status_code == 403
    for actor in (outsider, viewer):
        assert client.post(ctx['url'], json=payload(ctx), headers={**auth_header(actor['token']), 'Idempotency-Key': 'repeat-once'}).status_code == 403
    assert not client.get(ctx['url']+'-options', headers=auth_header(viewer['token'])).json()['can_manage']


def test_only_completed_participants_and_flag_and_current_membership(client, SessionLocal, monkeypatch):
    from booker_api.config import settings
    ctx = source(client, SessionLocal, pending=True)
    pending = ctx['pending']
    options = client.get(ctx['url']+'-options', headers=ctx['headers']).json()
    assert len(options['participants']) == 2
    assert repeat(client, ctx, payload(ctx, [pending['id']])).status_code == 409
    ids = [p['source_request_id'] for p in options['participants']]
    assert repeat(client, ctx, payload(ctx, [ids[0], ids[0]])).status_code == 409
    assert repeat(client, ctx, payload(ctx)).status_code == 201
    monkeypatch.setattr(settings, 'repeat_events', False)
    assert repeat(client, ctx, payload(ctx)).status_code == 503
    monkeypatch.setattr(settings, 'repeat_events', True)
    with SessionLocal() as db:
        db.query(TeamMember).filter_by(organization_id=ctx['customer']['id']).delete(); db.commit()
    assert repeat(client, ctx, payload(ctx)).status_code == 403


def test_repeat_migration_is_reversible_and_preserves_existing_schema(tmp_path):
    from pathlib import Path

    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from alembic import command

    url = f"sqlite:///{tmp_path / 'repeat.db'}"
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'head')
    engine = create_engine(url)
    assert 'event_repeat_preferences' in inspect(engine).get_table_names()
    assert any(f['referred_table'] == 'event_team_requirements' and f['options'].get('ondelete') == 'SET NULL' for f in inspect(engine).get_foreign_keys('event_repeat_preferences'))
    command.downgrade(config, 'f7a8b9c0d1e2')
    assert 'event_repeat_preferences' not in inspect(engine).get_table_names()
    assert 'shortlist_guests' in inspect(engine).get_table_names()
    command.upgrade(config, 'head')
    assert 'event_repeat_preferences' in inspect(engine).get_table_names()
    engine.dispose()



def test_completed_event_cannot_be_reopened_by_new_requests_or_offers(client, SessionLocal):
    ctx = source(client, SessionLocal, pending=True)
    with SessionLocal() as db:
        slot = db.query(AvailabilitySlot).filter_by(resource_id=ctx['artists'][2]['id']).one().id
    request_body = {'resource_type': 'artist', 'resource_id': ctx['artists'][2]['id']}
    assert client.post(f"/events/{ctx['event']['id']}/requests", headers=ctx['headers'], json=request_body).status_code == 409
    assert client.post('/quick-request', headers=ctx['headers'], json={'event_id': ctx['event']['id'], 'artist_id': ctx['artists'][2]['id'], 'slot_id': slot}).status_code == 409
    assert client.post(f"/requests/{ctx['pending']['id']}/offers", headers=ctx['headers'], json={'slot_id': slot, 'honorarium_rub': 100000}).status_code == 409
    with SessionLocal() as db:
        assert db.get(Event, ctx['event']['id']).status == 'Completed'
        assert db.query(Request).count() == 3 and db.query(Booking).count() == 2
