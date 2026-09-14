from datetime import timedelta
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from booker_api.models import AuditLog, Subscription, SupportTicket, TeamMember, User
from booker_api.security import now
from tests.conftest import auth_header, register


def setup(client, SessionLocal, kind='customer', plan='customer_business'):
    user = register(client, 'support-priority@booker.test', 'Customer')
    headers = auth_header(user['token'])
    org = client.post('/orgs', headers=headers, json={'name': 'Support org', 'kind': kind}).json()['id']
    with SessionLocal() as db:
        db.add(Subscription(organization_id=org, plan_code=plan, billing_period='monthly', status='active', starts_at=now()-timedelta(days=1), current_period_end=now()+timedelta(days=30))); db.commit()
    return user, headers, org


def create(client, headers, org=None, key='support-retry', **extra):
    return client.post('/support/tickets', headers={**headers, 'Idempotency-Key': key}, json={'organization_id': org, 'category': 'payment', 'subject': 'Вопрос оплаты', 'body': 'PRIVATE Подробности вопроса', **extra})


def test_priority_snapshot_retry_expiration_and_private_audit(client, SessionLocal):
    user, headers, org = setup(client, SessionLocal)
    first = create(client, headers, org); assert first.status_code == 201, first.text
    ticket = first.json(); assert ticket['priority'] and ticket['escalation'] == 'human'
    assert create(client, headers, org).json()['id'] == ticket['id']
    assert create(client, headers, org, subject='Другая тема').status_code == 409
    with SessionLocal() as db:
        db.query(Subscription).filter_by(organization_id=org).one().current_period_end = now()-timedelta(seconds=1); db.commit()
    assert create(client, headers, org).json()['priority']
    assert not create(client, headers, org, key='expired-plan').json()['priority']
    assert client.get(f"/support/tickets/{ticket['id']}", headers=headers).json()['body'].startswith('PRIVATE')
    with SessionLocal() as db:
        assert db.query(SupportTicket).count() == 2
        logs = db.query(AuditLog).filter(AuditLog.action.like('support.%')).all()
        assert all('PRIVATE' not in str(log.payload) for log in logs)
        assert db.query(AuditLog).filter_by(action='support.ticket.created').count() == 2
        db.query(TeamMember).filter_by(organization_id=org, user_id=user['user_id']).delete(); db.commit()
    assert create(client, headers, org).status_code == 403


def test_queue_permissions_pagination_detail_and_close(client, SessionLocal):
    _user, headers, org = setup(client, SessionLocal)
    other = register(client, 'support-other@booker.test', 'Other')
    other_headers = auth_header(other['token'])
    ordinary = create(client, other_headers).json()
    priority = create(client, headers, org).json()
    assert not ordinary['priority']
    assert client.get('/support/tickets', headers=other_headers).json()['total'] == 1
    for method, suffix in [('get', ''), ('post', '/close')]:
        assert getattr(client, method)(f"/support/tickets/{priority['id']}{suffix}", headers=other_headers).status_code == 403
    assert create(client, other_headers, org).status_code == 403
    admin = register(client, 'support-admin@booker.test', 'Operator')
    with SessionLocal() as db:
        db.get(User, admin['user_id']).is_platform_admin = True; db.commit()
    admin_headers = auth_header(admin['token'])
    queue = client.get('/support/tickets?state=open&limit=1', headers=admin_headers).json()
    assert queue['is_operator'] and queue['total'] == 2 and queue['items'][0]['id'] == priority['id']
    assert 'body' not in queue['items'][0]
    assert client.get('/support/tickets?state=open&limit=1&offset=1', headers=admin_headers).json()['items'][0]['id'] == ordinary['id']
    assert client.get(f"/support/tickets/{priority['id']}", headers=admin_headers).status_code == 200
    for _ in range(2):
        assert client.post(f"/support/tickets/{priority['id']}/close", headers=admin_headers).status_code == 200
    assert client.get('/support/tickets?state=open', headers=admin_headers).json()['items'][0]['id'] == ordinary['id']
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action='support.ticket.closed').count() == 1
    assert client.get('/support/tickets?state=unrecognized', headers=admin_headers).status_code == 422
    assert create(client, headers, org, subject='   ', key='spaces-only').status_code == 422


def test_premium_pro_and_flag(client, SessionLocal, monkeypatch):
    from booker_api.config import settings
    _user, headers, org = setup(client, SessionLocal, 'artist', 'artist_premium')
    assert create(client, headers, org).json()['priority']
    with SessionLocal() as db:
        db.query(Subscription).filter_by(organization_id=org).one().plan_code = 'artist_pro'; db.commit()
    assert not create(client, headers, org, key='pro-request').json()['priority']
    monkeypatch.setattr(settings, 'commercial_plans', False)
    assert not create(client, headers, org, key='flag-request').json()['priority']


def test_support_migration(tmp_path):
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    url = f"sqlite:///{tmp_path / 'support.db'}"; config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'd1e2f3a4b5c6'); engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO users (id,email,full_name,password_hash,is_platform_admin,totp_enabled,created_at) VALUES ('support-legacy-user','legacy@test.local','Legacy','x',0,0,CURRENT_TIMESTAMP)")
        conn.exec_driver_sql("INSERT INTO support_tickets (id,author_user_id,category,subject,body,status,created_at) VALUES ('legacy-ticket','support-legacy-user','other','Legacy','Saved content','open',CURRENT_TIMESTAMP)")
    command.upgrade(config, 'head')
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT priority,body FROM support_tickets WHERE id='legacy-ticket'").one() == (0, 'Saved content')
    command.downgrade(config, 'd1e2f3a4b5c6')
    assert 'priority' not in {c['name'] for c in inspect(engine).get_columns('support_tickets')}
    command.upgrade(config, 'head'); engine.dispose()


def test_support_admin_session_step_up(client, SessionLocal, monkeypatch):
    from booker_api.config import settings
    user, headers, org = setup(client, SessionLocal)
    ticket = create(client, headers, org).json()
    with SessionLocal() as db:
        db.get(User, user['user_id']).is_platform_admin = True; db.commit()
    monkeypatch.setattr(settings, 'require_admin_2fa_enforced', True)
    assert client.get('/support/tickets', headers=headers).status_code == 403
    assert client.get(f"/support/tickets/{ticket['id']}", headers=headers).status_code == 403
    assert client.post(f"/support/tickets/{ticket['id']}/close", headers=headers).status_code == 403
