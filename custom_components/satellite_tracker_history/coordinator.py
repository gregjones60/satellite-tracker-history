"""Poll tracker feeds into the shared archive, once per feed however many vehicles use it."""
import asyncio
import logging
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SpotAPI, TrackerAPIError
from .const import CONF_DEVICE, CONF_FEED_ID, CONF_PASSWORD, DOMAIN, INTERVAL, PROVIDER_GARMIN
from .garmin import GarminAPI
from .vehicle import archive_feed, provider

_LOGGER = logging.getLogger(__name__)

POLLERS = f"{DOMAIN}_pollers"
# Vehicles on the same feed refresh at slightly different moments; a fetch this recent is reused.
FRESH_SECONDS = INTERVAL / 2
# Services that filter by time are asked for this much history while a feed has nothing archived.
BACKFILL = timedelta(days=30)


def feed_api(hass, data):
    """The client for the service an entry's feed comes from."""
    api = GarminAPI if provider(data) == PROVIDER_GARMIN else SpotAPI
    return api(hass, data[CONF_FEED_ID], data.get(CONF_PASSWORD, ''))


class FeedPoller:
    """Fetch one feed's new positions into the archive, shared by every vehicle on that feed."""

    def __init__(self, hass, store, feed, api):
        self.hass = hass
        self.store = store
        self.feed = feed
        self.api = api
        self._lock = asyncio.Lock()
        self._fetched = None

    async def async_latest(self):
        """Return the latest archived position of every device in the feed."""
        async with self._lock:
            if self._fetched is None or time.monotonic() - self._fetched >= FRESH_SECONDS:
                # Resume from the newest archived fix, so a gap while Home Assistant was down is filled.
                last = await self.hass.async_add_executor_job(self.store.latest_time, self.feed)
                since = (datetime.fromtimestamp(last, timezone.utc) if last
                         else datetime.now(timezone.utc) - BACKFILL)
                points = await self.api.fetch(since)
                await self.hass.async_add_executor_job(self.store.insert, self.feed, points)
                self._fetched = time.monotonic()
        return await self.hass.async_add_executor_job(self.store.latest, self.feed)


def async_get_poller(hass, store, data):
    """The poller for an entry's feed. Keyed by password too, so a vehicle with a wrong
    password cannot poison a shared poll."""
    key = (archive_feed(data), data.get(CONF_PASSWORD, ''))
    pollers = hass.data.setdefault(POLLERS, {})
    poller = pollers.get(key)
    if poller is None:
        poller = pollers[key] = FeedPoller(hass, store, key[0], feed_api(hass, data))
    return poller


class SpotCoordinator(DataUpdateCoordinator):
    """One vehicle's latest position; data is the position dict, or None before its first fix."""

    def __init__(self, hass, entry, store):
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
                         update_interval=timedelta(seconds=INTERVAL))
        self.entry = entry
        self.store = store
        # The archive key: the SPOT feed ID, or the provider-prefixed feed of another service.
        self.feed = archive_feed(entry.data)
        self.device = entry.data[CONF_DEVICE]
        self.poller = async_get_poller(hass, store, entry.data)

    async def _async_update_data(self):
        try:
            latest = await self.poller.async_latest()
        except (TrackerAPIError, ValueError, ET.ParseError, sqlite3.Error) as exc:
            # TrackerAPIError messages are sanitized and never contain the feed password.
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
