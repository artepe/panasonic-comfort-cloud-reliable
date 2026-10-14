"""Synthetic fixtures; no real account, device GUID or network access."""

from types import MappingProxyType

import pytest
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.panasonic_cc_reliable.const import DEFAULTS, DOMAIN
from custom_components.panasonic_cc_reliable.models import Device


@pytest.fixture
def ac_device():
    return Device(
        "synthetic/ac",
        "Test AC",
        "Test model",
        "ac",
        {
            "deviceGuid": "synthetic/ac",
            "deviceName": "Test AC",
            "deviceType": "1",
            "parameters": {"operate": 1},
        },
    )


@pytest.fixture
def ac_status():
    return {
        "heatMode": True,
        "coolMode": True,
        "fanMode": True,
        "quietMode": True,
        "powerfulMode": True,
        "nanoe": True,
        "airSwingLR": True,
        "parameters": {
            "operate": 1,
            "operationMode": 3,
            "temperatureSet": 22.5,
            "insideTemperature": 21,
            "outTemperature": 5,
            "fanSpeed": 0,
            "ecoMode": 0,
            "nanoe": 1,
            "fanAutoMode": 0,
            "airSwingUD": 2,
            "airSwingLR": 2,
        },
    }


@pytest.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    instance.config_entries = ConfigEntries(instance, {})
    await instance.config.async_set_time_zone("Europe/Helsinki")
    yield instance
    await instance.async_block_till_done()
    await instance.async_stop(force=True)


@pytest.fixture
def entry():
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Synthetic account",
        data={"account_id": "test-account"},
        options=dict(DEFAULTS),
        source="user",
        unique_id="test-account",
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
