"""Panasonic Comfort Cloud Reliable custom integration."""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .api import ComfortCloudClient
from .const import CONF_APP_VERSION, DEFAULTS, DOMAIN
from .coordinator import ComfortCloudCoordinator

PLATFORMS = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.BUTTON,
]


@dataclass
class RuntimeData:
    coordinator: ComfortCloudCoordinator
    session: aiohttp.ClientSession
    store: Store


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = Store(
        hass, 1, f"{DOMAIN}.{entry.data['account_id']}.tokens", private=True, atomic_writes=True
    )
    tokens = await store.async_load()
    # This account owns its cookie jar; do not reuse another account's login.
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
    client = ComfortCloudClient(
        session,
        entry.options.get(CONF_APP_VERSION, DEFAULTS[CONF_APP_VERSION]),
        tokens,
        store.async_save,
    )
    coordinator = ComfortCloudCoordinator(hass, entry, client)
    entry.runtime_data = RuntimeData(coordinator, session, store)
    try:
        await coordinator.async_config_entry_first_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await session.close()
        raise
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.session.close()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry):
    await Store(
        hass, 1, f"{DOMAIN}.{entry.data['account_id']}.tokens", private=True, atomic_writes=True
    ).async_remove()
