"""Device trackers for each SPOT messenger."""
from datetime import datetime, timezone
from homeassistant.components.device_tracker import TrackerEntity, SourceType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator=hass.data[DOMAIN][entry.entry_id]
    known=set()
    def add_devices():
        new=set(coordinator.data or {})-known
        if new:
            known.update(new)
            async_add_entities([SpotTracker(coordinator,device) for device in new])
    add_devices()
    entry.async_on_unload(coordinator.async_add_listener(add_devices))

class SpotTracker(CoordinatorEntity,TrackerEntity):
    _attr_should_poll=False
    def __init__(self, coordinator, device):
        super().__init__(coordinator)
        self.device=device
        self._attr_unique_id=f'{coordinator.feed}_{device}'

    @property
    def name(self):
        return self.coordinator.data.get(self.device,{}).get('name',self.device)

    @property
    def source_type(self):
        return SourceType.GPS

    @property
    def latitude(self):
        return self.coordinator.data.get(self.device,{}).get('lat')

    @property
    def longitude(self):
        return self.coordinator.data.get(self.device,{}).get('lon')

    @property
    def extra_state_attributes(self):
        p=self.coordinator.data.get(self.device,{})
        return {'last_spot_message': datetime.fromtimestamp(p['time'],timezone.utc).isoformat() if p.get('time') else None,'message_type':p.get('type'),'messenger_id':self.device}
