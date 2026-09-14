import json
from datetime import timedelta

from booker_api.models import (
    AuditLog,
    BusinessEventNote,
    BusinessEventTemplate,
    Event,
    EventPlan,
    EventTeamRequirement,
    Request,
    Subscription,
    TeamMember,
)
from booker_api.security import now
from tests.conftest import auth_header, register
from tests.test_event_budget import offer_for
from tests.test_matching import setup_matching


def setup(client, SessionLocal):
    ctx = setup_matching(client)
    offer_for(client, SessionLocal, ctx, 1)
    with SessionLocal() as db:
        db.add(Subscription(organization_id=ctx['customer']['id'], plan_code='customer_business', billing_period='monthly', status='active', starts_at=now()-timedelta(days=1), current_period_end=now()+timedelta(days=30)))
        db.get(Event, ctx['event']['id']).notes = 'PRIVATE source notes'
        db.add(EventPlan(event_id=ctx['event']['id'], selections_json='[]'))
        db.commit()
    ctx['base'] = f"/business/organizations/{ctx['customer']['id']}/templates"
    return ctx


def post(client, ctx, path, data, key='business-command'):
    return client.post(path, headers={**ctx['headers'], 'Idempotency-Key': key}, json=data)


def draft_body(ctx):
    return {'title': 'Новый вечер', 'event_date': (ctx['start']+timedelta(days=10)).isoformat(), 'ends_at': (ctx['end']+timedelta(days=10)).isoformat()}


def test_immutable_template_and_clean_draft_idempotency(client, SessionLocal):
    ctx = setup(client, SessionLocal)
    payload = {'source_event_id': ctx['event']['id'], 'name': 'Корпоративный вечер'}
    result = post(client, ctx, ctx['base'], payload)
    assert result.status_code == 201, result.text
    template_id = result.json()['id']
    assert post(client, ctx, ctx['base'], payload).json()['id'] == template_id
    assert post(client, ctx, ctx['base'], {**payload, 'name': 'Changed'}).status_code == 409
    with SessionLocal() as db:
        event = db.get(Event, ctx['event']['id']); event.city = 'Казань'; event.budget_rub = 999
        role = db.query(EventTeamRequirement).filter_by(event_id=event.id).first(); role.notes = 'PRIVATE terms'; role.status = 'closed'
        db.commit()
    templates = client.get(ctx['base'], headers=ctx['headers']).json()
    assert templates['items'][0]['brief']['city'] == 'Москва'
    assert templates['items'][0]['brief']['budget_rub'] == 250000
    assert 'PRIVATE' not in json.dumps(templates)
    url = f'/business/templates/{template_id}/events'
    body = draft_body(ctx)
    made = post(client, ctx, url, body)
    assert made.status_code == 201, made.text
    event_id = made.json()['id']
    assert post(client, ctx, url, body).json()['id'] == event_id
    with SessionLocal() as db:
        draft = db.get(Event, event_id)
        assert draft.status == 'Draft' and draft.city == 'Москва' and draft.budget_rub == 250000 and draft.notes == ''
        assert db.get(EventPlan, event_id) is None
        assert db.query(Request).filter_by(event_id=event_id).count() == 0
        roles = db.query(EventTeamRequirement).filter_by(event_id=event_id).all()
        assert len(roles) == 3 and all(r.status == 'open' and r.notes == '' for r in roles)
        assert not {r.id for r in roles}.intersection(r['id'] for r in ctx['event']['requirements'])
        assert db.query(AuditLog).filter_by(action='business.draft_created').count() == 1


def test_clone_uses_current_brief_and_rejects_invalid_dates(client, SessionLocal):
    ctx = setup(client, SessionLocal)
    url = f"/business/events/{ctx['event']['id']}/clone"
    body = draft_body(ctx)
    assert post(client, ctx, url, {**body, 'event_date': '2000-01-01T00:00:00Z'}).status_code == 422
    assert post(client, ctx, url, {**body, 'event_date': body['event_date'][:19]}).status_code == 422
    assert post(client, ctx, url, {**body, 'ends_at': body['event_date']}).status_code == 422
    made = post(client, ctx, url, body)
    assert made.status_code == 201, made.text
    details = client.get(f"/events/{made.json()['id']}", headers=ctx['headers']).json()
    assert details['status'] == 'Draft' and details['requests'] == [] and details['budget_rub'] == 250000
    assert len(details['requirements']) == 3


def test_expiry_and_flag_keep_data_readable_but_gate_new_work(client, SessionLocal, monkeypatch):
    from booker_api.config import settings
    ctx = setup(client, SessionLocal)
    template_id = post(client, ctx, ctx['base'], {'name': 'Шаблон', 'source_event_id': ctx['event']['id']}).json()['id']
    note_url = f"/business/events/{ctx['event']['id']}/notes"
    note = post(client, ctx, note_url, {'body': 'Внутренняя заметка'}).json()
    with SessionLocal() as db:
        db.query(Subscription).filter_by(organization_id=ctx['customer']['id']).one().current_period_end = now()-timedelta(seconds=1); db.commit()
    assert not client.get(ctx['base'], headers=ctx['headers']).json()['can_create']
    notes = client.get(note_url, headers=ctx['headers']).json()
    assert notes['items'][0]['body'] == 'Внутренняя заметка' and not notes['can_write']
    assert post(client, ctx, f'/business/templates/{template_id}/events', draft_body(ctx)).status_code == 403
    assert post(client, ctx, note_url, {'body': 'New'}, 'new-note-key').status_code == 403
    assert client.delete(f"/business/notes/{note['id']}?expected_revision=1", headers=ctx['headers']).status_code == 200
    with SessionLocal() as db:
        db.query(Subscription).filter_by(organization_id=ctx['customer']['id']).one().current_period_end = now()+timedelta(days=1); db.commit()
    monkeypatch.setattr(settings, 'customer_business', False)
    assert post(client, ctx, f'/business/templates/{template_id}/events', draft_body(ctx)).status_code == 403
    assert client.post(f'/business/templates/{template_id}/archive', headers=ctx['headers']).status_code == 200
    assert client.post(f'/business/templates/{template_id}/archive', headers=ctx['headers']).status_code == 200
    assert client.get(ctx['base'], headers=ctx['headers']).json()['items'] == []


