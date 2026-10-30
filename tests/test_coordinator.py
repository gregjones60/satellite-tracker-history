"""Coordinator error handling and loaded-entry lookups, with HA test doubles."""
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock

import pytest

from custom_components.satellite_tracker_history.api import SpotAPIError
from custom_components.satellite_tracker_history.const import DOMAIN


@pytest.fixture
def module(monkeypatch):
    update = types.ModuleType('homeassistant.helpers.update_coordinator')
    class DataUpdateCoordinator:
        def __init__(self, hass, logger, **kwargs):
            self.hass = hass
            self.init_kwargs = kwargs
    update.DataUpdateCoordinator = DataUpdateCoordinator
    update.UpdateFailed = type('UpdateFailed', (Exception,), {})
    monkeypatch.setitem(sys.modules, update.__name__, update)
    import custom_components.satellite_tracker_history.api as api
    import custom_components.satellite_tracker_history.garmin as garmin
    for client in (api, garmin):
        monkeypatch.setattr(client, 'async_get_clientsession', lambda hass: None)
    path = Path(__file__).resolve().parents[1]/'custom_components/satellite_tracker_history/coordinator.py'
    spec = importlib.util.spec_from_file_location('custom_components.satellite_tracker_history.coordinator', path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def entry(entry_id='entry-a', feed='feed-a', device='vehicle', **data):
    return types.SimpleNamespace(entry_id=entry_id,
                                 data={'feed_id': feed, 'password': 'secret', 'device': device, **data})


async def execute(fn, *args):
    return fn(*args)


class Archive:
    def __init__(self, last=None):
        self.inserted = []
        self.last = last

    def latest_time(self, feed):
        return self.last

    def insert(self, feed, points):
        self.inserted.append((feed, points))

    def latest(self, feed):
        return {'vehicle': {'name': 'Bluey'}, 'trailer': {'name': 'Camper'}}


def make_hass():
    return types.SimpleNamespace(async_add_executor_job=execute, data={})


def coordinator(module, error):
    result = module.SpotCoordinator(make_hass(), entry(), store=Archive())
    result.poller.api = types.SimpleNamespace(fetch=AsyncMock(side_effect=error))
    return result


def test_coordinator_is_bound_to_its_config_entry(module):
    owner = entry()
    result = module.SpotCoordinator(make_hass(), owner, store=None)
    assert result.init_kwargs['config_entry'] is owner
    assert (result.feed, result.device) == ('feed-a', 'vehicle')


@pytest.mark.asyncio
async def test_each_vehicle_gets_only_its_own_position(module):
    hass, store = make_hass(), Archive()
    vehicle = module.SpotCoordinator(hass, entry(), store)
    trailer = module.SpotCoordinator(hass, entry('entry-b', device='trailer'), store)
    spare = module.SpotCoordinator(hass, entry('entry-c', device='spare'), store)
    assert vehicle.poller is trailer.poller
    vehicle.poller.api = types.SimpleNamespace(fetch=AsyncMock(return_value=[]))
    assert await vehicle._async_update_data() == {'name': 'Bluey'}
    assert await trailer._async_update_data() == {'name': 'Camper'}
    assert await spare._async_update_data() is None
    # One fetch served all three vehicles.
    assert vehicle.poller.api.fetch.await_count == 1


@pytest.mark.asyncio
async def test_a_failed_fetch_is_retried_by_the_next_vehicle(module, monkeypatch):
    hass, store = make_hass(), Archive()
    first = module.SpotCoordinator(hass, entry(), store)
    second = module.SpotCoordinator(hass, entry('entry-b', device='trailer'), store)
    first.poller.api = types.SimpleNamespace(fetch=AsyncMock(side_effect=[SpotAPIError('HTTP 500'), []]))
    with pytest.raises(module.UpdateFailed):
        await first._async_update_data()
    await second._async_update_data()
    assert first.poller.api.fetch.await_count == 2
    # A stale fetch is repeated.
    now = module.time.monotonic()
    monkeypatch.setattr(module.time, 'monotonic', lambda: now + module.FRESH_SECONDS)
    first.poller.api.fetch = AsyncMock(return_value=[])
    await first._async_update_data()
    assert first.poller.api.fetch.await_count == 1


def test_pollers_are_shared_per_feed_and_password(module):
    hass = make_hass()
    poller = lambda **data: module.async_get_poller(hass, None, {'feed_id': 'feed-a', 'password': 'pw', **data})
    a = poller()
    assert poller() is a
    assert poller(provider='spot') is a
    assert poller(password='other') is not a
    assert poller(feed_id='feed-b') is not a
    # The same name on another service is a different feed.
    garmin = poller(provider='garmin')
    assert garmin is not a
    assert (garmin.feed, type(garmin.api).__name__, type(a.api).__name__) == ('garmin:feed-a', 'GarminAPI', 'SpotAPI')


@pytest.mark.asyncio
async def test_polling_resumes_from_the_newest_archived_fix_or_backfills(module):
    for last, expected in ((1_700_000_000, module.datetime.fromtimestamp(1_700_000_000, module.timezone.utc)),
                           (None, None)):
        hass = make_hass()
        vehicle = module.SpotCoordinator(hass, entry(provider='garmin'), Archive(last))
        vehicle.poller.api = types.SimpleNamespace(fetch=AsyncMock(return_value=[]))
        before = module.datetime.now(module.timezone.utc)
        await vehicle._async_update_data()
        since = vehicle.poller.api.fetch.await_args.args[0]
        if expected:
            assert since == expected
        else:
            assert before - module.BACKFILL <= since <= module.datetime.now(module.timezone.utc) - module.BACKFILL
        assert vehicle.feed == 'garmin:feed-a'


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [SpotAPIError('SPOT feed request failed with HTTP 500'),
                                   ValueError('SPOT API error: Bad feed')])
async def test_expected_feed_failures_become_update_failed(module, error):
    with pytest.raises(module.UpdateFailed, match=str(error)):
        await coordinator(module, error)._async_update_data()


@pytest.mark.asyncio
async def test_unexpected_errors_are_left_for_home_assistant_to_report(module):
    with pytest.raises(RuntimeError):
        await coordinator(module, RuntimeError('bug'))._async_update_data()


def test_lookups_only_return_loaded_entries(module):
    first = types.SimpleNamespace(entry=entry('one'))
    second = types.SimpleNamespace(entry=entry('two'))
    requested = []
    def loaded(domain):
        requested.append(domain)
        return [types.SimpleNamespace(runtime_data=first), types.SimpleNamespace(runtime_data=second)]
    hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(async_loaded_entries=loaded))
    assert module.loaded_coordinators(hass) == [first, second]
    assert module.loaded_coordinator(hass, 'two') is second
    assert module.loaded_coordinator(hass, 'unloaded') is None
    assert set(requested) == {DOMAIN}
