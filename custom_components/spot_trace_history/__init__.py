"""SPOT Trace History integration."""
from pathlib import Path
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.loader import async_get_integration
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import websocket_api
from homeassistant.helpers import config_validation as cv
from .coordinator import SpotCoordinator, loaded_coordinator, loaded_coordinators
from .device_tracker import device_enabled, tracker_unique_id
from .store import async_get_store
from .import_actions import register_import_actions
from .trips import ws_trips, ws_create_trip, ws_update_trip, ws_delete_trip
from .const import DOMAIN

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS=['device_tracker']

SpotConfigEntry = ConfigEntry[SpotCoordinator]


async def async_setup(hass, config):
    """Serve the bundled Lovelace card and register domain-wide actions and commands."""
    js_path = Path(__file__).parent / "www" / "spot-trace-history-card.js"
    integration = await async_get_integration(hass, DOMAIN)
    url = f"/spot_trace_history/spot-trace-history-card.js?v={integration.version}"
    await hass.http.async_register_static_paths([
        StaticPathConfig("/spot_trace_history/spot-trace-history-card.js", str(js_path), False)
    ])
    frontend.add_extra_js_url(hass, url)
    register_import_actions(hass, loaded_coordinators)
    for command in (ws_devices, ws_track, ws_trips, ws_create_trip, ws_update_trip, ws_delete_trip):
        websocket_api.async_register_command(hass, command)
    return True


async def async_reload_entry(hass, entry):
    """Reload an entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass, entry: SpotConfigEntry):
    coordinator=SpotCoordinator(hass,entry,async_get_store(hass))
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data=coordinator
    await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS)
    return True

async def async_unload_entry(hass,entry: SpotConfigEntry):
    return await hass.config_entries.async_unload_platforms(entry,PLATFORMS)


async def async_remove_config_entry_device(hass, entry: SpotConfigEntry, device_entry):
    """Allow deleting a device whose tracker is disabled; its archived history is kept."""
    feed = entry.data['feed_id']
    active = {tracker_unique_id(feed, device) for device in (entry.runtime_data.data or {})
              if device_enabled(entry, device)}
    return not any(domain == DOMAIN and identifier in active
                   for domain, identifier in device_entry.identifiers)


@websocket_api.websocket_command({vol.Required('type'): 'spot_trace_history/devices'})
@websocket_api.async_response
async def ws_devices(hass, connection, msg):
    """Return devices across all configured feeds, including archived-only devices."""
    result = []
    for coordinator in loaded_coordinators(hass):
        devices = await hass.async_add_executor_job(coordinator.store.list_devices, coordinator.feed)
        for device in devices:
            result.append({'entry_id': coordinator.entry.entry_id, 'feed_id': coordinator.feed, **device})
    connection.send_result(msg['id'], result)


@websocket_api.websocket_command({
    vol.Required('type'): 'spot_trace_history/track',
    vol.Required('entry_id'): cv.string,
    vol.Required('device'): cv.string,
    vol.Required('start'): vol.Coerce(int),
    vol.Required('end'): vol.Coerce(int),
    vol.Optional('limit', default=20000): vol.All(vol.Coerce(int), vol.Range(min=1, max=50000)),
})
@websocket_api.async_response
async def ws_track(hass, connection, msg):
    coordinator = loaded_coordinator(hass, msg['entry_id'])
    if coordinator is None:
        connection.send_error(msg['id'], 'not_found', 'SPOT configuration not found')
        return
    if msg['end'] < msg['start'] or msg['end'] - msg['start'] > 366 * 86400:
        connection.send_error(msg['id'], 'invalid_range', 'Choose a range up to 366 days')
        return
    rows = await hass.async_add_executor_job(coordinator.store.tracks,
        coordinator.feed, msg['device'], msg['start'], msg['end'], msg['limit'])
    connection.send_result(msg['id'], rows)
