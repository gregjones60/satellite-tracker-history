"""Config entry diagnostics for bug reports.

The feed ID grants public read access to a shared feed's locations, so it is redacted alongside the
password, coordinates, and the entry title (which embeds part of the feed ID).
"""
from datetime import datetime, timezone

from homeassistant.components.diagnostics import async_redact_data

from .device_tracker import device_enabled

TO_REDACT = {"feed_id", "password", "lat", "lon", "title", "unique_id"}


def _utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else None


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    devices = await hass.async_add_executor_job(coordinator.store.list_devices, coordinator.feed)
    latest = coordinator.data or {}
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            # SpotAPIError messages are sanitized and never contain the feed password.
            "last_exception": str(coordinator.last_exception) if coordinator.last_exception else None,
            "update_interval_seconds": coordinator.update_interval.total_seconds(),
        },
        "archive": [
            {
                "messenger_id": device["device"],
                "positions": device["count"],
                "first_position": _utc(device["first"]),
                "latest_position": _utc(device["last"]),
                "latest_message_type": latest.get(device["device"], {}).get("type"),
                "tracker_enabled": device_enabled(entry, device["device"]),
            }
            for device in devices
        ],
    }
