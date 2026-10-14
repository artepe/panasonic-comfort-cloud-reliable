"""Verify account serialization, retry budgets and typed failure boundaries."""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.panasonic_cc_reliable.api import ComfortCloudClient, RequestSession
from custom_components.panasonic_cc_reliable.errors import (
    AuthenticationError,
    CommandUncertainError,
    CommunicationError,
    ProtocolError,
    RateLimitError,
)
from custom_components.panasonic_cc_reliable.vendor.helpers import check_response, retry_delay


def response(status=200, body=None, headers=None):
    return SimpleNamespace(
        status=status,
        headers=headers or {},
        text=AsyncMock(return_value=json.dumps(body if body is not None else {"ok": True})),
    )


def client():
    result = ComfortCloudClient(
        SimpleNamespace(cookie_jar=SimpleNamespace()),
        "1.21.0",
        {
            "access_token": "synthetic",
            "expires_at": time.time() + 3600,
            "refresh_token": "synthetic-refresh",
            "client_id": "synthetic-client",
        },
        gap=0,
    )
    result.transport.request = AsyncMock(return_value=response())
    return result


async def test_multiple_expired_reads_refresh_once():
    api = client()
    api.settings.data["expires_at"] = 0

    async def refresh():
        await asyncio.sleep(0)
        api.settings.set_token("new", "rotated", time.time() + 3600)

    api.auth.refresh_token = AsyncMock(side_effect=refresh)
    await asyncio.gather(*(api.request("GET", "/device/group") for _ in range(5)))
    api.auth.refresh_token.assert_awaited_once()
    assert api.transport.request.await_count == 5


