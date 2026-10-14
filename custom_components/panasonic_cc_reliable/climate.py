"""Air-conditioner controls backed by confirmed cloud responses."""

from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_ENABLE_CONTROL
from .entity import ComfortCloudEntity, add_dynamic_entities
from .models import numeric
from .select import HORIZONTAL, VERTICAL, selected_swing, swing_parameters

PARALLEL_UPDATES = 1
MODES = {
    HVACMode.HEAT_COOL: 0,
    HVACMode.DRY: 1,
    HVACMode.COOL: 2,
    HVACMode.HEAT: 3,
    HVACMode.FAN_ONLY: 4,
}
FLAGS = {
    HVACMode.HEAT_COOL: "autoMode",
    HVACMode.DRY: "dryMode",
    HVACMode.COOL: "coolMode",
    HVACMode.HEAT: "heatMode",
    HVACMode.FAN_ONLY: "fanMode",
}
FANS = {"auto": 0, "low": 1, "low_mid": 2, "mid": 3, "high_mid": 4, "high": 5}
PRESETS = {"none": 0, "powerful": 1, "quiet": 2}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.coordinator

    def factory(device_id):
        if coordinator.devices[device_id].kind == "ac" and coordinator.snapshots[device_id].raw:
            yield ComfortCloudClimate(coordinator, device_id)

    add_dynamic_entities(entry, coordinator, async_add_entities, factory)


class ComfortCloudClimate(ComfortCloudEntity, ClimateEntity):
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 16
    _attr_max_temp = 30
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, device_id):
        super().__init__(coordinator, device_id, "climate")

    def feature(self, name):
        return self.snapshot.raw.get(
            name, self.coordinator.devices[self.device_id].listing.get(name, False)
        )

    @property
    def supported_features(self):
        if not self.coordinator.options[CONF_ENABLE_CONTROL]:
            return ClimateEntityFeature(0)
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )
        if self.value("parameters.fanSpeed") is not None:
            features |= ClimateEntityFeature.FAN_MODE
        if self.feature("quietMode") or self.feature("powerfulMode"):
            features |= ClimateEntityFeature.PRESET_MODE
        if self.value("parameters.airSwingUD") is not None:
            features |= ClimateEntityFeature.SWING_MODE
        if self.feature("airSwingLR") and self.value("parameters.airSwingLR") != 6:
            features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE
        return features

    @property
    def swing_modes(self):
        return [key for key in VERTICAL if key != "swing" or self.feature("autoSwingUD")]

    @property
    def swing_mode(self):
        return selected_swing(self.value("parameters") or {}, "airSwingUD", VERTICAL)

    @property
    def swing_horizontal_modes(self):
        return list(HORIZONTAL)

    @property
    def swing_horizontal_mode(self):
        return selected_swing(self.value("parameters") or {}, "airSwingLR", HORIZONTAL)

    async def async_set_swing_mode(self, swing_mode):
        if self.value("parameters.airSwingUD") is None or swing_mode not in self.swing_modes:
            raise HomeAssistantError("Unsupported vertical swing mode")
        await self.coordinator.command(
            self.device_id,
            swing_parameters(self.value("parameters") or {}, "airSwingUD", VERTICAL, swing_mode),
        )

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode):
        if not self.feature("airSwingLR") or self.value("parameters.airSwingLR") == 6:
            raise HomeAssistantError("This unit does not support horizontal swing")
        await self.coordinator.command(
            self.device_id,
            swing_parameters(
                self.value("parameters") or {}, "airSwingLR", HORIZONTAL, swing_horizontal_mode
            ),
        )

    @property
    def hvac_modes(self):
        modes = [HVACMode.OFF]
        for mode, flag in FLAGS.items():
            if self.feature(flag) or self.value("parameters.operationMode") == MODES[mode]:
                modes.append(mode)
        return modes

    @property
    def hvac_mode(self):
        operate = self.value("parameters.operate")
        if operate == 0:
            return HVACMode.OFF
        if operate != 1:
            return None
        code = self.value("parameters.operationMode")
        return next((mode for mode, value in MODES.items() if value == code), None)

    @property
    def hvac_action(self):
        # Operation mode does not prove that the compressor is running.
        return HVACAction.OFF if self.hvac_mode == HVACMode.OFF else None

    @property
    def current_temperature(self):
        return numeric(self.value("parameters.insideTemperature"), temperature=True)

    @property
    def target_temperature(self):
        return numeric(self.value("parameters.temperatureSet"), temperature=True)

    @property
    def fan_modes(self):
        return list(FANS)

    @property
    def fan_mode(self):
        return next(
            (name for name, value in FANS.items() if value == self.value("parameters.fanSpeed")),
            None,
        )

    @property
    def preset_modes(self):
        return (
            ["none"]
            + (["powerful"] if self.feature("powerfulMode") else [])
            + (["quiet"] if self.feature("quietMode") else [])
        )

    @property
    def preset_mode(self):
        return next(
            (name for name, value in PRESETS.items() if value == self.value("parameters.ecoMode")),
            None,
        )

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode not in self.hvac_modes:
            raise HomeAssistantError("This unit does not report support for that mode")
        parameters = (
            {"operate": 0}
            if hvac_mode == HVACMode.OFF
            else {"operate": 1, "operationMode": MODES[hvac_mode]}
        )
        await self.coordinator.command(self.device_id, parameters)

    async def async_set_temperature(self, **kwargs):
        value = kwargs.get(ATTR_TEMPERATURE)
        if (
            numeric(value, temperature=True) is None
            or not self.min_temp <= value <= self.max_temp
            or value * 2 != round(value * 2)
        ):
            raise HomeAssistantError("Target temperature must be 16–30 °C in 0.5 °C steps")
        parameters = {"temperatureSet": value}
        mode = kwargs.get("hvac_mode")
        if mode is not None:
            if mode not in self.hvac_modes or mode == HVACMode.OFF:
                raise HomeAssistantError("Choose a supported running mode with a temperature")
            parameters.update(operate=1, operationMode=MODES[mode])
        elif self.hvac_mode == HVACMode.OFF:
            raise HomeAssistantError("Turn the unit on explicitly before changing its setpoint")
        await self.coordinator.command(self.device_id, parameters)

    async def async_set_fan_mode(self, fan_mode):
        if fan_mode not in FANS:
            raise HomeAssistantError("Unsupported fan mode")
        if self.hvac_mode in {None, HVACMode.OFF}:
            raise HomeAssistantError("Turn the unit on explicitly before changing fan speed")
        await self.coordinator.command(self.device_id, {"fanSpeed": FANS[fan_mode]})

    async def async_set_preset_mode(self, preset_mode):
        if preset_mode not in self.preset_modes:
            raise HomeAssistantError("Unsupported preset")
        if self.hvac_mode in {None, HVACMode.OFF}:
            raise HomeAssistantError("Turn the unit on explicitly before changing presets")
        await self.coordinator.command(self.device_id, {"ecoMode": PRESETS[preset_mode]})

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self):
        code = self.value("parameters.operationMode")
        if code not in MODES.values():
            raise HomeAssistantError("Select a known operating mode first")
        await self.coordinator.command(self.device_id, {"operate": 1})
