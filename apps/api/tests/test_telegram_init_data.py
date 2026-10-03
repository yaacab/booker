"""Mini App data is a first-factor claim only after server-side verification."""

import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from booker_api.auth_providers.telegram import InvalidTelegramInitData, verify_init_data

FAKE_BOT_VALUE = "fixture-telegram-token-not-a-real-secret"
NOW = 1_790_000_000


def signed_data(*, token: str = FAKE_BOT_VALUE, auth_date: int = NOW,
                user_id: int = 123456789, **extra: str) -> str:
    fields = {
        "auth_date": str(auth_date),
        "user": json.dumps({"id": user_id, "first_name": "Тест", "last_name": "Букер"},
                           ensure_ascii=False, separators=(",", ":")),
        **extra,
    }
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(key, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid_signed_claim_has_stable_replay_key_and_no_booker_session():
    raw = signed_data(query_id="test-query")
    claim = verify_init_data(raw, bot_token=FAKE_BOT_VALUE, now_epoch=NOW)
    assert claim.subject == "123456789"
    assert claim.first_name == "Тест"
    assert claim.last_name == "Букер"
    assert len(claim.proof_hash) == 64
    # Query parameter order changes the raw bytes but not the signed claim.
    assert verify_init_data("&".join(reversed(raw.split("&"))),
                            bot_token=FAKE_BOT_VALUE, now_epoch=NOW).proof_hash == claim.proof_hash
    assert not hasattr(claim, "token")


@pytest.mark.parametrize("raw", [
    "", "auth_date=123&user=%7B%7D", "hash=short", "broken-field",
    signed_data() + "&user=%7B%7D",
    signed_data().replace("123456789", "987654321"),
])
def test_missing_tampered_or_ambiguous_data_is_rejected(raw):
    with pytest.raises(InvalidTelegramInitData):
        verify_init_data(raw, bot_token=FAKE_BOT_VALUE, now_epoch=NOW)


def test_wrong_bot_expired_and_future_data_are_rejected():
    with pytest.raises(InvalidTelegramInitData):
        verify_init_data(signed_data(), bot_token="other-bot", now_epoch=NOW)
    with pytest.raises(InvalidTelegramInitData):
        verify_init_data(signed_data(auth_date=NOW - 301),
                         bot_token=FAKE_BOT_VALUE, now_epoch=NOW)
    with pytest.raises(InvalidTelegramInitData):
        verify_init_data(signed_data(auth_date=NOW + 31),
                         bot_token=FAKE_BOT_VALUE, now_epoch=NOW)


def test_signed_user_must_have_a_real_numeric_subject_and_name():
    raw = signed_data(user_id=0)
    with pytest.raises(InvalidTelegramInitData):
        verify_init_data(raw, bot_token=FAKE_BOT_VALUE, now_epoch=NOW)
    fields = {"auth_date": str(NOW), "user": json.dumps({"id": True, "first_name": ""})}
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    key = hmac.new(b"WebAppData", FAKE_BOT_VALUE.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(key, check_string.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(InvalidTelegramInitData):
        verify_init_data(urlencode(fields), bot_token=FAKE_BOT_VALUE, now_epoch=NOW)
