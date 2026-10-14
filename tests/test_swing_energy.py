"""Native swing controls and optional cloud electricity allocations."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.panasonic_cc_reliable.climate import ComfortCloudClimate
from custom_components.panasonic_cc_reliable.const import CONF_ENABLE_CONTROL
from custom_components.panasonic_cc_reliable.coordinator import ComfortCloudCoordinator
from custom_components.panasonic_cc_reliable.models import Snapshot
from custom_components.panasonic_cc_reliable.sensor import DailyEnergySensor


def ready(hass, entry, device, status):
    coordinator = ComfortCloudCoordinator(hass, entry, AsyncMock())
    coordinator.devices[device.id] = device
    coordinator.snapshots[device.id] = Snapshot()
    coordinator.snapshots[device.id].success(status, "live")
    coordinator.command = AsyncMock()
    coordinator.options[CONF_ENABLE_CONTROL] = True
    return coordinator


async def test_climate_swing_features_and_confirmed_state(hass, entry, ac_device, ac_status):
    coordinator = ready(hass, entry, ac_device, ac_status)
    entity = ComfortCloudClimate(coordinator, ac_device.id)
    assert entity.supported_features & ClimateEntityFeature.SWING_MODE
    assert entity.supported_features & ClimateEntityFeature.SWING_HORIZONTAL_MODE
    assert entity.swing_mode == entity.swing_horizontal_mode == "auto"
    await entity.async_set_swing_mode("down")
    coordinator.command.assert_awaited_once_with(ac_device.id, {"fanAutoMode": 3, "airSwingUD": 1})
    assert entity.swing_mode == "auto"
    await coordinator.async_shutdown()


async def test_cloud_correction_keeps_same_daily_reset(hass, entry, ac_device, ac_status):
    from homeassistant.components.sensor import SensorStateClass

    coordinator = ready(hass, entry, ac_device, ac_status)
    coordinator.energy[ac_device.id] = {
        "date": dt_util.now().strftime("%Y%m%d"),
        "consumption": 4,
        "last_success": dt_util.utcnow(),
    }
    sensor = DailyEnergySensor(coordinator, ac_device.id)
    reset = sensor.last_reset
    coordinator.energy[ac_device.id]["consumption"] = 3.8
    assert sensor.native_value == 3.8
    assert sensor.state_class == SensorStateClass.TOTAL
    assert sensor.last_reset == reset
    await coordinator.async_shutdown()


async def test_horizontal_swing_preserves_vertical_auto(hass, entry, ac_device, ac_status):
    coordinator = ready(hass, entry, ac_device, ac_status)
    await ComfortCloudClimate(coordinator, ac_device.id).async_set_swing_horizontal_mode("left")
    coordinator.command.assert_awaited_once_with(ac_device.id, {"fanAutoMode": 2, "airSwingLR": 1})
    await coordinator.async_shutdown()


async def test_unsupported_continuous_swing_is_not_offered_or_sent(
    hass, entry, ac_device, ac_status
):
    coordinator = ready(hass, entry, ac_device, ac_status)
    entity = ComfortCloudClimate(coordinator, ac_device.id)
    assert "swing" not in entity.swing_modes
    with pytest.raises(HomeAssistantError):
        await entity.async_set_swing_mode("swing")
    coordinator.command.assert_not_awaited()
    await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "heat,cool,expected",
    [
        (0.75, 0.25, (3, 1)),
        (75, 25, (None, None)),
        (None, None, (None, None)),
        (0.8, 0.8, (None, None)),
        (0, 1, (0, 4)),
    ],
)
async def test_energy_allocates_only_unambiguous_reported_fractions(
    hass, entry, ac_device, ac_status, heat, cool, expected
):
    coordinator = ready(hass, entry, ac_device, ac_status)
    coordinator.client.energy.return_value = {
        "historyDataList": [
            {
                "dataTime": dt_util.now().strftime("%Y%m%d"),
                "consumption": 4,
                "heatConsumptionRate": heat,
                "coolConsumptionRate": cool,
            }
        ]
    }
    await coordinator._update_energy(ac_device)
    data = coordinator.energy[ac_device.id]
    assert data["consumption"] == 4
    assert (data["heating_consumption"], data["cooling_consumption"]) == expected
    sensor = DailyEnergySensor(
        coordinator, ac_device.id, "heating_consumption", "Heating electricity today"
    )
    assert sensor.available == (expected[0] is not None)
    await coordinator.async_shutdown()
