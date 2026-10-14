"""Exercise real Home Assistant config flows with a mocked remote login."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.panasonic_cc_reliable.config_flow import ComfortCloudFlow
from custom_components.panasonic_cc_reliable.vendor.exceptions import MFARequiredError


def flow(hass):
    result = ComfortCloudFlow()
    result.hass = hass
    result.context = {"source": "user"}
    return result


def mocks():
    session = SimpleNamespace(cookie_jar=SimpleNamespace(), close=AsyncMock(), closed=False)
    client = SimpleNamespace(
        login=AsyncMock(),
        complete_mfa=AsyncMock(),
        devices=AsyncMock(return_value=[object()]),
        settings=SimpleNamespace(
            data={"access_token": "synthetic-token", "refresh_token": "synthetic-refresh"}
        ),
    )
    return session, client


async def test_user_form_is_a_real_ha_form(hass):
    result = await flow(hass).async_step_user()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert {str(key) for key in result["data_schema"].schema} == {
        "username",
        "password",
        "app_version",
    }


async def test_setup_uses_and_saves_selected_app_version(hass):
    session, client = mocks()
    value = flow(hass)
    with (
        patch(
            "custom_components.panasonic_cc_reliable.config_flow.aiohttp.ClientSession",
            return_value=session,
        ),
        patch(
            "custom_components.panasonic_cc_reliable.config_flow.ComfortCloudClient",
            return_value=client,
        ) as factory,
    ):
        result = await value.async_step_user(
            {"username": "test@example.invalid", "password": "synthetic", "app_version": "4.4.0"}
        )
    assert factory.call_args.args[1] == "4.4.0"
    assert result["options"]["app_version"] == "4.4.0"


async def test_invalid_setup_version_does_not_attempt_login(hass):
    result = await flow(hass).async_step_user(
        {"username": "test@example.invalid", "password": "synthetic", "app_version": "invalid"}
    )
    assert result["errors"] == {"app_version": "invalid_version"}


async def test_success_never_persists_password_or_otp(hass):
    session, client = mocks()
    value = flow(hass)
    with (
        patch(
            "custom_components.panasonic_cc_reliable.config_flow.aiohttp.ClientSession",
            return_value=session,
        ),
        patch(
            "custom_components.panasonic_cc_reliable.config_flow.ComfortCloudClient",
            return_value=client,
        ),
    ):
        result = await value.async_step_user(
            {"username": "test@example.invalid", "password": "SYNTHETIC-PRIVATE"}
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    serialized = json.dumps(result["data"])
    assert (
        "SYNTHETIC-PRIVATE" not in serialized
        and "password" not in serialized
        and "otp" not in serialized
    )
    assert "refresh_token" not in serialized
    session.close.assert_awaited_once()


async def test_mfa_uses_same_pending_login_session(hass):
    session, client = mocks()
    client.login.side_effect = MFARequiredError()
    value = flow(hass)
    with (
        patch(
            "custom_components.panasonic_cc_reliable.config_flow.aiohttp.ClientSession",
            return_value=session,
        ),
        patch(
            "custom_components.panasonic_cc_reliable.config_flow.ComfortCloudClient",
            return_value=client,
        ),
    ):
        result = await value.async_step_user(
            {"username": "test@example.invalid", "password": "synthetic"}
        )
        assert result["step_id"] == "mfa"
        session.close.assert_not_awaited()
        result = await value.async_step_mfa({"otp_code": "123456"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    client.login.assert_awaited_once()
    client.complete_mfa.assert_awaited_once_with("123456")
    session.close.assert_awaited_once()


async def test_aborted_flow_closes_private_cookie_jar(hass):
    session, client = mocks()
    value = flow(hass)
    value._session = session
    value._client = client
    value.async_remove()
    await hass.async_block_till_done()
    session.close.assert_awaited_once()


@pytest.mark.parametrize(
    "code,expected", [(4103, "agreements_required"), (4106, "app_version"), (429, "rate_limit")]
)
async def test_special_errors_are_not_reported_as_bad_passwords(hass, code, expected):
    from custom_components.panasonic_cc_reliable.vendor.helpers import failure

    session, client = mocks()
    client.login.side_effect = failure(401 if code != 429 else 429, code, {})
    value = flow(hass)
    with (
        patch(
            "custom_components.panasonic_cc_reliable.config_flow.aiohttp.ClientSession",
            return_value=session,
        ),
        patch(
            "custom_components.panasonic_cc_reliable.config_flow.ComfortCloudClient",
            return_value=client,
        ),
    ):
        result = await value.async_step_user(
            {"username": "test@example.invalid", "password": "synthetic"}
        )
    assert result["errors"] == {"base": expected}
    session.close.assert_awaited_once()


async def test_reauthentication_keeps_existing_entry(hass):
    import hashlib

    account_id = hashlib.sha256(b"test@example.invalid").hexdigest()[:24]
    existing = SimpleNamespace(unique_id=account_id, options={})
    session, client = mocks()
    value = flow(hass)
    value.context = {"source": "reauth", "entry_id": "synthetic-entry"}
    with (
        patch.object(value, "_get_reauth_entry", return_value=existing),
        patch.object(
            value,
            "async_update_reload_and_abort",
            return_value={"type": FlowResultType.ABORT, "reason": "reauth_successful"},
        ) as update,
        patch(
            "custom_components.panasonic_cc_reliable.config_flow.aiohttp.ClientSession",
            return_value=session,
        ),
        patch(
            "custom_components.panasonic_cc_reliable.config_flow.ComfortCloudClient",
            return_value=client,
        ),
    ):
        result = await value.async_step_reauth_confirm(
            {"username": "test@example.invalid", "password": "synthetic"}
        )
    assert result["reason"] == "reauth_successful"
    assert update.call_args.args[0] is existing
    assert update.call_args.kwargs["data_updates"] == {"account_id": account_id}


async def test_reauthentication_rejects_a_different_account_before_network(hass):
    import hashlib

    from homeassistant.data_entry_flow import AbortFlow

    account_id = hashlib.sha256(b"first@example.invalid").hexdigest()[:24]
    value = flow(hass)
    value.context = {"source": "reauth", "entry_id": "synthetic-entry"}
    with (
        patch.object(
            value, "_get_reauth_entry", return_value=SimpleNamespace(unique_id=account_id)
        ),
        pytest.raises(AbortFlow) as caught,
    ):
        await value.async_step_reauth_confirm(
            {"username": "second@example.invalid", "password": "synthetic"}
        )
    assert caught.value.reason == "wrong_account"
    assert value._session is None
