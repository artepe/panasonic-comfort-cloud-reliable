"""Validate cloud mappings, bounded controls and conditional entity discovery."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.panasonic_cc_reliable.climate import ComfortCloudClimate
from custom_components.panasonic_cc_reliable.coordinator import ComfortCloudCoordinator
from custom_components.panasonic_cc_reliable.entity import add_dynamic_entities
from custom_components.panasonic_cc_reliable.models import Device, Snapshot
from custom_components.panasonic_cc_reliable.select import VERTICAL, SwingSelect
from custom_components.panasonic_cc_reliable.sensor import (
    CloudFieldSensor,
    DailyEnergySensor,
    temperature,
)


def ready(hass, entry, ac_device, ac_status):
    coordinator = ComfortCloudCoordinator(hass, entry, AsyncMock())
    coordinator.devices[ac_device.id] = ac_device
    coordinator.snapshots[ac_device.id] = Snapshot()
    coordinator.snapshots[ac_device.id].success(ac_status, "live")
    coordinator.command = AsyncMock()
    return coordinator


async def test_temperature_and_mode_do_not_claim_compressor_activity(
    hass, entry, ac_device, ac_status
):
    result = ready(hass, entry, ac_device, ac_status)
    entity = ComfortCloudClimate(result, ac_device.id)
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.target_temperature == 22.5
    assert entity.current_temperature == 21
    assert entity.hvac_action is None
    await result.async_shutdown()


@pytest.mark.parametrize("value", [8, 15, 30.5, 40, 21.1, float("nan")])
async def test_setpoint_rejects_unverified_or_invalid_ranges(
    hass, entry, ac_device, ac_status, value
):
    result = ready(hass, entry, ac_device, ac_status)
    with pytest.raises(HomeAssistantError):
        await ComfortCloudClimate(result, ac_device.id).async_set_temperature(temperature=value)
    result.command.assert_not_awaited()
    await result.async_shutdown()


async def test_temperature_does_not_implicitly_turn_off_unit_on(hass, entry, ac_device, ac_status):
    ac_status["parameters"]["operate"] = 0
    result = ready(hass, entry, ac_device, ac_status)
    with pytest.raises(HomeAssistantError):
        await ComfortCloudClimate(result, ac_device.id).async_set_temperature(temperature=22)
    result.command.assert_not_awaited()
    await result.async_shutdown()


async def test_command_does_not_optimistically_change_confirmed_reading(
    hass, entry, ac_device, ac_status
):
    result = ready(hass, entry, ac_device, ac_status)
    entity = ComfortCloudClimate(result, ac_device.id)
    await entity.async_set_temperature(temperature=23)
    result.command.assert_awaited_once_with(ac_device.id, {"temperatureSet": 23})
    assert entity.target_temperature == 22.5
    await result.async_shutdown()


async def test_vertical_swing_preserves_horizontal_auto(hass, entry, ac_device, ac_status):
    result = ready(hass, entry, ac_device, ac_status)
    entity = SwingSelect(result, ac_device.id, "airSwingUD", VERTICAL, "Vertical swing")
    await entity.async_select_option("down")
    result.command.assert_awaited_once_with(ac_device.id, {"fanAutoMode": 3, "airSwingUD": 1})
    await result.async_shutdown()


async def test_zones_tracked_by_zone_id_after_reorder(hass, entry, ac_device, ac_status):
    result = ready(hass, entry, ac_device, ac_status)
    result.snapshots[ac_device.id].raw = {
        "status": {
            "zoneStatus": [{"zoneId": 2, "temperatureNow": 40}, {"zoneId": 1, "temperatureNow": 22}]
        }
    }
    description = temperature("zone_1", "Zone 1", "status.zoneStatus.0.temperatureNow", "Test")
    entity = CloudFieldSensor(
        result, ac_device.id, description, zone_id=1, zone_field="temperatureNow"
    )
    assert entity.native_value == 22
    await result.async_shutdown()


async def test_energy_from_previous_day_is_unavailable(hass, entry, ac_device, ac_status):
    from homeassistant.util import dt as dt_util

    result = ready(hass, entry, ac_device, ac_status)
    result.energy[ac_device.id] = {
        "date": (dt_util.now() - timedelta(days=1)).strftime("%Y%m%d"),
        "consumption": 4,
        "last_success": dt_util.utcnow(),
    }
    assert not DailyEnergySensor(result, ac_device.id).available
    await result.async_shutdown()


async def test_dynamic_discovery_deduplicates_and_adds_later_devices(
    hass, entry, ac_device, ac_status
):
    result = ready(hass, entry, ac_device, ac_status)
    added = []
    add_dynamic_entities(
        entry,
        result,
        lambda entities: added.extend(entities),
        lambda device_id: [ComfortCloudClimate(result, device_id)],
    )
    result.async_update_listeners()
    assert len(added) == 1
    other = Device("second-device", "Second", "Test", "ac", {})
    result.devices[other.id] = other
    result.snapshots[other.id] = Snapshot()
    result.async_update_listeners()
    assert len(added) == 2
    await result.async_shutdown()
