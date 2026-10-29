"""Tracker defaults and stable identities for native HA customization."""
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import Mock

import pytest

from custom_components.spot_trace_history.const import DOMAIN


@pytest.fixture
def trackers(monkeypatch):
    components = types.ModuleType('homeassistant.components')
    components.__path__ = []
    tracker = types.ModuleType('homeassistant.components.device_tracker')
    tracker.TrackerEntity = type('TrackerEntity', (), {})
    tracker.SourceType = types.SimpleNamespace(GPS='gps')
    update = types.ModuleType('homeassistant.helpers.update_coordinator')
    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator
    update.CoordinatorEntity = CoordinatorEntity
    registry = types.ModuleType('homeassistant.helpers.device_registry')
    registry.DeviceInfo = dict
    for module in (components,tracker,update,registry):
        monkeypatch.setitem(sys.modules,module.__name__,module)
    path = Path(__file__).resolve().parents[1]/'custom_components/spot_trace_history/device_tracker.py'
    spec = importlib.util.spec_from_file_location('custom_components.spot_trace_history.device_tracker',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_icon_default_and_native_device_identity_survive_rename(trackers):
    coordinator = types.SimpleNamespace(feed='feed-a',data={'vehicle':{'name':'Bluey'}})
    entry = types.SimpleNamespace(options={})
    entity = trackers.SpotTracker(coordinator,entry,'vehicle')
    assert entity.icon is None
    identifiers = entity.device_info['identifiers']
    assert identifiers == {(DOMAIN,'feed-a_vehicle')}
    assert entity.device_info['manufacturer'] == 'SPOT'
    entry.options = {'devices':{'vehicle':{'name':'Touring vehicle','icon':'mdi:car-estate'}}}
    assert entity.icon == 'mdi:car-estate'
    assert entity.device_info['name'] == 'Touring vehicle'
    assert entity.device_info['identifiers'] == identifiers
    entry.options['devices']['vehicle']['icon'] = ''
    assert entity.icon is None
    other = trackers.SpotTracker(types.SimpleNamespace(feed='feed-b',data=coordinator.data),entry,'vehicle')
    assert other.device_info['identifiers'] != identifiers


@pytest.mark.asyncio
async def test_disabled_tracker_is_not_created_but_archive_data_remains(trackers):
    coordinator = types.SimpleNamespace(feed='feed-a',data={'vehicle':{'name':'Bluey'},'trailer':{'name':'Camper'}},
                                         async_add_listener=Mock(return_value=Mock()))
    entry = types.SimpleNamespace(entry_id='entry',options={'devices':{'trailer':{'enabled':False}}},
                                  async_on_unload=Mock(),runtime_data=coordinator)
    hass = types.SimpleNamespace(data={})
    add = Mock()
    await trackers.async_setup_entry(hass,entry,add)
    assert [entity.device for entity in add.call_args.args[0]] == ['vehicle']
    assert set(coordinator.data) == {'vehicle','trailer'}
    # A new messenger discovered during later polling gets its native device too.
    coordinator.data['second-vehicle'] = {'name':'Second vehicle'}
    coordinator.async_add_listener.call_args.args[0]()
    assert [entity.device for entity in add.call_args.args[0]] == ['second-vehicle']
