"""Authenticate against scripted, synthetic HTTP pages, never a real account."""

import time
from http.cookies import SimpleCookie
from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.panasonic_cc_reliable.vendor.ccappversion import CCAppVersion
from custom_components.panasonic_cc_reliable.vendor.panasonicauthentication import (
    PanasonicAuthentication,
)
from custom_components.panasonic_cc_reliable.vendor.panasonicsettings import PanasonicSettings


def reply(status, text="", headers=None, cookies=None):
    return SimpleNamespace(
        status=status,
        headers=headers or {},
        cookies=cookies or {},
        text=AsyncMock(return_value=text),
    )


async def test_classic_login_uses_cookie_value_and_correct_relative_redirect():
    cookie = SimpleCookie()
    cookie["_csrf"] = "synthetic-csrf"
    session = SimpleNamespace(
        cookie_jar=SimpleNamespace(clear_domain=lambda domain: None),
        get=AsyncMock(
            side_effect=[
                reply(302, headers={"Location": "/authorize-page?state=synthetic-state"}),
                reply(200, cookies=cookie),
                reply(
                    302, headers={"Location": "panasonic-iot-cfc://callback?code=synthetic-code"}
                ),
            ]
        ),
        post=AsyncMock(
            side_effect=[
                reply(200, '<input type="hidden" name="wa" value="synthetic-wa">'),
                reply(302, headers={"Location": "/continue"}),
                reply(
                    200,
                    '{"access_token":"synthetic-access","refresh_token":"synthetic-refresh","expires_in":3600}',
                ),
                reply(200, '{"clientId":"synthetic-client"}'),
            ]
        ),
    )
    settings = PanasonicSettings()
    auth = PanasonicAuthentication(session, settings, CCAppVersion("1.21.0"))
    await auth.authenticate("test@example.invalid", "synthetic-password")
    assert session.post.call_args_list[0].kwargs["json"]["_csrf"] == "synthetic-csrf"
    assert session.get.call_args_list[2].args[0] == "https://authglb.digital.panasonic.com/continue"
    assert settings.refresh_token == "synthetic-refresh"
    assert settings.data["expires_at"] > time.time() + 3500


async def test_mfa_otp_grant_updates_tokens():
    session = SimpleNamespace(
        post=AsyncMock(
            side_effect=[
                reply(200, "{}"),
                reply(
                    200,
                    '{"access_token":"synthetic-access","refresh_token":"synthetic-refresh","expires_in":3600}',
                ),
            ]
        )
    )
    settings = PanasonicSettings()
    auth = PanasonicAuthentication(session, settings, CCAppVersion("1.21.0"))
    auth._mfa_token = "synthetic-mfa-token"
    await auth.verify_mfa("123456")
    assert settings.refresh_token == "synthetic-refresh"
    assert (
        session.post.call_args.kwargs["json"]["grant_type"]
        == "http://auth0.com/oauth/grant-type/mfa-otp"
    )


async def test_guardian_mfa_follows_transaction_and_authorization_code():
    session = SimpleNamespace(
        post=AsyncMock(
            side_effect=[
                reply(200, '{"transactionToken":"synthetic-transaction"}'),
                reply(200, "{}"),
                reply(200, '{"state":"accepted","token":"synthetic-signature"}'),
                reply(
                    302, headers={"Location": "panasonic-iot-cfc://callback?code=synthetic-code"}
                ),
                reply(
                    200,
                    '{"access_token":"synthetic-access","refresh_token":"synthetic-refresh","expires_in":3600}',
                ),
            ]
        )
    )
    settings = PanasonicSettings()
    auth = PanasonicAuthentication(session, settings, CCAppVersion("1.21.0"))
    auth._guardian_mfa_config = {
        "serviceUrl": "https://authglb.digital.panasonic.com/guardian",
        "requestToken": "synthetic-request",
        "postActionURL": "https://authglb.digital.panasonic.com/resume",
    }
    auth._code_verifier = "synthetic-verifier"
    await auth.verify_mfa("123456")
    assert settings.refresh_token == "synthetic-refresh"
    assert session.post.call_args_list[3].kwargs["data"] == {
        "accepted": "true",
        "signature": "synthetic-signature",
    }
