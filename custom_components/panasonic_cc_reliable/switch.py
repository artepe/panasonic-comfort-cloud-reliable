"""Nanoe controls only on units reporting a compatible on/off enum."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_ENABLE_CONTROL
from .entity import ComfortCloudEntity, add_dynamic_entities

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.coordinator

    def factory(device_id):
        device = coordinator.devices[device_id]
        raw = coordinator.snapshots[device_id].raw
        if (
            coordinator.options[CONF_ENABLE_CONTROL]
            and device.kind == "ac"
            and raw.get("nanoe", False)
            and raw.get("parameters", {}).get("nanoe") in {1, 2}
        ):
            yield NanoeSwitch(coordinator, device_id)

    add_dynamic_entities(entry, coordinator, async_add_entities, factory)


class NanoeSwitch(ComfortCloudEntity, SwitchEntity):
    _attr_name = "Nanoe"

    def __init__(self, coordinator, device_id):
        super().__init__(coordinator, device_id, "nanoe")

    @property
    def available(self):
        return super().available and self.value("parameters.nanoe") in {1, 2}

    @property
    def is_on(self):
        return self.value("parameters.nanoe") == 2

    async def _set(self, value):
        if self.value("parameters.operate") != 1:
            raise HomeAssistantError("Turn the unit on explicitly before changing Nanoe")
        await self.coordinator.command(self.device_id, {"nanoe": value})

    async def async_turn_on(self, **kwargs):
        await self._set(2)

    async def async_turn_off(self, **kwargs):
        await self._set(1)
