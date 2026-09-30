from datetime import timedelta

from booker_api.models import Subscription, TeamInvitation, TeamMember
from booker_api.security import now
from tests.conftest import auth_header, grant_team_plan, register


def setup(client):
    owner = register(client, 'team-owner@booker.test', 'Owner')
    headers = auth_header(owner['token'])
    org = client.post('/orgs', headers=headers, json={'name': 'Team', 'kind': 'customer'}).json()
    guest = register(client, 'team-guest@booker.test', 'Guest')
    return owner, headers, org['id'], guest


def invitation(client, headers, org, secret='a'*64, role='manager', email='team-guest@booker.test'):
    return client.post(f'/orgs/{org}/team/invitations', headers=headers, json={'email': email, 'role': role, 'secret': secret, 'can_confirm_offer': True})


def accept(client, guest, secret='a'*64):
    return client.post('/team-invitations/accept', headers={**auth_header(guest['token']), 'X-Team-Invitation': secret})


def test_free_capacity_and_paid_invitation_replay(client, SessionLocal):
    owner, headers, org, guest = setup(client)
    assert invitation(client, headers, org).status_code == 409
    assert client.post(f'/orgs/{org}/members', headers=headers, json={'user_id': guest['user_id']}).status_code == 409
    grant_team_plan(client, org)
    first = invitation(client, headers, org)
    assert first.status_code == 201, first.text
    assert invitation(client, headers, org).json()['id'] == first.json()['id']
    assert invitation(client, headers, org, role='viewer').status_code == 409
    preview = client.post('/team-invitations/preview', headers={**auth_header(guest['token']), 'X-Team-Invitation': 'a'*64})
    assert preview.status_code == 200 and preview.json()['name'] == 'Team'
    assert accept(client, owner).status_code == 403
    result = accept(client, guest)
    assert result.status_code == 200, result.text
    assert accept(client, guest).json()['reused']
    data = client.get(f'/orgs/{org}/team', headers=headers).json()
    assert data['used'] == 2 and data['reserved'] == 0
    with SessionLocal() as db:
        row = db.get(TeamInvitation, first.json()['id'])
        assert row.token_hash != 'a'*64
        assert db.query(TeamMember).filter_by(organization_id=org).count() == 2
        assert not hasattr(row, 'secret')


def test_pending_capacity_and_downgrade_preserve_existing_members(client, SessionLocal):
    _owner, headers, org, guest = setup(client)
    grant_team_plan(client, org)
    for i in range(4):
        assert invitation(client, headers, org, secret=str(i)*64, email=f'pending{i}@booker.test').status_code == 201
    assert invitation(client, headers, org).status_code == 409
    data = client.get(f'/orgs/{org}/team', headers=headers).json()
    assert data['reserved'] == 4
    row_id = data['invitations'][0]['id']
    assert client.post(f'/orgs/{org}/team/invitations/{row_id}/revoke', headers=headers).status_code == 200
    assert invitation(client, headers, org).status_code == 201
    with SessionLocal() as db:
        db.query(Subscription).filter_by(organization_id=org).one().current_period_end = now()-timedelta(seconds=1); db.commit()
    assert accept(client, guest).status_code == 409
    data = client.get(f'/orgs/{org}/team', headers=headers).json()
    assert data['used'] == 1 and data['seats'] == 1
    grant_team_plan(client, org)
    assert accept(client, guest).status_code == 200
    with SessionLocal() as db:
        db.query(Subscription).filter_by(organization_id=org).one().current_period_end = now()-timedelta(seconds=1); db.commit()
    assert client.get(f'/orgs/{org}/team', headers=auth_header(guest['token'])).status_code == 200


def test_expiry_revoke_and_removed_member_cannot_rejoin(client, SessionLocal):
    _owner, headers, org, guest = setup(client)
    grant_team_plan(client, org)
    first = invitation(client, headers, org).json()['id']
    with SessionLocal() as db:
        db.get(TeamInvitation, first).expires_at = now()-timedelta(seconds=1); db.commit()
    assert accept(client, guest).status_code == 410
    second = invitation(client, headers, org, 'b'*64).json()['id']
    assert client.post(f'/orgs/{org}/team/invitations/{second}/revoke', headers=headers).status_code == 200
    assert accept(client, guest, 'b'*64).status_code == 410
    assert invitation(client, headers, org, 'c'*64).status_code == 201
    assert accept(client, guest, 'c'*64).status_code == 200
    data = client.get(f'/orgs/{org}/team', headers=headers).json()
    target = next(m for m in data['members'] if not m['is_self'])
    assert client.delete(f"/orgs/{org}/team/members/{target['id']}", headers=headers).status_code == 200
    assert accept(client, guest, 'c'*64).status_code == 410
    assert client.get(f'/orgs/{org}/team', headers=auth_header(guest['token'])).status_code == 403


