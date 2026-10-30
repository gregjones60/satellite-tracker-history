"""Poll SPOT feeds into the shared archive, once per feed however many vehicles use it."""
import asyncio
import logging
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SpotAPI, SpotAPIError
from .const import CONF_DEVICE, CONF_FEED_ID, CONF_PASSWORD, DOMAIN, INTERVAL

_LOGGER = logging.getLogger(__name__)

POLLERS = f"{DOMAIN}_pollers"
# Vehicles on the same feed refresh at slightly different moments; a fetch this recent is reused.
FRESH_SECONDS = INTERVAL / 2


class FeedPoller:
    """Fetch one feed's newest page into the archive, shared by every vehicle on that feed."""

    def __init__(self, hass, store, feed, password):
        self.hass = hass
        self.store = store
        self.feed = feed
        self.api = SpotAPI(hass, feed, password)
        self._lock = asyncio.Lock()
        self._fetched = None

    async def async_latest(self):
        """Return the latest archived position of every device in the feed."""
        async with self._lock:
            if self._fetched is None or time.monotonic() - self._fetched >= FRESH_SECONDS:
                # The newest page is enough for regular polling.
                points = await self.api.page()
                await self.hass.async_add_executor_job(self.store.insert, self.feed, points)
                self._fetched = time.monotonic()
        return await self.hass.async_add_executor_job(self.store.latest, self.feed)


def async_get_poller(hass, store, feed, password):
    # Keyed by password too, so a vehicle with a wrong password cannot poison a shared poll.
    pollers = hass.data.setdefault(POLLERS, {})
    poller = pollers.get((feed, password))
    if poller is None:
        poller = pollers[(feed, password)] = FeedPoller(hass, store, feed, password)
    return poller


class SpotCoordinator(DataUpdateCoordinator):
    """One vehicle's latest position; data is the position dict, or None before its first fix."""

    def __init__(self, hass, entry, store):
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
                         update_interval=timedelta(seconds=INTERVAL))
        self.entry = entry
        self.store = store
        self.feed = entry.data[CONF_FEED_ID]
        self.device = entry.data[CONF_DEVICE]
        self.poller = async_get_poller(hass, store, self.feed, entry.data.get(CONF_PASSWORD, ''))

    async def _async_update_data(self):
        try:
            latest = await self.poller.async_latest()
        except (SpotAPIError, ValueError, ET.ParseError, sqlite3.Error) as exc:
            # SpotAPIError messages are sanitized and never contain the feed password.
            raise UpdateFailed(str(exc)) from exc
        return latest.get(self.device)

    def async_set_latest(self, latest):
        """Publish archive changes made outside polling, such as a history import."""
        self.async_set_updated_data(latest.get(self.device))


def loaded_coordinators(hass):
    """Return the coordinator of every loaded vehicle entry."""
    return [entry.runtime_data for entry in hass.config_entries.async_loaded_entries(DOMAIN)]


def loaded_coordinator(hass, entry_id):
    return next((c for c in loaded_coordinators(hass) if c.entry.entry_id == entry_id), None)
