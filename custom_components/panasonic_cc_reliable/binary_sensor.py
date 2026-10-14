"""Freshness and directly reported Aquarea flags."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory

from .entity import ComfortCloudEntity, add_dynamic_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.coordinator

    def factory(device_id):
        yield FreshStatusSensor(coordinator, device_id)
        if coordinator.devices[device_id].kind == "ac":
            if "operate" in coordinator.snapshots[device_id].raw.get("parameters", {}):
                yield ACPowerSensor(coordinator, device_id)
        if coordinator.devices[device_id].kind == "aquarea":
            for key, name, field in (
                ("defrost", "Defrost", "deiceStatus"),
                ("force_dhw", "Forced hot water", "forceDHW"),
                ("force_heater", "Forced backup heater", "forceHeater"),
                ("pump_duty", "Pump enabled", "pumpDuty"),
            ):
                if field in coordinator.snapshots[device_id].raw.get("status", {}):
                    yield AquareaFlagSensor(coordinator, device_id, key, name, field)

    add_dynamic_entities(entry, coordinator, async_add_entities, factory)


class FreshStatusSensor(ComfortCloudEntity, BinarySensorEntity):
    _attr_name = "Status fresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, device_id):
        super().__init__(coordinator, device_id, "status_fresh")

    @property
    def available(self):
        return True

    @property
    def is_on(self):
        return (
            self.device_id in self.coordinator.devices
            and self.coordinator.usable(self.device_id)
            and self.coordinator.last_update_success
        )


class ACPowerSensor(ComfortCloudEntity, BinarySensorEntity):
    _attr_name = "Unit switched on"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator, device_id):
        super().__init__(coordinator, device_id, "unit_on")

    @property
    def is_on(self):
        value = self.value("parameters.operate")
        return value == 1 if value in {0, 1} else None


class AquareaFlagSensor(ComfortCloudEntity, BinarySensorEntity):
    def __init__(self, coordinator, device_id, key, name, field):
        super().__init__(coordinator, device_id, key)
        self.field = field
        self._attr_name = name
        self._attr_icon = "mdi:snowflake-melt" if key == "defrost" else "mdi:information-outline"

    @property
    def is_on(self):
        value = self.value("status." + self.field)
        return value == 1 if value in {0, 1} else None
