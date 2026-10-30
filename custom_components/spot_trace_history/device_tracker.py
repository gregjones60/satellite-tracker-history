"""The device tracker of each vehicle."""
from datetime import datetime, timezone

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE, CONF_ENABLED, CONF_ICON, DOMAIN, PROVIDER_SPOT
from .vehicle import MANUFACTURERS, archive_feed, provider, tracker_unique_id, vehicle_name

# Updates come from the coordinator; entities never poll.
PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SpotTracker(entry.runtime_data, entry)])


class SpotTracker(CoordinatorEntity, TrackerEntity):
    _attr_should_poll = False
    # The tracker is the device's main feature, so it takes the device's name.
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self.device = entry.data[CONF_DEVICE]
        self.provider = provider(entry.data)
        self._attr_unique_id = tracker_unique_id(archive_feed(entry.data), self.device)
        # Applies only when the entity is first registered; trackers switched off before
        # vehicles had their own entries are created disabled. Later changes belong to HA.
        self._attr_entity_registry_enabled_default = entry.options.get(CONF_ENABLED, True)

    @property
    def _position(self):
        return self.coordinator.data or {}

    @property
    def source_type(self):
        return SourceType.GPS

    @property
    def icon(self):
        return self.entry.options.get(CONF_ICON) or None

    @property
    def device_info(self):
        """Associate the tracker with a native HA device for area/label settings."""
        return DeviceInfo(identifiers={(DOMAIN, self._attr_unique_id)}, name=vehicle_name(self.entry, self._position),
                          manufacturer=MANUFACTURERS[self.provider], serial_number=self.device)

    @property
    def latitude(self):
        return self._position.get("lat")

    @property
    def longitude(self):
        return self._position.get("lon")

    @property
    def extra_state_attributes(self):
        p = self._position
        last = datetime.fromtimestamp(p["time"], timezone.utc).isoformat() if p.get("time") else None
        if self.provider == PROVIDER_SPOT:
            # SPOT's attribute names predate other services; automations may rely on them.
            return {"last_spot_message": last, "message_type": p.get("type"), "messenger_id": self.device}
        return {"last_message": last, "message_type": p.get("type"), "imei": self.device}