async def test_account_requests_do_not_overlap():
    api = client()
    active = maximum = 0

    async def request(*args, **kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        return response()

    api.transport.request.side_effect = request
    await asyncio.gather(*(api.request("GET", "/device/group") for _ in range(10)))
    assert maximum == 1


async def test_read_retry_is_bounded(monkeypatch):
    api = client()
    api.transport.request.side_effect = CommunicationError("Temporary failure")
    monkeypatch.setattr("custom_components.panasonic_cc_reliable.api.asyncio.sleep", AsyncMock())
    with pytest.raises(CommunicationError):
        await api.request("GET", "/device/group")
    assert api.transport.request.await_count == 3


async def test_write_timeout_is_not_replayed(ac_device):
    api = client()
    api.transport.request.side_effect = CommunicationError("Timeout")
    with pytest.raises(CommandUncertainError):
        await api.control(ac_device, {"operate": 1})
    assert api.transport.request.await_count == 1


async def test_write_auth_rejection_is_not_replayed(ac_device):
    api = client()
    api.transport.request.return_value = response(401)
    api.auth.refresh_token = AsyncMock()
    with pytest.raises(AuthenticationError):
        await api.control(ac_device, {"operate": 1})
    assert api.transport.request.await_count == 1
    api.auth.refresh_token.assert_not_awaited()


async def test_read_401_refreshes_and_registers_once():
    api = client()
    api.transport.request.side_effect = [response(401), response()]
    api.auth.refresh_token = AsyncMock()
    api.auth._retrieve_client_acc = AsyncMock()
    await api.request("GET", "/device/group")
    api.auth.refresh_token.assert_awaited_once()
    api.auth._retrieve_client_acc.assert_awaited_once()


async def test_rotated_token_saved_even_when_registration_fails():
    api = client()
    api._token_saver = AsyncMock()

    async def refresh():
        api.settings.set_token("new", "rotated", time.time() + 3600)

    api.auth.refresh_token = AsyncMock(side_effect=refresh)
    api.auth._retrieve_client_acc = AsyncMock(side_effect=CommunicationError("Server unavailable"))
    with pytest.raises(CommunicationError):
        await api._ensure_auth(force=True)
    assert api._token_saver.call_args.args[0]["refresh_token"] == "rotated"


async def test_rate_limit_does_not_trigger_read_retries():
    api = client()
    api.transport.request.return_value = response(429, headers={"Retry-After": "120"})
    with pytest.raises(RateLimitError) as caught:
        await api.request("GET", "/device/group")
    assert caught.value.retry_after == 120
    assert api.transport.request.await_count == 1


async def test_cooldown_stops_network_requests():
    session = SimpleNamespace(cookie_jar=SimpleNamespace(), request=AsyncMock())
    transport = RequestSession(session, gap=0)
    transport.cooldown_until = time.monotonic() + 60
    with pytest.raises(RateLimitError):
        await transport.get("https://accsmart.panasonic.com/device/group")
    session.request.assert_not_awaited()


async def test_auth_redirect_cannot_send_credentials_elsewhere():
    session = SimpleNamespace(cookie_jar=SimpleNamespace(), request=AsyncMock())
    with pytest.raises(ProtocolError):
        await RequestSession(session).post(
            "https://not-panasonic.example/login", json={"password": "synthetic"}
        )
    session.request.assert_not_awaited()


@pytest.mark.parametrize("error", [AuthenticationError(), RateLimitError(), ProtocolError()])
async def test_cached_fallback_cannot_hide_auth_or_rate_or_schema_errors(ac_device, error):
    api = client()
    api._status_request = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        await api.status(ac_device)
    assert api._status_request.await_count == 1


async def test_adapter_failure_can_return_labeled_cache(ac_device, ac_status):
    api = client()
    api._status_request = AsyncMock(side_effect=[CommunicationError(), ac_status])
    raw, source = await api.status(ac_device)
    assert source == "cached" and raw == ac_status
    assert api._status_request.call_args.kwargs["direct"] is False


async def test_hws_uses_group_listing_not_ac_endpoint():
    from custom_components.panasonic_cc_reliable.models import Device

    device = Device(
        "synthetic-hws", "Test tank", "Test", "hws", {"parameters": {"tankTemperature": 55}}
    )
    api = client()
    api.devices = AsyncMock(return_value=[device])
    raw, source = await api.status(device)
    assert source == "group_listing" and raw["parameters"]["tankTemperature"] == 55
    api.transport.request.assert_not_awaited()


async def test_generic_403_is_not_misclassified_as_bad_password():
    with pytest.raises(ProtocolError):
        await check_response(response(403, {"code": 4300}), "status", 200)


async def test_response_errors_do_not_expose_body():
    with pytest.raises(ProtocolError) as caught:
        await check_response(
            response(400, {"password": "PRIVATE", "access_token": "PRIVATE"}), "login", 200
        )
    assert "PRIVATE" not in str(caught.value)


def test_retry_after_missing_is_bounded():
    assert retry_delay(None) == 60
    assert retry_delay("999999999") == 86400


@pytest.mark.parametrize(
    "code,error_type",
    [(4103, "AgreementRequiredError"), (4106, "AppVersionError"), (429, "RateLimitError")],
)
async def test_http_200_error_envelopes_keep_correct_failure_type(code, error_type):
    from custom_components.panasonic_cc_reliable import errors

    api = client()
    api.transport.request.return_value = response(200, {"code": code, "message": "synthetic error"})
    with pytest.raises(getattr(errors, error_type)):
        await api.request("GET", "/device/group")
    assert api.transport.request.await_count == 1


async def test_unrecognized_nested_error_code_is_a_protocol_error():
    api = client()
    api.transport.request.return_value = response(200, {"code": {}, "message": "synthetic"})
    with pytest.raises(ProtocolError):
        await api.request("GET", "/device/group")


async def test_known_adapter_offline_does_not_waste_retry_budget():
    api = client()
    api.transport.request.return_value = response(500, {"code": 5005, "message": "synthetic"})
    with pytest.raises(CommunicationError):
        await api.request("GET", "/deviceStatus/test")
    assert api.transport.request.await_count == 1
