"""Don't invent readings, trust expired tokens or hide cache age."""

import base64
import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.panasonic_cc_reliable.errors import ProtocolError
from custom_components.panasonic_cc_reliable.models import (
    Snapshot,
    discover,
    numeric,
    raw_numeric_paths,
    redact,
    validate_status,
)
from custom_components.panasonic_cc_reliable.vendor.panasonicsettings import PanasonicSettings


def token(exp):
    part = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return "header." + part + ".signature"


def test_expired_jwt_not_masked_by_future_local_expiry():
    settings = PanasonicSettings(
        {"access_token": token(time.time() - 1), "expires_at": time.time() + 3600}
    )
    assert not settings.is_access_token_valid


def test_expired_local_expiry_not_masked_by_future_jwt():
    settings = PanasonicSettings(
        {"access_token": token(time.time() + 3600), "expires_at": time.time() - 1}
    )
    assert not settings.is_access_token_valid


def test_token_refreshes_before_expiry_and_handles_non_jwt_tokens():
    assert not PanasonicSettings({"access_token": token(time.time() + 10)}).is_access_token_valid
    assert PanasonicSettings(
        {"access_token": "opaque", "expires_at": time.time() + 3600}
    ).is_access_token_valid
    assert not PanasonicSettings({"access_token": "opaque"}).is_access_token_valid


@pytest.mark.parametrize("value", [-255, 126, 255, float("nan"), float("inf"), None, "21", True])
def test_missing_temperature_is_not_a_reading(value):
    assert numeric(value, temperature=True) is None


def test_real_zero_and_energy_255_are_preserved():
    assert numeric(0, temperature=True) == 0
    assert numeric(255) == 255


def test_one_empty_status_cannot_clear_previous_snapshot(ac_device, ac_status):
    snapshot = Snapshot()
    snapshot.success(ac_status, "live")
    with pytest.raises(ProtocolError):
        validate_status(ac_device, {})
    assert snapshot.raw == ac_status


def test_old_live_status_expires(ac_status):
    snapshot = Snapshot(
        raw=ac_status, source="live", last_success=datetime.now(UTC) - timedelta(seconds=601)
    )
    assert not snapshot.usable(600)


def test_cached_status_needs_recent_source_timestamp(ac_status):
    snapshot = Snapshot()
    snapshot.success(ac_status, "cached")
    assert not snapshot.usable(600)
    snapshot.raw["timestamp"] = int(time.time() * 1000)
    assert snapshot.usable(600)
    snapshot.raw["timestamp"] = int((time.time() - 3600) * 1000)
    assert not snapshot.usable(600)


def test_discovery_includes_hws_aquarea_unknown_and_deduplicates():
    rows = [
        {"deviceGuid": "a", "deviceType": "1", "parameters": {"operate": 1}},
        {"deviceGuid": "b", "deviceType": "2"},
        {"deviceGuid": "c", "deviceType": "11", "parameters": {"tankTemperature": 50}},
        {"deviceGuid": "d", "deviceType": "99"},
    ]
    devices = discover({"groupList": [{"deviceList": rows}, {"deviceIdList": rows}]})
    assert [device.kind for device in devices] == ["ac", "aquarea", "hws", "unknown"]


def test_redaction_is_recursive():
    result = redact(
        {
            "access_token": "PRIVATE",
            "deviceGuid": "PRIVATE",
            "deviceName": "PRIVATE",
            "parameters": {"insideTemperature": 21, "email": "PRIVATE"},
            "zones": [{"zoneName": "PRIVATE"}],
            "message": "Bearer PRIVATE",
        }
    )
    assert "PRIVATE" not in json.dumps(result)
    assert result["parameters"]["insideTemperature"] == 21


def test_raw_fields_exclude_private_data():
    result = raw_numeric_paths(
        {"temperature": 21, "clientId": 234, "secret": 45, "nested": {"fanSpeed": 0}}
    )
    assert result == ["temperature", "nested.fanSpeed"]
