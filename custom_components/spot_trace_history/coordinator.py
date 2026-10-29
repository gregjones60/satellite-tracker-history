"""Poll one SPOT feed into the shared archive."""
import logging
import sqlite3
import xml.etree.ElementTree as ET
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SpotAPI, SpotAPIError
from .const import DOMAIN, INTERVAL

_LOGGER = logging.getLogger(__name__)


class SpotCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, store):
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
                         update_interval=timedelta(seconds=INTERVAL))
        self.entry = entry
        self.store = store
        self.api = SpotAPI(hass, entry.data['feed_id'], entry.data.get('password', ''))
        self.feed = entry.data['feed_id']

    async def _async_update_data(self):
        try:
            # The newest page is enough for regular polling.
            points = await self.api.page()
            await self.hass.async_add_executor_job(self.store.insert, self.feed, points)
            return await self.hass.async_add_executor_job(self.store.latest, self.feed)
        except (SpotAPIError, ValueError, ET.ParseError, sqlite3.Error) as exc:
            # SpotAPIError messages are sanitized and never contain the feed password.
            raise UpdateFailed(str(exc)) from exc


def loaded_coordinators(hass):
    """Return the coordinator of every loaded feed entry."""
    return [entry.runtime_data for entry in hass.config_entries.async_loaded_entries(DOMAIN)]


def loaded_coordinator(hass, entry_id):
    return next((c for c in loaded_coordinators(hass) if c.entry.entry_id == entry_id), None)
