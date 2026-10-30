"""Config entry diagnostics for bug reports.

The feed ID grants public read access to a shared feed's locations, so it is redacted alongside the
password, coordinates, and the entry title and unique ID (which name the vehicle or embed its IDs).
The messenger ID and vehicle name identify the owner's hardware, so they are redacted too.
"""
from datetime import datetime, timezone

from homeassistant.components.diagnostics import REDACTED, async_redact_data

from .const import CONF_DEVICE, CONF_FEED_ID, CONF_NAME, CONF_PASSWORD

TO_REDACT = {CONF_FEED_ID, CONF_PASSWORD, CONF_DEVICE, CONF_NAME, "lat", "lon", "title", "unique_id"}


def _utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else None


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    summary = await hass.async_add_executor_job(coordinator.store.device_summary, coordinator.feed,
                                                coordinator.device) or {}
    last_exception = None
    if coordinator.last_exception:
        # SpotAPIError messages never contain the password; SPOT's error text can echo the feed ID.
        last_exception = str(coordinator.last_exception)
        for secret in (coordinator.feed, coordinator.device):
            last_exception = last_exception.replace(secret, REDACTED)
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": last_exception,
            "update_interval_seconds": coordinator.update_interval.total_seconds(),
        },
        "archive": {
            "positions": summary.get("count", 0),
            "first_position": _utc(summary.get("first")),
            "latest_position": _utc(summary.get("last")),
            "latest_message_type": (coordinator.data or {}).get("type"),
        },
    }
