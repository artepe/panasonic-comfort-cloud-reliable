"""Smoke-test the real HA loader, entity platforms and unload path."""

from unittest.mock import AsyncMock, patch

from homeassistant import loader
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import area_registry, device_registry, entity_registry

from custom_components.panasonic_cc_reliable.const import DOMAIN


async def test_loads_in_home_assistant_2026_10_and_unloads(hass, entry, ac_device, ac_status):
    hass.config.skip_pip = True
    loader.async_setup(hass)
    device_registry.async_setup(hass)
    await area_registry.async_load(hass)
    await device_registry.async_load(hass)
    await entity_registry.async_load(hass)
    client = AsyncMock()
    client.devices.return_value = [ac_device]
    client.status.return_value = (ac_status, "live")
    with patch("custom_components.panasonic_cc_reliable.ComfortCloudClient", return_value=client):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.LOADED
    states = hass.states.async_all()
    assert any(state.entity_id.startswith("climate.") and state.state == "heat" for state in states)
    assert any(
        state.state == "21.0" and state.attributes.get("device_class") == "temperature"
        for state in states
    )
    assert entry.runtime_data.coordinator.devices[ac_device.id].kind == "ac"
    session = entry.runtime_data.session
    created_ids = {state.entity_id for state in states}
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert session.closed
    assert entry.state == ConfigEntryState.NOT_LOADED
    assert all(
        (state := hass.states.get(entity_id)) is None or state.state == "unavailable"
        for entity_id in created_ids
    )
    flow_result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow_result["step_id"] == "user"
    hass.config_entries.flow.async_abort(flow_result["flow_id"])
