"""Identity of a vehicle entry, for every tracker service it may come from.

SPOT vehicles keep the keys they had before other services were supported: the archive feed is the
SPOT feed ID itself. Other services prefix their feed with the provider, so a Garmin MapShare name can
never collide with a SPOT feed ID in the shared archive.
"""
from .const import CONF_DEVICE, CONF_FEED_ID, CONF_NAME, CONF_PROVIDER, PROVIDER_GARMIN, PROVIDER_SPOT

MANUFACTURERS = {PROVIDER_SPOT: "SPOT", PROVIDER_GARMIN: "Garmin"}


def provider(data):
    # Entries created before other services were supported have no provider and are SPOT.
    return data.get(CONF_PROVIDER, PROVIDER_SPOT)


def archive_feed(data):
    """The feed key under which a vehicle's positions are archived."""
    name = provider(data)
    return data[CONF_FEED_ID] if name == PROVIDER_SPOT else f"{name}:{data[CONF_FEED_ID]}"


def tracker_unique_id(feed, device):
    """The tracker entity's unique ID, from the archive feed key and the device ID."""
    return f"{feed}_{device}"


def vehicle_unique_id(provider_name, feed, device):
    """The config entry's unique ID."""
    return f"{provider_name}:{feed}:{device}"


def vehicle_name(entry, position=None):
    """The vehicle's chosen name, else the name its service reports, else its device ID."""
    return entry.options.get(CONF_NAME) or (position or {}).get("name") or entry.data[CONF_DEVICE]
