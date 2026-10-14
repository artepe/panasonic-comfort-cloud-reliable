"""A refresh button that respects the account cooldown and device backoff."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .entity import ComfortCloudEntity, add_dynamic_entities

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.coordinator
    add_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda device_id: [RefreshButton(coordinator, device_id)],
    )


class RefreshButton(ComfortCloudEntity, ButtonEntity):
    _attr_name = "Refresh status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator, device_id):
        super().__init__(coordinator, device_id, "refresh")

    @property
    def available(self):
        return True

    async def async_press(self):
        await self.coordinator.async_request_refresh()
