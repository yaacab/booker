import asyncio
import ipaddress
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from booker_api.ical import fetch_ical, validate_ical_fetch_url


def test_validate_rejects_http_scheme():
    with pytest.raises(ValueError, match="https"):
        validate_ical_fetch_url("http://calendar.example.com/x.ics")


def test_validate_rejects_loopback_literal():
    with pytest.raises(ValueError, match="приватный"):
        validate_ical_fetch_url("https://127.0.0.1/x.ics")


def test_validate_rejects_link_local_metadata():
    with pytest.raises(ValueError, match="приватный"):
        validate_ical_fetch_url("https://169.254.169.254/latest/meta-data/")


def test_validate_rejects_private_literal():
    with pytest.raises(ValueError, match="приватный"):
        validate_ical_fetch_url("https://10.0.0.5/cal.ics")


def test_validate_rejects_credentials():
    with pytest.raises(ValueError, match="credentials"):
        validate_ical_fetch_url("https://user:pass@calendar.example.com/x.ics")


def test_validate_rejects_non_443_port():
    with pytest.raises(ValueError, match="443"):
        validate_ical_fetch_url("https://calendar.example.com:8443/x.ics")


def test_validate_rejects_hostname_resolving_to_private(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        assert host == "evil.example"
        return [(None, None, None, None, ("192.168.1.9", port))]

    monkeypatch.setattr("booker_api.ical.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError, match="приватный"):
        validate_ical_fetch_url("https://evil.example/cal.ics")


def test_validate_allows_public_hostname(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(None, None, None, None, ("93.184.216.34", port))]

    monkeypatch.setattr("booker_api.ical.socket.getaddrinfo", fake_getaddrinfo)
    validate_ical_fetch_url("https://calendar.example.com/public.ics")


def test_fetch_ical_revalidates_redirect_to_private(monkeypatch):
    public = "https://calendar.example.com/public.ics"
    private = "https://127.0.0.1/secret.ics"

    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host == "calendar.example.com":
            return [(None, None, None, None, ("93.184.216.34", port))]
        raise AssertionError(f"unexpected host {host}")

    monkeypatch.setattr("booker_api.ical.socket.getaddrinfo", fake_getaddrinfo)

    redirect = httpx.Response(
        302,
        headers={"location": private},
        request=httpx.Request("GET", public),
    )

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=redirect)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr("booker_api.ical.httpx.AsyncClient", MagicMock(return_value=mock_client))

    with pytest.raises(ValueError, match="приватный"):
        asyncio.run(fetch_ical(public))


def test_blocked_ipv6_mapped_loopback():
    from booker_api.ical import _is_blocked_ip

    assert _is_blocked_ip(ipaddress.ip_address("::ffff:127.0.0.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("::1")) is True
