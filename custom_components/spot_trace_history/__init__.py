"""SPOT Trace History integration."""
import asyncio
import logging
from pathlib import Path
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError
from .gpx_import import async_import_gpx
from .sqlite_import import async_import_sqlite
from .import_paths import import_source
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.components import frontend, http
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import websocket_api
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import SpotAPI
from .store import Store
from .const import DOMAIN, INTERVAL

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER=logging.getLogger(__name__)
PLATFORMS=['device_tracker']

class SpotCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, store):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=INTERVAL))
        self.entry=entry
        self.store=store
        self.api=SpotAPI(hass, entry.data['feed_id'], entry.data.get('password',''))
        self.feed=entry.data['feed_id']
        self.backfill_start=51
        self.backfill_done=False

    async def _async_update_data(self):
        try:
            # The newest page is enough for regular polling; page through feed on initial setup.
            points=await self.api.page()
            await self.hass.async_add_executor_job(self.store.insert,self.feed,points)
            return await self.hass.async_add_executor_job(self.store.latest,self.feed)
        except Exception as exc:
            raise UpdateFailed(str(exc)) from exc

    async def backfill(self):
        """Fetch one older page at a time, separated from regular polling."""
        if self.backfill_done:
            return
        points = await self.api.page(self.backfill_start)
        await self.hass.async_add_executor_job(self.store.insert, self.feed, points)
        if len(points) < 50:
            self.backfill_done = True
        else:
            self.backfill_start += 50

async def async_setup(hass, config):
    """Serve the bundled Lovelace card without requiring /config/www."""
    js_path = Path(__file__).parent / "www" / "spot-trace-history-card.js"
    integration = await async_get_integration(hass, DOMAIN)
    url = f"/spot_trace_history/spot-trace-history-card.js?v={integration.version}"
    await hass.http.async_register_static_paths([
        StaticPathConfig("/spot_trace_history/spot-trace-history-card.js", str(js_path), False)
    ])
    frontend.add_extra_js_url(hass, url)
    return True


async def async_reload_entry(hass, entry):
    """Reload an entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass, entry):
    store=Store(hass.config.path('spot_trace_history.sqlite'))
    coordinator=SpotCoordinator(hass,entry,store)
    hass.data.setdefault(DOMAIN,{})[entry.entry_id]=coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS)
    for service, importer, suffixes in [
        ('import_gpx', async_import_gpx, {'.gpx'}),
        ('import_sqlite', async_import_sqlite, {'.db', '.sqlite', '.sqlite3'}),
    ]:
        if hass.services.has_service(DOMAIN, service):
            continue
        async def import_history(call, importer=importer, suffixes=suffixes):
            # Import only local files under the Home Assistant config directory.
            entries = [c for c in hass.data.get(DOMAIN, {}).values()
                       if isinstance(c, SpotCoordinator)]
            try:
                source = import_source(hass.config.path(), call.data['filename'], suffixes)
                count = await importer(hass, entries, source, call.data)
            except ValueError as exc:
                raise HomeAssistantError(str(exc)) from exc
            _LOGGER.info('Processed %d valid historical positions from %s (existing fixes are deduplicated)', count, source.name)
        hass.services.async_register(DOMAIN, service, import_history,
            schema=vol.Schema({vol.Required('filename'): cv.string,
                               vol.Optional('feed_id'): cv.string,
                               vol.Optional('entry_id'): cv.string,
                               vol.Optional('feed_mapping'): vol.Schema({cv.string: cv.string}),
                               vol.Optional('device_mapping'): vol.Schema({cv.string: cv.string})}))
    if not hass.data[DOMAIN].get('_ws_registered'):
        websocket_api.async_register_command(hass, ws_devices)
        websocket_api.async_register_command(hass, ws_track)
        hass.data[DOMAIN]['_ws_registered'] = True
    # Backfill can take a long time; start it without blocking startup.
    # Historical pages require separate API requests. Manual backfill deferred to a later release.
    return True

async def async_unload_entry(hass,entry):
    ok=await hass.config_entries.async_unload_platforms(entry,PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id,None)
    return ok


@websocket_api.websocket_command({vol.Required('type'): 'spot_trace_history/devices'})
@websocket_api.async_response
async def ws_devices(hass, connection, msg):
    """Return devices across all configured feeds, including archived-only devices."""
    result = []
    for entry_id, coordinator in hass.data.get(DOMAIN, {}).items():
        if not isinstance(coordinator, SpotCoordinator):
            continue
        devices = await hass.async_add_executor_job(coordinator.store.list_devices, coordinator.feed)
        for device in devices:
            result.append({'entry_id': entry_id, 'feed_id': coordinator.feed, **device})
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
    coordinator = hass.data.get(DOMAIN, {}).get(msg['entry_id'])
    if not isinstance(coordinator, SpotCoordinator):
        connection.send_error(msg['id'], 'not_found', 'SPOT configuration not found')
        return
    if msg['end'] < msg['start'] or msg['end'] - msg['start'] > 366 * 86400:
        connection.send_error(msg['id'], 'invalid_range', 'Choose a range up to 366 days')
        return
    rows = await hass.async_add_executor_job(coordinator.store.tracks,
        coordinator.feed, msg['device'], msg['start'], msg['end'], msg['limit'])
    connection.send_result(msg['id'], rows)
