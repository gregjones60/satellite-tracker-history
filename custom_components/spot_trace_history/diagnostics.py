"""Config entry diagnostics for bug reports.

The feed ID grants public read access to a shared feed's locations, so it is redacted alongside the
password, coordinates, and the entry title (which embeds part of the feed ID). Messenger IDs and device
names identify the owner's hardware, so each messenger appears only as a stable alias (device_1, ...)
that links its archive summary to its device settings.
"""
from datetime import datetime, timezone

from homeassistant.components.diagnostics import REDACTED, async_redact_data

from .const import CONF_DEVICES
from .device_tracker import device_enabled

TO_REDACT = {"feed_id", "password", "lat", "lon", "title", "unique_id", "name"}


def _utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else None


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    devices = await hass.async_add_executor_job(coordinator.store.list_devices, coordinator.feed)
    latest = coordinator.data or {}
    settings = entry.options.get(CONF_DEVICES, {})
    messengers = [device["device"] for device in devices]
    messengers += [device for device in settings if device not in messengers]
    alias = {device: f"device_{number}" for number, device in enumerate(messengers, 1)}

    entry_data = entry.as_dict()
    entry_data["options"] = {**entry_data["options"],
                             CONF_DEVICES: {alias[device]: value for device, value in settings.items()}}
    last_exception = None
    if coordinator.last_exception:
        # SpotAPIError messages never contain the password; SPOT's error text can echo the feed ID.
        last_exception = str(coordinator.last_exception).replace(coordinator.feed, REDACTED)
    return {
        "entry": async_redact_data(entry_data, TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": last_exception,
            "update_interval_seconds": coordinator.update_interval.total_seconds(),
        },
        "archive": [
            {
                "device": alias[device["device"]],
                "positions": device["count"],
                "first_position": _utc(device["first"]),
                "latest_position": _utc(device["last"]),
                "latest_message_type": latest.get(device["device"], {}).get("type"),
                "tracker_enabled": device_enabled(entry, device["device"]),
            }
            for device in devices
        ],
    }
