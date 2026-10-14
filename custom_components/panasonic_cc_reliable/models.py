"""Conservative models for observed Comfort Cloud response shapes."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .errors import ProtocolError


def numeric(value: Any, *, temperature: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    if temperature and not -80 <= value <= 100:
        return None
    return float(value)


def get_path(data: dict, path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit():
            value = value[int(part)] if int(part) < len(value) else None
        else:
            return None
    return value


@dataclass(frozen=True)
class Device:
    guid: str
    name: str
    model: str
    kind: str
    listing: dict = field(repr=False, compare=False)

    @property
    def id(self) -> str:
        return hashlib.sha256(self.guid.encode()).hexdigest()[:24]


def discover(data: dict) -> list[Device]:
    groups = data.get("groupList")
    if not isinstance(groups, list):
        raise ProtocolError("Cloud response has no valid groupList")
    found: dict[str, Device] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        rows = group.get("deviceList") or group.get("deviceIdList", [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("deviceGuid"), str):
                continue
            kind = str(row.get("deviceType", "1"))
            kind = (
                "aquarea"
                if kind == "2"
                else "hws"
                if kind == "11"
                else "ac"
                if "parameters" in row
                else "unknown"
            )
            device = Device(
                row["deviceGuid"],
                str(row.get("deviceName", "Panasonic")),
                str(row.get("deviceModuleNumber", "Comfort Cloud")),
                kind,
                row,
            )
            found[device.id] = device
    return list(found.values())


def validate_status(device: Device, data: Any) -> dict:
    if not isinstance(data, dict):
        raise ProtocolError("Invalid device response")
    key = "status" if device.kind == "aquarea" else "parameters"
    if not isinstance(data.get(key), dict) or not data[key]:
        raise ProtocolError("Device response contains no usable status")
    return data


def source_timestamp(data: dict) -> datetime | None:
    value = data.get("timestamp")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000 if value > 10**11 else value, UTC)
    except ValueError, OverflowError, OSError:
        return None


@dataclass
class Snapshot:
    raw: dict = field(default_factory=dict, repr=False)
    last_success: datetime | None = None
    failures: int = 0
    error: str | None = None
    source: str = "unavailable"
    next_poll: float = 0

    def success(self, raw: dict, source: str) -> None:
        self.raw = raw
        self.last_success = datetime.now(UTC)
        self.failures = 0
        self.error = None
        self.source = source

    def age(self) -> float | None:
        return (
            (datetime.now(UTC) - self.last_success).total_seconds() if self.last_success else None
        )

    def usable(self, stale_after: int) -> bool:
        age = self.age()
        if age is None or age >= stale_after:
            return False
        if self.source == "cached":
            stamp = source_timestamp(self.raw)
            if stamp is None:
                return False
            cache_age = (datetime.now(UTC) - stamp).total_seconds()
            return -300 <= cache_age < stale_after
        return True


_PRIVATE_KEY = re.compile(
    r"token|password|secret|authorization|cookie|csrf|signature|email|username|deviceguid|hashguid|clientid|groupid|groupname|devicename|zonename|serial|macaddress|ipaddress|address|owner|^name$|^id$|^guid$",
    re.I,
)


def redact(data: Any) -> Any:
    """Recursive field redaction plus string scrubbing as defense in depth."""
    if isinstance(data, dict):
        return {
            key: "**REDACTED**" if _PRIVATE_KEY.search(str(key)) else redact(value)
            for key, value in data.items()
        }
    if isinstance(data, (list, tuple)):
        return [redact(item) for item in data]
    if isinstance(data, str):
        data = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "**REDACTED**", data)
        data = re.sub(r"(?i)Bearer\s+\S+", "**REDACTED**", data)
        data = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "**REDACTED**", data)
    return data


def raw_numeric_paths(data: dict, prefix: str = "") -> list[str]:
    """Only numeric device-status leaves; never turn identifiers into entities."""
    result = []
    for key, value in data.items():
        if _PRIVATE_KEY.search(key):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.extend(raw_numeric_paths(value, path))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    result.extend(raw_numeric_paths(item, f"{path}.{index}"))
        elif numeric(value) is not None and not isinstance(value, bool):
            result.append(path)
    return result
