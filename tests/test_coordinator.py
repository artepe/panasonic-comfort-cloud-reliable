"""A broken device/history stream must not take other status streams down."""

import time
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from custom_components.panasonic_cc_reliable.const import CONF_ENABLE_CONTROL, CONF_ENABLE_ENERGY
from custom_components.panasonic_cc_reliable.coordinator import ComfortCloudCoordinator
from custom_components.panasonic_cc_reliable.errors import (
    AuthenticationError,
    CommunicationError,
    ProtocolError,
    RateLimitError,
)
from custom_components.panasonic_cc_reliable.models import Device, Snapshot


async def coordinator(hass, entry, ac_device):
    client = AsyncMock()
    client.devices.return_value = [ac_device]
    result = ComfortCloudCoordinator(hass, entry, client)
    await result._discover()
    return result, client


async def test_one_device_failure_preserves_other_device(hass, entry, ac_device, ac_status):
    result, client = await coordinator(hass, entry, ac_device)
    broken = Device("broken", "Broken", "Test", "ac", {})
    result.devices = {broken.id: broken, ac_device.id: ac_device}
    result.snapshots[broken.id] = Snapshot()
    client.status.side_effect = [CommunicationError(), (ac_status, "live")]
    data = await result._async_update_data()
    assert data[broken.id].failures == 1
    assert data[ac_device.id].failures == 0 and result.usable(ac_device.id)
    await result.async_shutdown()


async def test_energy_failure_does_not_lose_temperature(hass, entry, ac_device, ac_status):
    result, client = await coordinator(hass, entry, ac_device)
    result.options[CONF_ENABLE_ENERGY] = True
    client.status.return_value = (ac_status, "live")
    client.energy.side_effect = ProtocolError("No history")
    await result._async_update_data()
    assert result.usable(ac_device.id)
    assert result.energy[ac_device.id]["error"] == "No history"
    await result.async_shutdown()


async def test_rate_limit_stops_rest_of_cycle_and_sets_cooldown_interval(
    hass, entry, ac_device, ac_status
):
    result, client = await coordinator(hass, entry, ac_device)
    second = Device("second", "Second", "Test", "ac", {})
    result.devices[second.id] = second
    result.snapshots[second.id] = Snapshot()
    result.snapshots[ac_device.id].success(ac_status, "live")
    client.status.side_effect = RateLimitError("Rate limited", retry_after=1000)
    await result._async_update_data()
    assert client.status.await_count == 1
    assert result.update_interval.total_seconds() == 1000
    await result.async_shutdown()


async def test_revoked_auth_starts_ha_reauthentication(hass, entry, ac_device):
    result, client = await coordinator(hass, entry, ac_device)
    client.status.side_effect = AuthenticationError()
    with pytest.raises(ConfigEntryAuthFailed):
        await result._async_update_data()
    await result.async_shutdown()


async def test_removed_devices_not_considered_available(hass, entry, ac_device, ac_status):
    result, client = await coordinator(hass, entry, ac_device)
    result.snapshots[ac_device.id].success(ac_status, "live")
    other = Device("other", "Other", "Test", "ac", {})
    client.devices.return_value = [other]
    await result._discover()
    from custom_components.panasonic_cc_reliable.sensor import ConnectionSensor

    sensor = ConnectionSensor(
        result,
        ac_device.id if ac_device.id in result.devices else other.id,
        "connection",
        "Connection",
    )
    sensor.device_id = ac_device.id
    assert sensor.native_value == "removed"
    await result.async_shutdown()


async def test_default_monitoring_rejects_writes(hass, entry, ac_device, ac_status):
    result, client = await coordinator(hass, entry, ac_device)
    result.snapshots[ac_device.id].success(ac_status, "live")
    with pytest.raises(HomeAssistantError, match="Enable AC controls"):
        await result.command(ac_device.id, {"operate": 0})
    client.control.assert_not_awaited()
    await result.async_shutdown()


async def test_cached_data_does_not_authorize_controls(hass, entry, ac_device, ac_status):
    result, client = await coordinator(hass, entry, ac_device)
    result.options[CONF_ENABLE_CONTROL] = True
    ac_status["timestamp"] = int(time.time() * 1000)
    result.snapshots[ac_device.id].success(ac_status, "cached")
    with pytest.raises(HomeAssistantError, match="live"):
        await result.command(ac_device.id, {"operate": 0})
    client.control.assert_not_awaited()
    await result.async_shutdown()


async def test_recovery_clears_failure_and_restores_polling(hass, entry, ac_device, ac_status):
    result, client = await coordinator(hass, entry, ac_device)
    result.snapshots[ac_device.id].failures = 3
    result.snapshots[ac_device.id].error = "Old error"
    client.status.return_value = (ac_status, "live")
    await result._async_update_data()
    assert result.snapshots[ac_device.id].failures == 0
    assert result.snapshots[ac_device.id].error is None
    await result.async_shutdown()