def test_role_authorization_last_owner_and_current_inviter(client, SessionLocal):
    _owner, headers, org, guest = setup(client)
    grant_team_plan(client, org)
    assert invitation(client, headers, org, role='admin').status_code == 201
    assert accept(client, guest).status_code == 200
    gh = auth_header(guest['token'])
    assert invitation(client, gh, org, 'b'*64, role='admin', email='third@booker.test').status_code == 403
    assert invitation(client, gh, org, 'b'*64, email='third@booker.test').status_code == 201
    data = client.get(f'/orgs/{org}/team', headers=headers).json()
    own = next(m for m in data['members'] if m['is_self'])
    path = f"/orgs/{org}/team/members/{own['id']}"
    assert client.delete(path, headers=headers).status_code == 409
    assert client.delete(path, headers=gh).status_code == 403
    assert client.put(path, headers=headers, json={'role': 'viewer', 'can_confirm_offer': False, 'expected_role': 'owner', 'expected_can_confirm_offer': True}).status_code == 409
    other = next(m for m in data['members'] if not m['is_self'])
    edit = {'role': 'viewer', 'can_confirm_offer': True, 'expected_role': 'admin', 'expected_can_confirm_offer': True}
    assert client.put(f"/orgs/{org}/team/members/{other['id']}", headers=headers, json=edit).status_code == 200
    assert not next(m for m in client.get(f'/orgs/{org}/team', headers=headers).json()['members'] if m['id'] == other['id'])['can_confirm_offer']
    third = register(client, 'third@booker.test', 'Third')
    assert accept(client, third, 'b'*64).status_code == 410
    assert invitation(client, gh, org, 'd'*64, email='fourth@booker.test').status_code == 403


def test_team_invitation_migration(tmp_path):
    from pathlib import Path

    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from alembic import command

    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    url = f"sqlite:///{tmp_path / 'team.db'}"; config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'head'); engine = create_engine(url)
    assert 'team_invitations' in inspect(engine).get_table_names()
    command.downgrade(config, 'c0d1e2f3a4b5')
    assert 'team_invitations' not in inspect(engine).get_table_names()
    command.upgrade(config, 'head'); engine.dispose()


def test_supply_plan_seats_and_business_flag(client, SessionLocal, monkeypatch):
    from booker_api.config import settings

    _owner, headers, org, _guest = setup(client)
    for kind, code, seats in [('artist', 'artist_pro', 2), ('venue', 'venue_premium', 5)]:
        target = client.post('/orgs', headers=headers, json={'name': kind, 'kind': kind}).json()['id']
        with SessionLocal() as db:
            db.add(Subscription(organization_id=target, plan_code=code, billing_period='monthly', status='active', starts_at=now()-timedelta(days=1), current_period_end=now()+timedelta(days=1))); db.commit()
        for i in range(seats-1):
            assert invitation(client, headers, target, secret=(str(i+5) if kind == 'artist' else str(i))*64, email=f'{kind}{i}@booker.test').status_code == 201
        assert invitation(client, headers, target, secret='f'*64, email='overflow@booker.test').status_code == 409
    grant_team_plan(client, org)
    monkeypatch.setattr(settings, 'customer_business', False)
    assert client.get(f'/orgs/{org}/team', headers=headers).json()['seats'] == 1
    assert invitation(client, headers, org, secret='e'*64).status_code == 409


def test_current_platform_admin_may_issue_support_invitation(client, SessionLocal):
    from booker_api.models import User

    _owner, headers, org, guest = setup(client)
    grant_team_plan(client, org)
    admin = register(client, 'team-platform@booker.test', 'Platform')
    with SessionLocal() as db:
        db.get(User, admin['user_id']).is_platform_admin = True; db.commit()
    assert invitation(client, auth_header(admin['token']), org, role='admin').status_code == 201
    assert accept(client, guest).status_code == 200
    assert next(m for m in client.get(f'/orgs/{org}/team', headers=headers).json()['members'] if not m['is_self'])['role'] == 'admin'
