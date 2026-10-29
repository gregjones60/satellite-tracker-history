"""Device trackers for each SPOT messenger."""
from datetime import datetime, timezone

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICES, CONF_ENABLED, CONF_ICON, CONF_NAME, DOMAIN

# Updates come from the coordinator; entities never poll.
PARALLEL_UPDATES = 0


def tracker_unique_id(feed, device):
    return f"{feed}_{device}"


def device_settings(entry, device):
    return entry.options.get(CONF_DEVICES, {}).get(device, {})


def device_enabled(entry, device):
    return device_settings(entry, device).get(CONF_ENABLED, True)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()

    def add_devices():
        new = {
            device
            for device in set(coordinator.data or {}) - known
            if device_enabled(entry, device)
        }
        if new:
            known.update(new)
            async_add_entities([SpotTracker(coordinator, entry, device) for device in new])

    add_devices()
    entry.async_on_unload(coordinator.async_add_listener(add_devices))


class SpotTracker(CoordinatorEntity, TrackerEntity):
    _attr_should_poll = False
    # The tracker is the device's main feature, so it takes the device's name.
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator, entry, device):
        super().__init__(coordinator)
        self.entry = entry
        self.device = device
        self._attr_unique_id = tracker_unique_id(coordinator.feed, device)

    def _device_name(self):
        return device_settings(self.entry, self.device).get(CONF_NAME) or self.coordinator.data.get(self.device, {}).get(
            "name", self.device
        )

    @property
    def source_type(self):
        return SourceType.GPS

    @property
    def icon(self):
        return device_settings(self.entry, self.device).get(CONF_ICON) or None

    @property
    def device_info(self):
        """Associate each tracker with a native HA device for area/label settings."""
        return DeviceInfo(identifiers={(DOMAIN, self._attr_unique_id)}, name=self._device_name(),
                          manufacturer='SPOT', serial_number=self.device)

    @property
    def latitude(self):
        return self.coordinator.data.get(self.device, {}).get("lat")

    @property
    def longitude(self):
        return self.coordinator.data.get(self.device, {}).get("lon")

    @property
    def extra_state_attributes(self):
        p = self.coordinator.data.get(self.device, {})
        return {
            "last_spot_message": datetime.fromtimestamp(
                p["time"], timezone.utc
            ).isoformat()
            if p.get("time")
            else None,
            "message_type": p.get("type"),
            "messenger_id": self.device,
        }
