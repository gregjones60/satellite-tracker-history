"""Device trackers for each SPOT messenger."""
from datetime import datetime, timezone

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICES, CONF_ENABLED, CONF_ICON, CONF_NAME, DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known = set()

    def device_enabled(device):
        settings = entry.options.get(CONF_DEVICES, {}).get(device, {})
        return settings.get(CONF_ENABLED, True)

    def add_devices():
        new = {
            device
            for device in set(coordinator.data or {}) - known
            if device_enabled(device)
        }
        if new:
            known.update(new)
            async_add_entities([SpotTracker(coordinator, entry, device) for device in new])

    add_devices()
    entry.async_on_unload(coordinator.async_add_listener(add_devices))


class SpotTracker(CoordinatorEntity, TrackerEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, entry, device):
        super().__init__(coordinator)
        self.entry = entry
        self.device = device
        self._attr_unique_id = f"{coordinator.feed}_{device}"

    @property
    def name(self):
        configured = self.entry.options.get(CONF_DEVICES, {}).get(self.device, {})
        return configured.get(CONF_NAME) or self.coordinator.data.get(self.device, {}).get(
            "name", self.device
        )

    @property
    def source_type(self):
        return SourceType.GPS

    @property
    def icon(self):
        return self.entry.options.get(CONF_DEVICES, {}).get(self.device, {}).get(CONF_ICON) or None

    @property
    def device_info(self):
        """Associate each tracker with a native HA device for area/label settings."""
        return {'identifiers': {(DOMAIN, self._attr_unique_id)}, 'name': self.name, 'manufacturer': 'SPOT'}

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
