"""Shared entities and dynamic discovery without per-entity network calls."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ComfortCloudCoordinator
from .models import get_path


class ComfortCloudEntity(CoordinatorEntity[ComfortCloudCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator, device_id: str, key: str):
        super().__init__(coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        device = coordinator.devices[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="Panasonic",
            model=device.model,
            name=device.name,
        )

    @property
    def snapshot(self):
        return self.coordinator.snapshots[self.device_id]

    @property
    def available(self):
        return self.device_id in self.coordinator.devices and self.coordinator.usable(
            self.device_id
        )

    def value(self, path: str):
        return get_path(self.snapshot.raw, path)

    @property
    def extra_state_attributes(self):
        return {
            "data_source": self.snapshot.source,
            "last_success": self.snapshot.last_success,
            "consecutive_failures": self.snapshot.failures,
        }


def add_dynamic_entities(entry, coordinator, async_add_entities, factory):
    """Detect devices and optional fields on every coordinator update."""
    added = set()

    def discover():
        entities = []
        for device_id in coordinator.devices:
            for entity in factory(device_id):
                if entity.unique_id not in added:
                    added.add(entity.unique_id)
                    entities.append(entity)
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))
