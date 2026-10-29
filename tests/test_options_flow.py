"""Exercise options behavior without starting Home Assistant.

Home Assistant surfaces are test doubles; schemas use real voluptuous. The
constructor test models the modern read-only OptionsFlow.config_entry contract.
"""
import copy
import importlib.util
import json
import re
import sys
import types
from enum import Enum
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol

from custom_components.spot_trace_history.const import DOMAIN


@pytest.fixture
def flow_module(monkeypatch):
    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    class OptionsFlow:
        @property
        def config_entry(self):
            return self._test_entry

        def async_show_menu(self, **kwargs):
            return {"type": "menu", **kwargs}

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_abort(self, **kwargs):
            return {"type": "abort", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

    class SelectSelectorMode(Enum):
        DROPDOWN = "dropdown"

    class SelectSelector:
        def __init__(self, config):
            self.config = config

        def __call__(self, value):
            return vol.In([option["value"] for option in self.config["options"]])(value)

    entries = types.ModuleType("homeassistant.config_entries")
    entries.ConfigFlow = ConfigFlow
    entries.OptionsFlow = OptionsFlow
    core = types.ModuleType("homeassistant.core")
    core.callback = lambda fn: fn
    selector = types.ModuleType("homeassistant.helpers.selector")
    selector.SelectSelector = SelectSelector
    selector.SelectSelectorMode = SelectSelectorMode
    selector.SelectOptionDict = dict
    selector.SelectSelectorConfig = dict
    class IconSelector:
        def __call__(self, value):
            return vol.Schema(str)(value)
    selector.IconSelector = IconSelector
    monkeypatch.setitem(sys.modules, entries.__name__, entries)
    monkeypatch.setitem(sys.modules, core.__name__, core)
    monkeypatch.setitem(sys.modules, selector.__name__, selector)
    monkeypatch.setattr(sys.modules["homeassistant"], "config_entries", entries, raising=False)
    monkeypatch.setattr(sys.modules["homeassistant.helpers"], "selector", selector, raising=False)

    name = "custom_components.spot_trace_history.config_flow"
    path = Path(__file__).resolve().parents[1] / "custom_components/spot_trace_history/config_flow.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def flow(flow_module, tmp_path):
    from custom_components.spot_trace_history.store import Store

    entry = types.SimpleNamespace(entry_id="entry-a", data={"feed_id": "feed-a"}, options={})
    store = Store(tmp_path / "positions.sqlite")
    for feed, device, name in [("feed-a", "vehicle", "Vehicle"),
                               ("feed-a", "trailer", "Trailer"),
                               ("feed-b", "other", "Other feed")]:
        store.insert(feed, [{"id": device, "device": device, "name": name,
                             "time": 100, "lat": -37.0, "lon": 145.0, "type": "TRACK"}])

    async def execute(fn, *args):
        return fn(*args)

    result = flow_module.SpotConfigFlow.async_get_options_flow(entry)
    # Model the config-entry binding performed by HA's options-flow manager.
    result._test_entry = entry
    result.hass = types.SimpleNamespace(
        data={DOMAIN: store},
        async_add_executor_job=AsyncMock(side_effect=execute),
    )
    return result


def test_options_factory_uses_modern_config_entry_contract(flow_module):
    entry = types.SimpleNamespace(entry_id="entry-a", options={})
    result = flow_module.SpotConfigFlow.async_get_options_flow(entry)
    assert isinstance(result, flow_module.SpotOptionsFlow)
    assert result._selected_device is None
    assert result._devices == []


@pytest.mark.asyncio
async def test_landing_menu(flow):
    result = await flow.async_step_init()
    assert result == {"type": "menu", "step_id": "init", "menu_options": ["manage_devices"]}
    flow.hass.async_add_executor_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_device_choices_use_saved_names_and_only_owning_feed(flow):
    flow.config_entry.options = {"devices": {"vehicle": {"name": "Camper", "enabled": False}}}
    result = await flow.async_step_manage_devices()
    assert result["type"] == "form"
    assert result["step_id"] == "manage_devices"
    select = next(iter(result["data_schema"].schema.values()))
    assert select.config["options"] == [
        {"value": "trailer", "label": "Trailer [trailer] (enabled)"},
        {"value": "vehicle", "label": "Camper [vehicle] (disabled)"},
    ]
    assert result["data_schema"]({"device": "vehicle"}) == {"device": "vehicle"}
    with pytest.raises(vol.Invalid):
        result["data_schema"]({"device": "other"})


@pytest.mark.asyncio
@pytest.mark.parametrize("options, defaults", [
    ({}, {"name": "Vehicle", "enabled": True}),
    ({"devices": {"vehicle": {"name": "Camper", "enabled": False}}},
     {"name": "Camper", "enabled": False}),
])
async def test_select_device_shows_defaults_and_metadata(flow, options, defaults):
    flow.config_entry.options = options
    result = await flow.async_step_manage_devices({"device": "vehicle"})
    assert result["type"] == "form"
    assert result["step_id"] == "device"
    assert result["data_schema"]({}) == {**defaults, 'icon': ''}
    assert result["description_placeholders"] == {
        "feed_id": "feed-a", "device_id": "vehicle", "message_count": "1",
        "first_position": "1970-01-01 00:01:40 UTC",
        "latest_position": "1970-01-01 00:01:40 UTC",
        "coordinates": "-37.000000, 145.000000",
    }
    with pytest.raises(vol.Invalid):
        result["data_schema"]({"name": "Vehicle", "enabled": "false"})


@pytest.mark.asyncio
@pytest.mark.parametrize("name, enabled", [("  Camper  ", False), ("   ", True)])
async def test_save_preserves_other_settings_and_archive(flow, name, enabled):
    original = {"unrelated": "keep", "devices": {
        "vehicle": {"name": "Vehicle", "enabled": True},
        "trailer": {"name": "Trailer", "enabled": False},
    }}
    flow.config_entry.options = copy.deepcopy(original)
    await flow.async_step_manage_devices({"device": "vehicle"})
    result = await flow.async_step_device({"name": name, "enabled": enabled})
    assert result["type"] == "create_entry"
    assert result["data"] == {"unrelated": "keep", "devices": {
        "vehicle": {"name": name.strip(), "enabled": enabled},
        "trailer": original["devices"]["trailer"],
    }}
    assert flow.config_entry.options == original
    devices = await flow._async_load_devices()
    assert {d["device"]: d["count"] for d in devices} == {"vehicle": 1, "trailer": 1}


@pytest.mark.asyncio
async def test_empty_feed_aborts(flow):
    flow.config_entry.data["feed_id"] = "empty-feed"
    assert await flow.async_step_manage_devices() == {"type": "abort", "reason": "no_devices"}


@pytest.mark.asyncio
async def test_unloaded_feed_reads_the_shared_archive(flow):
    # No coordinator is involved: the archive is opened from the HA config directory.
    store = flow.hass.data.pop(DOMAIN)
    flow.hass.config = types.SimpleNamespace(path=lambda name: str(store.path))
    result = await flow.async_step_manage_devices()
    assert result["step_id"] == "manage_devices"
    assert flow.hass.data[DOMAIN].path == store.path


@pytest.mark.asyncio
async def test_missing_selected_device_aborts_without_saving(flow):
    flow.async_create_entry = Mock()
    assert await flow.async_step_manage_devices({"device": "missing"}) == {
        "type": "abort", "reason": "device_not_found",
    }
    flow.async_create_entry.assert_not_called()
    assert flow.config_entry.options == {}


@pytest.mark.asyncio
async def test_device_step_without_selection_returns_to_device_picker(flow):
    result = await flow.async_step_device()
    assert result["type"] == "form"
    assert result["step_id"] == "manage_devices"


@pytest.mark.asyncio
async def test_metadata_uses_latest_archived_fix_from_owning_feed(flow):
    store = flow.hass.data[DOMAIN]
    for feed, time, lat, lon in [("feed-a", 300, -38.5, 146.5), ("feed-b", 500, 1.0, 2.0)]:
        store.insert(feed, [{"id": "recent", "device": "vehicle", "name": "Vehicle",
                                        "time": time, "lat": lat, "lon": lon, "type": "TRACK"}])
    result = await flow.async_step_manage_devices({"device": "vehicle"})
    assert result["description_placeholders"] == {
        "feed_id": "feed-a", "device_id": "vehicle", "message_count": "2",
        "first_position": "1970-01-01 00:01:40 UTC",
        "latest_position": "1970-01-01 00:05:00 UTC",
        "coordinates": "-38.500000, 146.500000",
    }


@pytest.mark.asyncio
async def test_duplicate_friendly_names_still_identify_devices(flow):
    flow.config_entry.options = {"devices": {
        "vehicle": {"name": "Tracker"}, "trailer": {"name": "Tracker"},
    }}
    result = await flow.async_step_manage_devices()
    selector = next(iter(result["data_schema"].schema.values()))
    assert [option["label"] for option in selector.config["options"]] == [
        "Tracker [trailer] (enabled)", "Tracker [vehicle] (enabled)",
    ]


@pytest.mark.asyncio
async def test_options_translation_placeholders_match_the_form(flow):
    root = Path(__file__).resolve().parents[1] / "custom_components/spot_trace_history"
    strings = json.loads((root / "translations/en.json").read_text())
    result = await flow.async_step_manage_devices({"device": "vehicle"})
    description = strings["options"]["step"]["device"]["description"]
    assert set(re.findall(r"\{(\w+)\}", description)) == set(result["description_placeholders"])
    assert "-37.000000, 145.000000" in description.format(**result["description_placeholders"])


@pytest.mark.parametrize("timestamp", [None, 10**100])
def test_unavailable_or_unrepresentable_time_has_a_display_fallback(flow_module, timestamp):
    assert flow_module.SpotOptionsFlow._position_time(timestamp) == "—"


@pytest.mark.asyncio
async def test_icon_selection_persists_and_can_be_cleared(flow):
    flow.config_entry.options = {'devices': {'vehicle': {'name':'Vehicle','enabled':True,
                                                        'icon':'mdi:car-estate','future_setting':'keep'}}}
    form = await flow.async_step_manage_devices({'device':'vehicle'})
    assert form['data_schema']({})['icon'] == 'mdi:car-estate'
    result = await flow.async_step_device({'name':'Vehicle','enabled':True,'icon':'mdi:caravan'})
    assert result['data']['devices']['vehicle']['icon'] == 'mdi:caravan'
    assert result['data']['devices']['vehicle']['future_setting'] == 'keep'
    result = await flow.async_step_device({'name':'Vehicle','enabled':True,'icon':''})
    assert 'icon' not in result['data']['devices']['vehicle']
    assert result['data']['devices']['vehicle']['future_setting'] == 'keep'
