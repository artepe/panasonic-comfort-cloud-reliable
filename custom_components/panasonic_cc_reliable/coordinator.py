"""Isolate individual devices while sharing the account's request budget."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ComfortCloudClient, comfort_cloud_timezone
from .const import (
    CONF_ENABLE_CONTROL,
    CONF_ENABLE_ENERGY,
    CONF_ENERGY_INTERVAL,
    CONF_POLL_INTERVAL,
    CONF_STALE_AFTER,
    DEFAULTS,
    DOMAIN,
    MAX_BACKOFF,
)
from .errors import ApiError, AuthenticationError, ProtocolError, RateLimitError
from .models import Device, Snapshot, numeric, validate_status

_LOGGER = logging.getLogger(__name__)


class ComfortCloudCoordinator(DataUpdateCoordinator[dict[str, Snapshot]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ComfortCloudClient):
        self.options = {**DEFAULTS, **entry.options}
        self.client = client
        self.devices: dict[str, Device] = {}
        self.snapshots: dict[str, Snapshot] = {}
        self.energy: dict[str, dict] = {}
        self._energy_due: dict[str, float] = {}
        self._discovery_due = 0.0
        self._cycle_lock = asyncio.Lock()
        self.account_error: str | None = None
        self._base_interval = self.options[CONF_POLL_INTERVAL]
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=self._base_interval),
            always_update=True,
        )

    @property
    def stale_after(self):
        return self.options[CONF_STALE_AFTER]

    def usable(self, device_id: str) -> bool:
        snapshot = self.snapshots.get(device_id)
        return snapshot is not None and snapshot.usable(self.stale_after)

    async def _discover(self):
        devices = await self.client.devices()
        if not devices:
            raise ProtocolError("No Comfort Cloud devices on this account")
        self.devices = {device.id: device for device in devices}
        # Keep removed devices' last snapshots, but entities become unavailable
        # immediately through the device-membership check in the entity base.
        for device in devices:
            self.snapshots.setdefault(device.id, Snapshot())
        self._discovery_due = time.monotonic() + 3600

    async def _async_update_data(self):
        async with self._cycle_lock:
            try:
                return await self._update_account()
            except AuthenticationError as err:
                raise ConfigEntryAuthFailed("Sign in again to Panasonic Comfort Cloud") from err
            except RateLimitError as err:
                self.account_error = str(err)
                self.update_interval = timedelta(seconds=max(self._base_interval, err.retry_after))
                raise UpdateFailed(
                    str(err), retry_after=max(self._base_interval, err.retry_after)
                ) from err
            except ApiError as err:
                raise UpdateFailed(str(err)) from err

    async def _update_account(self):
        self.account_error = None
        self.update_interval = timedelta(seconds=self._base_interval)
        has_hws = any(device.kind == "hws" for device in self.devices.values())
        if not self.devices or time.monotonic() >= self._discovery_due or has_hws:
            try:
                await self._discover()
            except AuthenticationError, RateLimitError:
                raise
            except ApiError as err:
                self.account_error = str(err)
                if not self.devices:
                    raise
        for device in tuple(self.devices.values()):
            snapshot = self.snapshots[device.id]
            if time.monotonic() < snapshot.next_poll:
                continue
            try:
                if device.kind == "hws":
                    # One account-wide group request already updated every HWS.
                    if self.account_error:
                        raise ProtocolError("Group listing refresh failed")
                    raw, source = validate_status(device, device.listing), "group_listing"
                else:
                    raw, source = await self.client.status(device)
                snapshot.success(raw, source)
                snapshot.next_poll = time.monotonic() + self._base_interval * 0.8
            except AuthenticationError:
                raise
            except ApiError as err:
                snapshot.failures += 1
                snapshot.error = str(err)
                pause = min(MAX_BACKOFF, self._base_interval * 2 ** min(snapshot.failures, 8))
                snapshot.next_poll = (
                    time.monotonic() + pause + random.uniform(0, min(30, pause * 0.1))
                )
                if isinstance(err, RateLimitError):
                    self.account_error = str(err)
                    self.update_interval = timedelta(
                        seconds=max(self._base_interval, err.retry_after)
                    )
                    break
                continue
            if (
                self.options[CONF_ENABLE_ENERGY]
                and device.kind == "ac"
                and time.monotonic() >= self._energy_due.get(device.id, 0)
            ):
                try:
                    await self._update_energy(device)
                except AuthenticationError:
                    raise
                except RateLimitError as err:
                    self.account_error = str(err)
                    self.update_interval = timedelta(
                        seconds=max(self._base_interval, err.retry_after)
                    )
                    break
                except ApiError as err:
                    # History failure never makes climate/status unavailable.
                    record = self.energy.setdefault(device.id, {})
                    record["error"] = str(err)
                    record["http_status"] = err.status or None
                    record["error_code"] = err.code if isinstance(err.code, int) else None
                finally:
                    self._energy_due[device.id] = (
                        time.monotonic() + self.options[CONF_ENERGY_INTERVAL]
                    )
        if not any(item.raw for item in self.snapshots.values()):
            raise ProtocolError("No readable device status yet; Home Assistant will retry")
        return self.snapshots

    async def _update_energy(self, device: Device):
        day = dt_util.now().strftime("%Y%m%d")
        record = self.energy.setdefault(device.id, {})
        record.update(
            last_attempt=dt_util.utcnow(),
            requested_date=day,
            timezone_offset=comfort_cloud_timezone(self.hass.config.time_zone),
            returned_dates=[],
            history_count=None,
        )
        raw = await self.client.energy(device, day, self.hass.config.time_zone)
        rows = raw.get("historyDataList")
        if not isinstance(rows, list):
            raise ProtocolError("Cloud returned no valid energy history")
        record["history_count"] = len(rows)
        # Keep only valid day identifiers, never whole response bodies or tokens.
        record["returned_dates"] = [
            key
            for item in rows
            if isinstance(item, dict) and (key := _history_day(item.get("dataTime"))) is not None
        ][:32]
        row = next(
            (
                item
                for item in rows
                if isinstance(item, dict) and _history_day(item.get("dataTime")) == day
            ),
            None,
        )
        consumption = numeric(row.get("consumption")) if row else None
        if consumption is None or consumption < 0:
            raise ProtocolError("Today's energy is not available yet")
        rates = {
            name: numeric(row.get(field))
            for name, field in (
                ("heating", "heatConsumptionRate"),
                ("cooling", "coolConsumptionRate"),
            )
        }
        valid_rates = {
            name: rate for name, rate in rates.items() if rate is not None and 0 <= rate <= 1
        }
        if sum(valid_rates.values()) > 1.001:
            valid_rates = {}
        self.energy[device.id] = {
            **record,
            "date": day,
            "consumption": consumption,
            "last_success": dt_util.utcnow(),
            "error": None,
            "http_status": None,
            "error_code": None,
            "heating_consumption": consumption * valid_rates["heating"]
            if "heating" in valid_rates
            else None,
            "cooling_consumption": consumption * valid_rates["cooling"]
            if "cooling" in valid_rates
            else None,
            "heating_rate": valid_rates.get("heating"),
            "cooling_rate": valid_rates.get("cooling"),
        }

    async def command(self, device_id: str, parameters: dict):
        async with self._cycle_lock:
            if not self.options[CONF_ENABLE_CONTROL]:
                raise HomeAssistantError("Enable AC controls in integration options first")
            if device_id not in self.devices or not self.usable(device_id):
                raise HomeAssistantError("Device status is too old to control; refresh it first")
            if self.snapshots[device_id].source != "live":
                raise HomeAssistantError("Controls require a live device response")
            try:
                await self.client.control(self.devices[device_id], parameters)
            except AuthenticationError as err:
                self.config_entry.async_start_reauth(self.hass)
                raise HomeAssistantError("Sign in again to Panasonic Comfort Cloud") from err
            except ApiError as err:
                raise HomeAssistantError(str(err)) from err
            self.snapshots[device_id].next_poll = 0
        # Report only the subsequent server state, never a guessed local value.
        await self.async_request_refresh()


def _history_day(value):
    """Accept a day identifier serialized as a string or JSON integer."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    key = str(value).strip()
    if len(key) != 8 or not key.isdigit():
        return None
    return key
