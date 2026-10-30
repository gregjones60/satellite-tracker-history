"""Satellite Tracker History integration."""
import asyncio
from pathlib import Path
import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryError
from homeassistant.loader import async_get_integration
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import websocket_api
from homeassistant.helpers import (config_validation as cv, device_registry as dr, entity_registry as er,
                                   issue_registry as ir)
from homeassistant.helpers.start import async_at_started
from .coordinator import SpotCoordinator, loaded_coordinator, loaded_coordinators
from .vehicle import archive_feed, tracker_unique_id, vehicle_name, vehicle_unique_id
from .store import async_get_store
from .import_actions import register_import_actions
from .trips import ws_trips, ws_create_trip, ws_update_trip, ws_delete_trip
from .const import (CONF_DEVICE, CONF_DEVICES, CONF_ENABLED, CONF_FEED_ID, CONF_ICON, CONF_NAME, DOMAIN,
                    LEGACY_DOMAIN, PROVIDER_SPOT)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS=['device_tracker']
TAKEOVER_LOCK = f'{DOMAIN}_takeover'

SpotConfigEntry = ConfigEntry[SpotCoordinator]


async def async_setup(hass, config):
    """Serve the bundled Lovelace card and register domain-wide actions and commands."""
    www = Path(__file__).parent / "www"
    integration = await async_get_integration(hass, DOMAIN)
    url = f"/satellite_tracker_history/satellite-tracker-history-card.js?v={integration.version}"
    await hass.http.async_register_static_paths([
        StaticPathConfig("/satellite_tracker_history/satellite-tracker-history-card.js", str(www / "satellite-tracker-history-card.js"), False),
        # The card requests the bundled Leaflet with its version in the query, so it can be cached.
        StaticPathConfig("/satellite_tracker_history/leaflet", str(www / "leaflet"), True),
    ])
    frontend.add_extra_js_url(hass, url)
    register_import_actions(hass, loaded_coordinators)
    for command in (ws_devices, ws_track, ws_trips, ws_create_trip, ws_update_trip, ws_delete_trip):
        websocket_api.async_register_command(hass, command)

    # Once every integration has set up, so a still-installed old integration can be detected.
    # Home Assistant only loads this integration at startup once it has entries of its own, so the
    # config flow also offers the takeover.
    async_at_started(hass, async_take_over_legacy)
    return True


async def async_take_over_legacy(hass):
    """Recreate every "SPOT Trace History" entry under this domain, then remove the old entry.

    Each new vehicle entry moves its tracker entity and device from the old domain when it sets up.
    Returns how many vehicles were created.
    """
    # The config flow and startup can both start a takeover; the second finds nothing left to do.
    async with hass.data.setdefault(TAKEOVER_LOCK, asyncio.Lock()):
        return await _async_take_over_legacy(hass)


async def _async_take_over_legacy(hass):
    legacy = hass.config_entries.async_entries(LEGACY_DOMAIN)
    if not legacy:
        return 0
    if LEGACY_DOMAIN in hass.config.components:
        # Its trackers are loaded, so they cannot be moved, and both would poll the same feeds.
        ir.async_create_issue(hass, DOMAIN, 'legacy_installed', is_fixable=False,
                              severity=ir.IssueSeverity.ERROR, translation_key='legacy_installed')
        return 0
    ir.async_delete_issue(hass, DOMAIN, 'legacy_installed')
    created = 0
    for old in legacy:
        if old.version == 1:
            vehicles = await _async_feed_vehicles(hass, old)
        else:
            vehicles = [{'data': dict(old.data), 'options': dict(old.options), 'title': old.title}]
        for vehicle in vehicles:
            if vehicle['data'].get(CONF_DEVICE) is None:
                continue
            # Setting up the new entry moves the tracker and device, before the old entry's removal
            # would delete whatever it still owns.
            result = await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_IMPORT},
                                                               data=vehicle)
            created += result['type'] is FlowResultType.CREATE_ENTRY
        await hass.config_entries.async_remove(old.entry_id)
    return created


async def async_reload_entry(hass, entry):
    """Reload an entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass, entry: SpotConfigEntry):
    """Version 1 entries were whole feeds; version 2 entries are one vehicle each."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        await _async_split_feed_entry(hass, entry)
    return True


async def _async_split_feed_entry(hass, entry):
    """Keep one messenger on this entry and give every other one its own entry; no history moves."""
    first, *others = await _async_feed_vehicles(hass, entry) or [None]
    if first is None:
        # Nothing was ever received or configured; setup explains how to add the vehicle.
        hass.config_entries.async_update_entry(entry, version=2, data={**entry.data, CONF_DEVICE: None}, options={})
        return
    hass.config_entries.async_update_entry(
        entry, version=2, unique_id=vehicle_unique_id(PROVIDER_SPOT, entry.data[CONF_FEED_ID],
                                                      first['data'][CONF_DEVICE]), **first)
    for vehicle in others:
        await hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_IMPORT}, data=vehicle)


