"""Shared TOTP helpers for API tests."""

TEST_TOTP_SECRET = "JBSWY3DPEHPK3PXP"


def totp_code(secret: str = TEST_TOTP_SECRET) -> str:
    import pyotp

    return pyotp.TOTP(secret).now()


def admin_totp_headers(token: str, secret: str = TEST_TOTP_SECRET) -> dict[str, str]:
    from tests.conftest import auth_header

    return {**auth_header(token), "X-Booker-TOTP": totp_code(secret)}
