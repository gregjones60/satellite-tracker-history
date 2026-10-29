"""Coordinator error handling and loaded-entry lookups, with HA test doubles."""
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock

import pytest

from custom_components.spot_trace_history.api import SpotAPIError
from custom_components.spot_trace_history.const import DOMAIN


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
    import custom_components.spot_trace_history.api as api
    monkeypatch.setattr(api, 'async_get_clientsession', lambda hass: None)
    path = Path(__file__).resolve().parents[1]/'custom_components/spot_trace_history/coordinator.py'
    spec = importlib.util.spec_from_file_location('custom_components.spot_trace_history.coordinator', path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def entry(entry_id='entry-a', feed='feed-a'):
    return types.SimpleNamespace(entry_id=entry_id, data={'feed_id': feed, 'password': 'secret'})


async def execute(fn, *args):
    return fn(*args)


def coordinator(module, error):
    hass = types.SimpleNamespace(async_add_executor_job=execute)
    result = module.SpotCoordinator(hass, entry(), store=None)
    result.api = types.SimpleNamespace(page=AsyncMock(side_effect=error))
    return result


def test_coordinator_is_bound_to_its_config_entry(module):
    owner = entry()
    result = module.SpotCoordinator(types.SimpleNamespace(), owner, store=None)
    assert result.init_kwargs['config_entry'] is owner
    assert result.feed == 'feed-a'


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