async def _async_feed_vehicles(hass, entry):
    """The vehicles of a version 1 SPOT feed entry: one per messenger in the archive or its settings.

    The first is an enabled messenger that already has a tracker, where there is one.
    """
    feed = entry.data[CONF_FEED_ID]
    archived = await hass.async_add_executor_job(async_get_store(hass).list_devices, feed)
    names = {device['device']: device['name'] for device in archived}
    settings = entry.options.get(CONF_DEVICES, {})
    messengers = list(names) + [device for device in settings if device not in names]
    # The original entry keeps an enabled messenger that already has a tracker, so it carries on unchanged.
    entities = er.async_get(hass)
    messengers.sort(key=lambda device: (
        settings.get(device, {}).get(CONF_ENABLED, True) is False,
        entities.async_get_entity_id('device_tracker', DOMAIN, tracker_unique_id(feed, device)) is None))

    def vehicle(device):
        configured = settings.get(device, {})
        options = {key: configured[key] for key in (CONF_NAME, CONF_ICON) if configured.get(key)}
        if configured.get(CONF_ENABLED) is False:
            options[CONF_ENABLED] = False
        title = options.get(CONF_NAME) or names.get(device) or device
        return {'data': {**entry.data, CONF_DEVICE: device}, 'options': options, 'title': title}

    return [vehicle(device) for device in messengers]


def _adopt_registry_entries(hass, entry):
    """Move this vehicle's device from the feed entry it was split from, or from the old domain.

    A tracker entity from a split needs no help: registering its unique ID moves it to this entry.
    One from the old domain belongs to another integration, so its platform is changed here, before
    the tracker platform loads and would otherwise create a second entity.
    """
    unique_id = tracker_unique_id(archive_feed(entry.data), entry.data[CONF_DEVICE])
    devices, entities = dr.async_get(hass), er.async_get(hass)
    # The entity first: moving a device to another entry deletes the entities its old entry still owns.
    legacy = entities.async_get_entity_id('device_tracker', LEGACY_DOMAIN, unique_id)
    if legacy is not None:
        entities.async_update_entity_platform(legacy, DOMAIN, new_config_entry_id=entry.entry_id)
    for domain in (DOMAIN, LEGACY_DOMAIN):
        for other in hass.config_entries.async_entries(domain):
            # Device identifiers are only unique within a config entry, so look in each one.
            device = None if other.entry_id == entry.entry_id else (
                devices.async_get_device_by_identifier((domain, unique_id), other.entry_id))
            if device is not None:
                devices.async_update_device(device.id, new_config_entry_id=entry.entry_id,
                                            new_identifiers={(DOMAIN, unique_id)})


async def async_setup_entry(hass, entry: SpotConfigEntry):
    if entry.data.get(CONF_DEVICE) is None:
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key='no_vehicle',
                               translation_placeholders={'feed_id': entry.data[CONF_FEED_ID]})
    _adopt_registry_entries(hass, entry)
    coordinator=SpotCoordinator(hass,entry,async_get_store(hass))
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data=coordinator
    await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS)
    return True

async def async_unload_entry(hass,entry: SpotConfigEntry):
    return await hass.config_entries.async_unload_platforms(entry,PLATFORMS)


async def async_remove_config_entry_device(hass, entry: SpotConfigEntry, device_entry):
    """The vehicle's own device goes with its entry; any other leftover device may be deleted."""
    own = tracker_unique_id(archive_feed(entry.data), entry.data[CONF_DEVICE])
    return (DOMAIN, own) not in device_entry.identifiers


@websocket_api.websocket_command({vol.Required('type'): 'satellite_tracker_history/devices'})
@websocket_api.async_response
async def ws_devices(hass, connection, msg):
    """Return every loaded vehicle that has archived positions."""
    result = []
    for coordinator in loaded_coordinators(hass):
        summary = await hass.async_add_executor_job(coordinator.store.device_summary, coordinator.feed,
                                                    coordinator.device)
        if summary is not None:
            entry = coordinator.entry
            result.append({'entry_id': entry.entry_id, 'feed_id': coordinator.feed, **summary,
                           'name': vehicle_name(entry, summary), 'icon': entry.options.get(CONF_ICON)})
    connection.send_result(msg['id'], result)


@websocket_api.websocket_command({
    vol.Required('type'): 'satellite_tracker_history/track',
    vol.Required('entry_id'): cv.string,
    vol.Required('device'): cv.string,
    vol.Required('start'): vol.Coerce(int),
    vol.Required('end'): vol.Coerce(int),
    vol.Optional('limit', default=20000): vol.All(vol.Coerce(int), vol.Range(min=1, max=50000)),
})
@websocket_api.async_response
async def ws_track(hass, connection, msg):
    coordinator = loaded_coordinator(hass, msg['entry_id'])
    if coordinator is None or coordinator.device != msg['device']:
        connection.send_error(msg['id'], 'not_found', 'Vehicle not found')
        return
    if msg['end'] < msg['start'] or msg['end'] - msg['start'] > 366 * 86400:
        connection.send_error(msg['id'], 'invalid_range', 'Choose a range up to 366 days')
        return
    rows = await hass.async_add_executor_job(coordinator.store.tracks,
        coordinator.feed, msg['device'], msg['start'], msg['end'], msg['limit'])
    connection.send_result(msg['id'], rows)
