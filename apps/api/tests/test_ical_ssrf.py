import asyncio
import gzip
import ipaddress
from unittest.mock import MagicMock

import httpx
import pytest

from booker_api.ical import MAX_ICAL_BYTES, fetch_ical, parse_ical_events, validate_ical_fetch_url


def _response_stream(payload: bytes, *, headers: dict[str, str] | None = None) -> httpx.Response:
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield payload

    return httpx.Response(200, headers=headers, stream=Body())


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

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"location": private})
        )
    )
    monkeypatch.setattr("booker_api.ical.httpx.AsyncClient", MagicMock(return_value=client))

    with pytest.raises(ValueError, match="приватный"):
        asyncio.run(fetch_ical(public))


def test_fetch_ical_stops_stream_after_byte_limit(monkeypatch):
    url = "https://calendar.example.com/big.ics"
    monkeypatch.setattr(
        "booker_api.ical.socket.getaddrinfo",
        lambda host, port, **kwargs: [(None, None, None, None, ("93.184.216.34", port))],
    )

    class CountedBody(httpx.AsyncByteStream):
        chunks_read = 0

        async def __aiter__(self):
            for _ in range(4):
                self.chunks_read += 1
                yield b"x" * (MAX_ICAL_BYTES // 2)

    body = CountedBody()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body))
    )
    monkeypatch.setattr("booker_api.ical.httpx.AsyncClient", MagicMock(return_value=client))
    with pytest.raises(ValueError, match="большой"):
        asyncio.run(fetch_ical(url))
    assert body.chunks_read == 3


def test_fetch_ical_accepts_small_stream(monkeypatch):
    url = "https://calendar.example.com/small.ics"
    monkeypatch.setattr(
        "booker_api.ical.socket.getaddrinfo",
        lambda host, port, **kwargs: [(None, None, None, None, ("93.184.216.34", port))],
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: _response_stream(b"BEGIN:VCALENDAR\nEND:VCALENDAR")
        )
    )
    monkeypatch.setattr("booker_api.ical.httpx.AsyncClient", MagicMock(return_value=client))
    assert asyncio.run(fetch_ical(url)) == "BEGIN:VCALENDAR\nEND:VCALENDAR"


def test_fetch_ical_accepts_small_gzip_and_rejects_decompression_bomb(monkeypatch):
    url = "https://calendar.example.com/compressed.ics"
    monkeypatch.setattr(
        "booker_api.ical.socket.getaddrinfo",
        lambda host, port, **kwargs: [(None, None, None, None, ("93.184.216.34", port))],
    )
    original_client = httpx.AsyncClient

    def client_for(payload: bytes):
        client = original_client(
            transport=httpx.MockTransport(
                lambda request: _response_stream(
                    gzip.compress(payload), headers={"content-encoding": "gzip"}
                )
            )
        )
        monkeypatch.setattr("booker_api.ical.httpx.AsyncClient", MagicMock(return_value=client))

    small = b"BEGIN:VCALENDAR\nEND:VCALENDAR"
    client_for(small)
    assert asyncio.run(fetch_ical(url)) == small.decode()
    client_for(b"x" * (MAX_ICAL_BYTES + 1))
    with pytest.raises(ValueError, match="большой"):
        asyncio.run(fetch_ical(url))


def test_remote_invalid_utf8_within_raw_limit_is_not_rejected_after_decode(monkeypatch):
    url = "https://calendar.example.com/legacy.ics"
    monkeypatch.setattr(
        "booker_api.ical.socket.getaddrinfo",
        lambda host, port, **kwargs: [(None, None, None, None, ("93.184.216.34", port))],
    )
    payload = (
        b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:legacy\nDTSTART:20261005T180000Z\n"
        + b"DESCRIPTION:"
        + b"\xff" * 200_000
        + b"\nEND:VEVENT\nEND:VCALENDAR"
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: _response_stream(payload))
    )
    monkeypatch.setattr("booker_api.ical.httpx.AsyncClient", MagicMock(return_value=client))
    assert len(parse_ical_events(asyncio.run(fetch_ical(url)))) == 1


def test_parser_limits_event_count(monkeypatch):
    monkeypatch.setattr("booker_api.ical.MAX_ICAL_EVENTS", 1)
    event = "BEGIN:VEVENT\nUID:one\nDTSTART:20261005T180000Z\nEND:VEVENT\n"
    assert len(parse_ical_events("BEGIN:VCALENDAR\n" + event + "END:VCALENDAR")) == 1
    with pytest.raises(ValueError, match="много событий"):
        parse_ical_events("BEGIN:VCALENDAR\n" + event + event + "END:VCALENDAR")


def test_blocked_ipv6_mapped_loopback():
    from booker_api.ical import _is_blocked_ip

    assert _is_blocked_ip(ipaddress.ip_address("::ffff:127.0.0.1")) is True
    assert _is_blocked_ip(ipaddress.ip_address("::1")) is True
