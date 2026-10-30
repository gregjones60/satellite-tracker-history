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


def vehicle(options=None, device='vehicle', feed='feed-a'):
    return types.SimpleNamespace(data={'feed_id': feed, 'device': device}, options=options or {})


def test_icon_name_and_native_device_identity_survive_rename(trackers):
    coordinator = types.SimpleNamespace(data={'name': 'Bluey'})
    entry = vehicle()
    entity = trackers.SpotTracker(coordinator, entry)
    assert entity.icon is None
    identifiers = entity.device_info['identifiers']
    assert identifiers == {(DOMAIN, 'feed-a_vehicle')}
    assert (entity.device_info['name'], entity.device_info['manufacturer']) == ('Bluey', 'SPOT')
    entry.options = {'name': 'Touring vehicle', 'icon': 'mdi:car-estate'}
    assert entity.icon == 'mdi:car-estate'
    assert entity.device_info['name'] == 'Touring vehicle'
    assert entity.device_info['identifiers'] == identifiers
    other = trackers.SpotTracker(coordinator, vehicle(feed='feed-b'))
    assert other.device_info['identifiers'] != identifiers


def test_a_tracker_before_its_first_fix_has_no_position_and_uses_its_messenger_id(trackers):
    entity = trackers.SpotTracker(types.SimpleNamespace(data=None), vehicle(device='0-123'))
    assert (entity.latitude, entity.longitude) == (None, None)
    assert entity.device_info['name'] == '0-123'
    assert entity.extra_state_attributes == {'last_spot_message': None, 'message_type': None, 'messenger_id': '0-123'}


def test_only_trackers_switched_off_before_the_split_start_disabled(trackers):
    coordinator = types.SimpleNamespace(data=None)
    assert trackers.SpotTracker(coordinator, vehicle())._attr_entity_registry_enabled_default is True
    assert trackers.SpotTracker(coordinator, vehicle({'enabled': False}))._attr_entity_registry_enabled_default is False


@pytest.mark.asyncio
async def test_each_vehicle_entry_has_exactly_one_tracker(trackers):
    entry = vehicle()
    entry.runtime_data = types.SimpleNamespace(data={'name': 'Bluey'})
    add = Mock()
    await trackers.async_setup_entry(types.SimpleNamespace(data={}), entry, add)
    assert [entity.device for entity in add.call_args.args[0]] == ['vehicle']
