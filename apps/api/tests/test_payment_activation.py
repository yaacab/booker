"""Only an explicit code registration AND every launch gate enables a provider."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from booker_api.commerce import provider as commerce
from booker_api.config import settings
from booker_api.payments import adapter as booking
from booker_api.payments.stub import StubPaymentAdapter


@pytest.fixture
def activated(monkeypatch):
    monkeypatch.setattr(booking, '_live_adapters', {})
    monkeypatch.setattr(commerce, '_live_providers', {})
    for name, value in {
        'environment': 'production', 'payment_provider': 'acceptance',
        'commerce_provider': 'acceptance', 'payment_live_opt_in': True,
        'commerce_live_opt_in': True, 'payment_sandbox_accepted': True,
        'lawyer_approval_date': datetime.now(timezone.utc).date().isoformat(), 'payment_flow_approval': 'approved',
        'payment_merchant_id': 'acceptance-merchant', 'payment_public_key': 'test-public',
        'payment_secret_key': 'test-secret', 'webhook_secret': 'acceptance-booking-secret-32-characters',
        'commerce_webhook_secret': 'acceptance-commerce-secret-32-characters',
        'allow_default_webhook_secret': False, 'payment_allow_stub': False,
        'commerce_allow_stub': False, 'require_admin_2fa_enforced': True,
    }.items():
        monkeypatch.setattr(settings, name, value)
    calls = []

    class BookingFixture(StubPaymentAdapter):
        name = 'acceptance'

        def __init__(self):
            calls.append('booking')

    class CommerceFixture:
        name = 'acceptance'
        test_mode = False

        def __init__(self):
            calls.append('commerce')

    booking.register_payment_adapter('acceptance', BookingFixture)
    commerce.register_commerce_provider('acceptance', CommerceFixture)
    return calls


@pytest.mark.parametrize('field,value', [
    ('environment', 'test'), ('environment', 'dev'), ('environment', 'unknown'),
    ('payment_sandbox_accepted', False), ('lawyer_approval_date', ''),
    ('lawyer_approval_date', 'not-a-date'),
    ('lawyer_approval_date', (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()),
    ('payment_flow_approval', ''), ('payment_flow_approval', 'pending'),
    ('payment_merchant_id', ''), ('payment_public_key', ' '), ('payment_secret_key', ''),
    ('allow_default_webhook_secret', True), ('payment_allow_stub', True),
    ('commerce_allow_stub', True), ('require_admin_2fa_enforced', False),
])
def test_every_shared_gate_blocks_before_constructing_adapter(activated, monkeypatch, field, value):
    monkeypatch.setattr(settings, field, value)
    assert not booking.payment_live_enabled()
    assert not booking.payment_capabilities()['available']
    with pytest.raises(HTTPException) as exc:
        booking.get_payment_adapter()
    assert exc.value.status_code == 503
    assert isinstance(commerce.get_provider(), commerce.DisabledProvider)
    assert activated == []


@pytest.mark.parametrize('domain', ['booking', 'commerce'])
@pytest.mark.parametrize('kind', ['opt_in', 'signature', 'unknown'])
def test_independent_activation_switches(activated, monkeypatch, domain, kind):
    field = {'booking': {'opt_in': 'payment_live_opt_in', 'signature': 'webhook_secret', 'unknown': 'payment_provider'},
             'commerce': {'opt_in': 'commerce_live_opt_in', 'signature': 'commerce_webhook_secret', 'unknown': 'commerce_provider'}}[domain][kind]
    monkeypatch.setattr(settings, field, False if kind == 'opt_in' else 'unknown')
    if domain == 'booking':
        assert not booking.payment_live_enabled()
        with pytest.raises(HTTPException):
            booking.get_payment_adapter()
        assert commerce.get_provider().name == 'acceptance'
        assert activated == ['commerce']
    else:
        assert isinstance(commerce.get_provider(), commerce.DisabledProvider)
        assert booking.get_payment_adapter().name == 'acceptance'
        assert activated == ['booking']


def test_configured_registered_provider_is_selected_without_payment_side_effects(activated):
    assert booking.payment_live_enabled()
    assert booking.payment_capabilities() == {
        'available': True, 'test_mode': False,
        'message': 'Онлайн-оплата через платёжного партнёра',
    }
    assert booking.get_payment_adapter().name == 'acceptance'
    assert commerce.get_provider().name == 'acceptance'
    assert activated == ['booking', 'commerce']


@pytest.mark.parametrize('name', ['stub', 'disabled', 'external', 'live', '', ' Mixed', 'a.b'])
def test_reserved_or_import_like_names_cannot_be_registered(name):
    with pytest.raises(ValueError):
        booking.register_payment_adapter(name, lambda: None)
    with pytest.raises(ValueError):
        commerce.register_commerce_provider(name, lambda: None)


def test_registration_does_not_allow_silent_replacement(activated):
    for register in [booking.register_payment_adapter, commerce.register_commerce_provider]:
        with pytest.raises(ValueError):
            register('acceptance', lambda: None)


def test_invalid_factory_cannot_enable_stub_fallback_or_leak_error(activated, monkeypatch):
    def broken():
        raise RuntimeError('secret-credential')
    monkeypatch.setitem(booking._live_adapters, 'acceptance', broken)
    monkeypatch.setitem(commerce._live_providers, 'acceptance', broken)
    with pytest.raises(HTTPException) as exc:
        booking.get_payment_adapter()
    assert exc.value.status_code == 503 and 'secret-credential' not in exc.value.detail
    assert isinstance(commerce.get_provider(), commerce.DisabledProvider)
