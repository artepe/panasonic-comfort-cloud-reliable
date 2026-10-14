"""Real cloud fields and explicit connection/freshness diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.util import dt as dt_util

from .const import CONF_ENABLE_ENERGY, CONF_ENERGY_INTERVAL, CONF_RAW_SENSORS
from .entity import ComfortCloudEntity, add_dynamic_entities
from .models import get_path, numeric, raw_numeric_paths, source_timestamp

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class FieldDescription(SensorEntityDescription):
    path: str
    explanation: str
    value_map: dict | None = None


def temperature(key, name, path, explanation):
    return FieldDescription(
        key=key,
        name=name,
        path=path,
        explanation=explanation,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    )


AC_FIELDS = (
    FieldDescription(
        key="operation_mode",
        name="Operating mode",
        path="parameters.operationMode",
        explanation="Selected operating mode; this does not prove compressor activity.",
        value_map={0: "auto", 1: "dry", 2: "cool", 3: "heat", 4: "fan"},
    ),
    FieldDescription(
        key="fan_speed",
        name="Fan speed",
        path="parameters.fanSpeed",
        explanation="Reported fan setting, not measured fan RPM.",
        value_map={0: "auto", 1: "low", 2: "low_mid", 3: "mid", 4: "high_mid", 5: "high"},
    ),
    FieldDescription(
        key="preset",
        name="Comfort preset",
        path="parameters.ecoMode",
        explanation="Reported normal, powerful or quiet setting.",
        value_map={0: "normal", 1: "powerful", 2: "quiet"},
    ),
    temperature(
        "inside_temperature",
        "Indoor temperature",
        "parameters.insideTemperature",
        "Indoor temperature reported by the heat pump, not a room-average estimate.",
    ),
    temperature(
        "outside_temperature",
        "Outdoor temperature",
        "parameters.outTemperature",
        "Outdoor temperature reported by the unit; unsupported sentinel values are ignored.",
    ),
    temperature(
        "target_temperature",
        "Target temperature",
        "parameters.temperatureSet",
        "The setpoint confirmed by the cloud, not an optimistic command value.",
    ),
    FieldDescription(
        key="air_quality",
        name="Air quality code",
        path="parameters.airQuality",
        explanation="Raw Panasonic air quality code. Its meaning is model dependent.",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)
AQUAREA_FIELDS = (
    temperature(
        "outside_temperature",
        "Outdoor temperature",
        "status.outdoorNow",
        "Outdoor temperature reported by the Aquarea controller.",
    ),
    temperature(
        "tank_temperature",
        "Hot water temperature",
        "status.tankStatus.temperatureNow",
        "Actual hot water tank temperature reported by the controller.",
    ),
    temperature(
        "tank_target",
        "Hot water target",
        "status.tankStatus.heatSet",
        "Configured hot water tank heating setpoint.",
    ),
    FieldDescription(
        key="operation_mode",
        name="Operation mode code",
        path="status.operationMode",
        explanation="Raw Aquarea reported operation mode; read and write codes are different.",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    FieldDescription(
        key="quiet_mode",
        name="Quiet level",
        path="status.quietMode",
        explanation="Reported quiet mode level: 0 is off; other values are device dependent.",
    ),
    FieldDescription(
        key="water_pressure_raw",
        name="Water pressure raw",
        path="status.waterPressure",
        explanation="Unscaled cloud field. Units have not been verified, so no pressure unit is assigned.",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)
HWS_FIELDS = (
    temperature(
        "tank_target",
        "Tank setpoint",
        "parameters.tankTemperature",
        "The tank setpoint from the group listing; it is not assumed to be the measured tank temperature.",
    ),
    FieldDescription(
        key="boost",
        name="Boost mode code",
        path="parameters.boostMode",
        explanation="Boost mode reported by the standalone hot water appliance.",
    ),
    FieldDescription(
        key="operation_mode",
        name="Operation mode code",
        path="parameters.operationMode",
        explanation="The appliance's raw operating mode from the group listing.",
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.coordinator

    def factory(device_id):
        device = coordinator.devices[device_id]
        raw = coordinator.snapshots[device_id].raw
        fields = (
            AC_FIELDS
            if device.kind == "ac"
            else AQUAREA_FIELDS
            if device.kind == "aquarea"
            else HWS_FIELDS
            if device.kind == "hws"
            else ()
        )
        for description in fields:
            if get_path(raw, description.path) is not None:
                yield CloudFieldSensor(coordinator, device_id, description)
        if device.kind == "aquarea":
            zones = get_path(raw, "status.zoneStatus") or []
            for index, zone in enumerate(zones):
                if not isinstance(zone, dict):
                    continue
                zone_id = zone.get("zoneId", index + 1)
                for suffix, name, field in (
                    ("temperature", "Temperature", "temperatureNow"),
                    ("heat_setpoint", "Heating target", "heatSet"),
                    ("cool_setpoint", "Cooling target", "coolSet"),
                ):
                    if field in zone:
                        description = temperature(
                            f"zone_{zone_id}_{suffix}",
                            f"Zone {zone_id} {name.lower()}",
                            f"status.zoneStatus.{index}.{field}",
                            "Cloud-reported zone value. Zone sensor configuration determines whether it represents room or water temperature.",
                        )
                        yield CloudFieldSensor(
                            coordinator, device_id, description, zone_id=zone_id, zone_field=field
                        )
        for key, name in (
            ("connection", "Connection status"),
            ("data_source", "Data source"),
            ("age", "Time since successful fetch"),
            ("last_success", "Last successful fetch"),
            ("source_timestamp", "Cloud timestamp"),
            ("failures", "Consecutive failures"),
            ("last_error", "Last communication error"),
        ):
            yield ConnectionSensor(coordinator, device_id, key, name)
        if coordinator.options[CONF_ENABLE_ENERGY] and device.kind == "ac":
            yield DailyEnergySensor(coordinator, device_id)
            yield DailyEnergySensor(
                coordinator, device_id, "heating_consumption", "Heating electricity today"
            )
            yield DailyEnergySensor(
                coordinator, device_id, "cooling_consumption", "Cooling electricity today"
            )
        if coordinator.options[CONF_RAW_SENSORS]:
            root = "status" if device.kind == "aquarea" else "parameters"
            for path in raw_numeric_paths(raw.get(root, {}), root):
                # Unmapped fields get no guessed unit or engineering meaning.
                if path not in {item.path for item in fields}:
                    yield RawFieldSensor(coordinator, device_id, path)

    add_dynamic_entities(entry, coordinator, async_add_entities, factory)


class CloudFieldSensor(ComfortCloudEntity, SensorEntity):
    def __init__(self, coordinator, device_id, description, zone_id=None, zone_field=None):
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description
        self.zone_id = zone_id
        self.zone_field = zone_field

    @property
    def native_value(self):
        if self.zone_id is not None:
            zones = self.value("status.zoneStatus") or []
            zone = next(
                (
                    item
                    for item in zones
                    if isinstance(item, dict) and item.get("zoneId") == self.zone_id
                ),
                {},
            )
            value = zone.get(self.zone_field)
        else:
            value = self.value(self.entity_description.path)
        if self.entity_description.value_map is not None:
            return self.entity_description.value_map.get(value)
        return numeric(
            value, temperature=self.entity_description.device_class == SensorDeviceClass.TEMPERATURE
        )

    @property
    def extra_state_attributes(self):
        return {
            **super().extra_state_attributes,
            "description": self.entity_description.explanation,
            "cloud_field": self.entity_description.path,
        }


class RawFieldSensor(CloudFieldSensor):
    def __init__(self, coordinator, device_id, path):
        description = FieldDescription(
            key="raw_" + path.replace(".", "_"),
            name="Raw " + path.split(".", 1)[-1],
            path=path,
            explanation="Unmapped numeric API field. No unit, scale or physical meaning has been assumed.",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        )
        super().__init__(coordinator, device_id, description)


class ConnectionSensor(ComfortCloudEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id, key, name):
        super().__init__(coordinator, device_id, key)
        self.key = key
        self._attr_name = name
        if key == "age":
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
            self._attr_device_class = SensorDeviceClass.DURATION
        if key in {"last_success", "source_timestamp"}:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        snapshot = self.snapshot
        if self.key == "connection":
            if self.device_id not in self.coordinator.devices:
                return "removed"
            if not self.coordinator.last_update_success:
                return "account_error"
            if self.coordinator.account_error:
                return "account_degraded"
            if not snapshot.usable(self.coordinator.stale_after):
                return "stale"
            return "degraded" if snapshot.failures or snapshot.source == "cached" else "connected"
        if self.key == "data_source":
            return snapshot.source
        if self.key == "age":
            return round(snapshot.age()) if snapshot.age() is not None else None
        if self.key == "last_success":
            return snapshot.last_success
        if self.key == "source_timestamp":
            return source_timestamp(snapshot.raw)
        if self.key == "failures":
            return snapshot.failures
        if self.key == "last_error":
            return snapshot.error or self.coordinator.account_error or "none"
        return None


class DailyEnergySensor(ComfortCloudEntity, SensorEntity):
    _attr_name = "Energy today"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator, device_id, field="consumption", name="Energy today"):
        super().__init__(
            coordinator,
            device_id,
            "energy_today" if field == "consumption" else "energy_today_" + field,
        )
        self.field = field
        self._attr_name = name

    @property
    def available(self):
        data = self.coordinator.energy.get(self.device_id, {})
        stamp = data.get("last_success")
        return (
            self.device_id in self.coordinator.devices
            and data.get(self.field) is not None
            and data.get("date") == dt_util.now().strftime("%Y%m%d")
            and stamp is not None
            and (dt_util.utcnow() - stamp).total_seconds()
            < max(3600, self.coordinator.options[CONF_ENERGY_INTERVAL] * 3)
        )

    @property
    def native_value(self):
        return self.coordinator.energy.get(self.device_id, {}).get(self.field)

    @property
    def last_reset(self):
        # Daily cloud totals and their shares may be revised downward. TOTAL
        # with an explicit daily reset avoids treating a correction as a new
        # meter cycle and inflating Energy Dashboard consumption.
        day = self.coordinator.energy.get(self.device_id, {}).get("date")
        if not day:
            return None
        try:
            date = datetime.strptime(day, "%Y%m%d")
            return dt_util.as_utc(
                dt_util.now().replace(
                    year=date.year,
                    month=date.month,
                    day=date.day,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            )
        except ValueError, TypeError:
            return None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.energy.get(self.device_id, {})
        return {
            "description": "Panasonic's delayed/estimated daily electricity total. Heating/cooling allocations use only reported fractions in the range 0–1. These are electrical input, not thermal output or COP.",
            "date": data.get("date"),
            "last_success": data.get("last_success"),
            "last_error": data.get("error"),
            "last_attempt": data.get("last_attempt"),
            "http_status": data.get("http_status"),
            "error_code": data.get("error_code"),
            "requested_date": data.get("requested_date"),
            "timezone_offset": data.get("timezone_offset"),
            "history_count": data.get("history_count"),
            "returned_dates": data.get("returned_dates"),
            "heat_consumption_fraction": data.get("heating_rate"),
            "cool_consumption_fraction": data.get("cooling_rate"),
        }
