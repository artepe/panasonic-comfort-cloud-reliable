"""Energy transport must use configured-zone offsets, including DST."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.panasonic_cc_reliable.api import ComfortCloudClient, comfort_cloud_timezone
from custom_components.panasonic_cc_reliable.coordinator import ComfortCloudCoordinator
from custom_components.panasonic_cc_reliable.errors import ProtocolError


@pytest.mark.parametrize(
    "zone,date,expected",
    [
        ("Europe/Helsinki", "2026-10-14T10:00:00", "+03:00"),
        ("Europe/Helsinki", "2026-12-14T10:00:00", "+02:00"),
        ("Europe/Helsinki", "2026-10-25T00:59:00", "+03:00"),
        ("Europe/Helsinki", "2026-10-25T01:01:00", "+02:00"),
        ("Asia/Kathmandu", "2026-12-14T10:00:00", "+05:45"),
        ("America/St_Johns", "2026-12-14T10:00:00", "-03:30"),
        ("UTC", "2026-12-14T10:00:00", "+00:00"),
    ],
)
def test_offset_is_derived_from_account_zone_not_server_zone(zone, date, expected):
    assert (
        comfort_cloud_timezone(zone, datetime.fromisoformat(date).replace(tzinfo=UTC)) == expected
    )


def test_invalid_zone_is_not_silently_converted_to_utc():
    with pytest.raises(ProtocolError):
        comfort_cloud_timezone("invalid-zone")
    assert comfort_cloud_timezone("+03:00") == "+03:00"


async def test_history_request_sends_offset_on_the_wire(ac_device):
    api = ComfortCloudClient(SimpleNamespace(cookie_jar=object()), "4.4.0")
    api.request = AsyncMock(return_value={"historyDataList": []})
    await api.energy(ac_device, "20261014", "Asia/Kathmandu")
    payload = api.request.call_args.args[2]
    assert payload["osTimezone"] == "+05:45"
    assert payload["dataMode"] == 2
    assert payload["date"] == "20261014"


async def test_numeric_history_day_is_read_and_diagnosed(hass, entry, ac_device):
    api = AsyncMock()
    day = dt_util.now().strftime("%Y%m%d")
    api.energy.return_value = {"historyDataList": [{"dataTime": int(day), "consumption": 0}]}
    coordinator = ComfortCloudCoordinator(hass, entry, api)
    await coordinator._update_energy(ac_device)
    energy = coordinator.energy[ac_device.id]
    assert energy["consumption"] == 0
    assert energy["returned_dates"] == [day]
    assert energy["timezone_offset"] in {"+02:00", "+03:00"}
    assert energy["last_attempt"] is not None
    await coordinator.async_shutdown()
