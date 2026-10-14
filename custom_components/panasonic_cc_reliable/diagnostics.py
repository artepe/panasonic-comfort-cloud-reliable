"""Diagnostics never include auth state, passwords or account identifiers."""

from .models import redact


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data.coordinator
    return {
        "options": dict(entry.options),
        "account_error": coordinator.account_error,
        "transport": coordinator.client.statistics(),
        "devices": [
            {
                "kind": device.kind,
                "model": device.model,
                "data_source": coordinator.snapshots[device_id].source,
                "last_success": coordinator.snapshots[device_id].last_success,
                "failures": coordinator.snapshots[device_id].failures,
                "last_error": coordinator.snapshots[device_id].error,
                "listing": redact(device.listing),
                "status": redact(coordinator.snapshots[device_id].raw),
                "energy": redact(coordinator.energy.get(device_id, {})),
            }
            for device_id, device in coordinator.devices.items()
        ],
    }
