"""SPOT Trace History integration."""
import asyncio
import logging
from pathlib import Path
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError
from .gpx import parse_gpx
from datetime import timedelta
from homeassistant.core import HomeAssistant
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
    url = "/spot_trace_history/spot-trace-history-card.js?v=0.5.0"
    await hass.http.async_register_static_paths([
        StaticPathConfig("/spot_trace_history/spot-trace-history-card.js", str(js_path), False)
    ])
    frontend.add_extra_js_url(hass, url)
    return True


async def async_setup_entry(hass, entry):
    store=Store(hass.config.path('spot_trace_history.sqlite'))
    coordinator=SpotCoordinator(hass,entry,store)
    hass.data.setdefault(DOMAIN,{})[entry.entry_id]=coordinator
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS)
    if not hass.services.has_service(DOMAIN, 'import_gpx'):
        async def import_gpx(call):
            # Import only local files under the Home Assistant config directory.
            base = Path(hass.config.path()).resolve()
            source = (base / call.data['filename']).resolve()
            if not source.is_relative_to(base) or source.suffix.lower() != '.gpx':
                raise HomeAssistantError('GPX file must be inside the Home Assistant config directory')
            if not source.is_file():
                raise HomeAssistantError(f'File not found: {source}')
            selected = call.data.get('feed_id')
            selected_entry = call.data.get('entry_id')
            entries = [c for c in hass.data.get(DOMAIN, {}).values()
                       if isinstance(c, SpotCoordinator) and (selected is None or c.feed == selected)
                       and (selected_entry is None or c.entry.entry_id == selected_entry)]
            if len(entries) != 1:
                raise HomeAssistantError('Specify entry_id or feed_id to select the destination SPOT feed')
            target = entries[0]
            names = await hass.async_add_executor_job(target.store.device_names, target.feed)
            names.update(call.data.get('device_mapping', {}))
            points = await hass.async_add_executor_job(parse_gpx, source, names)
            await hass.async_add_executor_job(target.store.insert, target.feed, points)
            target.async_set_updated_data(await hass.async_add_executor_job(target.store.latest, target.feed))
            _LOGGER.info('Imported %d GPX positions from %s', len(points), source.name)
        hass.services.async_register(DOMAIN, 'import_gpx', import_gpx,
            schema=vol.Schema({vol.Required('filename'): cv.string,
                               vol.Optional('feed_id'): cv.string,
                               vol.Optional('entry_id'): cv.string,
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