def test_notes_revision_retry_delete_no_body_in_audit(client, SessionLocal):
    ctx = setup(client, SessionLocal)
    url = f"/business/events/{ctx['event']['id']}/notes"
    body = {'body': 'PRIVATE internal note'}
    made = post(client, ctx, url, body)
    assert made.status_code == 201, made.text
    note_id = made.json()['id']
    assert post(client, ctx, url, body).json()['id'] == note_id
    patch = {'body': 'PRIVATE changed', 'expected_revision': 1}
    note_url = f'/business/notes/{note_id}'
    assert client.put(note_url, headers=ctx['headers'], json=patch).json()['revision'] == 2
    assert client.put(note_url, headers=ctx['headers'], json=patch).json()['reused']
    assert client.put(note_url, headers=ctx['headers'], json={**patch, 'body': 'Stale'}).status_code == 409
    assert client.delete(note_url+'?expected_revision=1', headers=ctx['headers']).status_code == 409
    assert client.delete(note_url+'?expected_revision=2', headers=ctx['headers']).status_code == 200
    assert client.delete(note_url+'?expected_revision=2', headers=ctx['headers']).status_code == 200
    assert client.put(note_url, headers=ctx['headers'], json={'body': 'Resurrect', 'expected_revision': 3}).status_code == 409
    assert client.get(url, headers=ctx['headers']).json()['items'] == []
    with SessionLocal() as db:
        assert db.get(BusinessEventNote, note_id).body == ''
        logs = db.query(AuditLog).filter(AuditLog.action.like('business.note%')).all()
        assert len(logs) == 3 and all('PRIVATE' not in (log.payload or '') for log in logs)


def test_object_authorization_viewer_and_own_note_rules(client, SessionLocal):
    ctx = setup(client, SessionLocal)
    outsider = register(client, 'business-outsider@booker.test')
    oh = auth_header(outsider['token'])
    template_id = post(client, ctx, ctx['base'], {'name': 'Шаблон', 'source_event_id': ctx['event']['id']}).json()['id']
    note_url = f"/business/events/{ctx['event']['id']}/notes"
    note_id = post(client, ctx, note_url, {'body': 'Private'}).json()['id']
    assert client.get(ctx['base'], headers=oh).status_code == 403
    assert client.get(note_url, headers=oh).status_code == 403
    assert client.post(f'/business/templates/{template_id}/events', headers={**oh, 'Idempotency-Key': 'foreign-key'}, json=draft_body(ctx)).status_code == 403
    with SessionLocal() as db:
        member = TeamMember(organization_id=ctx['customer']['id'], user_id=outsider['user_id'], role='viewer'); db.add(member); db.commit()
    assert client.get(note_url, headers=oh).status_code == 200
    assert not client.get(note_url, headers=oh).json()['items'][0]['can_edit']
    assert client.post(note_url, headers={**oh, 'Idempotency-Key': 'viewer-key'}, json={'body': 'Forbidden'}).status_code == 403
    assert client.post(f'/business/templates/{template_id}/archive', headers=oh).status_code == 403
    with SessionLocal() as db:
        db.query(TeamMember).filter_by(user_id=outsider['user_id'], organization_id=ctx['customer']['id']).one().role = 'manager'; db.commit()
    assert client.put(f'/business/notes/{note_id}', headers=oh, json={'body': 'Changed', 'expected_revision': 1}).status_code == 403
    assert client.delete(f'/business/notes/{note_id}?expected_revision=1', headers=oh).status_code == 403
    assert client.post(ctx['base'], headers={**ctx['headers'], 'Idempotency-Key': 'cross-org-key'}, json={'source_event_id': '00000000-0000-0000-0000-000000000000', 'name': 'Foreign'}).status_code == 404
    own_payload = {'body': 'Manager note'}
    own_headers = {**oh, 'Idempotency-Key': 'manager-note-key'}
    made = client.post(note_url, headers=own_headers, json=own_payload)
    assert made.status_code == 201, made.text
    with SessionLocal() as db:
        db.query(TeamMember).filter_by(user_id=outsider['user_id'], organization_id=ctx['customer']['id']).delete()
        db.commit()
        assert db.query(BusinessEventTemplate).count() == 1
    assert client.post(note_url, headers=own_headers, json=own_payload).status_code == 403


def test_business_migration_upgrade_downgrade(tmp_path):
    from pathlib import Path

    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from alembic import command

    url = f"sqlite:///{tmp_path / 'business.db'}"
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'head')
    engine = create_engine(url)
    assert {'business_event_templates', 'business_event_notes'} <= set(inspect(engine).get_table_names())
    assert {'events', 'users'} == {f['referred_table'] for f in inspect(engine).get_foreign_keys('business_event_notes')}
    command.downgrade(config, 'b9c0d1e2f3a4')
    assert 'business_event_notes' not in inspect(engine).get_table_names()
    assert 'event_repeat_preferences' in inspect(engine).get_table_names()
    command.upgrade(config, 'head')
    assert 'business_event_templates' in inspect(engine).get_table_names()
    engine.dispose()
