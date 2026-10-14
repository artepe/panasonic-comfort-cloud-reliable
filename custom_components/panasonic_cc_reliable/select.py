"""Independent vertical and horizontal vane selection."""

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_ENABLE_CONTROL
from .entity import ComfortCloudEntity, add_dynamic_entities

PARALLEL_UPDATES = 1
VERTICAL = {"auto": -1, "up": 0, "up_mid": 3, "mid": 2, "down_mid": 4, "down": 1, "swing": 5}
HORIZONTAL = {"auto": -1, "left": 1, "left_mid": 5, "mid": 2, "right_mid": 4, "right": 0}


def selected_swing(parameters, field, choices):
    auto = parameters.get("fanAutoMode")
    if auto == 0 or auto == (3 if field == "airSwingLR" else 2):
        return "auto"
    return next((key for key, value in choices.items() if value == parameters.get(field)), None)


def swing_parameters(parameters, field, choices, option):
    if option not in choices:
        raise HomeAssistantError("Unsupported swing option")
    if parameters.get("operate") != 1:
        raise HomeAssistantError("Turn the unit on explicitly before changing swing")
    if parameters.get("fanAutoMode") not in {0, 1, 2, 3}:
        raise HomeAssistantError("Current swing auto mode is unknown; refresh status first")
    other_auto = parameters["fanAutoMode"] in (0, 2 if field == "airSwingLR" else 3)
    this_auto = option == "auto"
    lr_auto = this_auto if field == "airSwingLR" else other_auto
    ud_auto = this_auto if field == "airSwingUD" else other_auto
    command = {"fanAutoMode": 0 if lr_auto and ud_auto else 3 if lr_auto else 2 if ud_auto else 1}
    if not this_auto:
        command[field] = choices[option]
    return command


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.coordinator

    def factory(device_id):
        device = coordinator.devices[device_id]
        raw = coordinator.snapshots[device_id].raw
        if not coordinator.options[CONF_ENABLE_CONTROL] or device.kind != "ac":
            return
        if raw.get("airSwingLR", device.listing.get("airSwingLR", False)):
            yield SwingSelect(coordinator, device_id, "airSwingLR", HORIZONTAL, "Horizontal swing")
        if "airSwingUD" in raw.get("parameters", {}):
            options = dict(VERTICAL)
            if not raw.get("autoSwingUD", device.listing.get("autoSwingUD", False)):
                options.pop("swing")
            yield SwingSelect(coordinator, device_id, "airSwingUD", options, "Vertical swing")

    add_dynamic_entities(entry, coordinator, async_add_entities, factory)


class SwingSelect(ComfortCloudEntity, SelectEntity):
    def __init__(self, coordinator, device_id, field, choices, name):
        super().__init__(coordinator, device_id, field)
        self.field = field
        self.choices = choices
        self._attr_options = list(choices)
        self._attr_name = name

    @property
    def current_option(self):
        return selected_swing(self.value("parameters") or {}, self.field, self.choices)

    async def async_select_option(self, option):
        parameters = swing_parameters(
            self.value("parameters") or {}, self.field, self.choices, option
        )
        await self.coordinator.command(self.device_id, parameters)
