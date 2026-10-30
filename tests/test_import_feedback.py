"""Import notifications and optional action responses, with HA test doubles."""
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.satellite_tracker_history.gpx import parse_gpx_report
from custom_components.satellite_tracker_history.import_feedback import import_message


def test_gpx_report_counts_invalid_and_unnamed_points(tmp_path):
    source = tmp_path/'history.gpx'
    source.write_text('''<gpx xmlns="http://www.topografix.com/GPX/1/1">
      <trk><name>Vehicle</name><trkseg>
        <trkpt lat="-37" lon="145"><time>2026-01-01T00:00:00Z</time></trkpt>
        <trkpt lat="999" lon="145"><time>2026-01-01T00:01:00Z</time></trkpt>
      </trkseg></trk><trk><trkseg><trkpt lat="-37" lon="145"/></trkseg></trk></gpx>''')
    result = parse_gpx_report(source)
    assert result['total'] == 3
    assert result['skipped'] == 2
    assert len(result['positions']) == 1


@pytest.fixture
def actions(monkeypatch):
    components = types.ModuleType('homeassistant.components')
    notification = types.ModuleType('homeassistant.components.persistent_notification')
    notification.async_create = Mock()
    core = types.ModuleType('homeassistant.core')
    core.SupportsResponse = types.SimpleNamespace(OPTIONAL='optional')
    exceptions = types.ModuleType('homeassistant.exceptions')
    class HomeAssistantError(Exception):
        def __init__(self, *args, **kwargs):
            super().__init__(*args)
            self.translation_key = kwargs.get('translation_key')
            self.translation_placeholders = kwargs.get('translation_placeholders')
    exceptions.HomeAssistantError = HomeAssistantError
    cv = types.ModuleType('homeassistant.helpers.config_validation')
    cv.string = str
    for module in (components,notification,core,exceptions,cv):
        monkeypatch.setitem(sys.modules,module.__name__,module)
    path = Path(__file__).resolve().parents[1]/'custom_components/satellite_tracker_history/import_actions.py'
    spec = importlib.util.spec_from_file_location('custom_components.satellite_tracker_history.import_actions',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [False,True])
async def test_import_actions_show_counts_and_optionally_return_results(actions,tmp_path,response):
    report = {'filename':'history.gpx','total':10,'valid':8,'added':0,'duplicates':8,'skipped':2,
              'start_time':'2020-01-01T00:00:00+00:00','end_time':'2020-02-01T00:00:00+00:00',
              'destinations':[{'entry_id':'one','added':0}]}
    actions.async_import_gpx = AsyncMock(return_value=report)
    actions.async_import_sqlite = AsyncMock(return_value=report)
    registry = {}
    def register(domain,name,handler,**kwargs):
        assert kwargs['supports_response'] == 'optional'
        registry[name] = handler
    hass = types.SimpleNamespace(config=types.SimpleNamespace(path=lambda:str(tmp_path)),data={},
        services=types.SimpleNamespace(has_service=lambda *args:False,async_register=register))
    actions.register_import_actions(hass,lambda hass:[])
    for name,suffix in [('import_gpx','.gpx'),('import_sqlite','.db')]:
        filename='history'+suffix
        (tmp_path/filename).write_text('test')
        result = await registry[name](types.SimpleNamespace(data={'filename':filename},return_response=response))
        assert result == (report if response else None)
    actions.async_import_gpx.assert_awaited_once()
    actions.async_import_sqlite.assert_awaited_once()
    message = actions.persistent_notification.async_create.call_args.args[1]
    assert '**0 locations added**' in message
    assert 'Duplicates ignored: 8' in message
    assert 'skipped: 2' in message
    assert '2020-01-01' in message
    assert 'matching year or dates' in message


@pytest.mark.asyncio
async def test_failed_import_replaces_success_notification(actions,tmp_path):
    (tmp_path/'history.gpx').write_text('test')
    actions.async_import_gpx = AsyncMock(side_effect=ValueError('Cannot select a feed'))
    registry = {}
    hass = types.SimpleNamespace(config=types.SimpleNamespace(path=lambda:str(tmp_path)),data={},
        services=types.SimpleNamespace(has_service=lambda *args:False,
            async_register=lambda domain,name,handler,**kwargs:registry.update({name:handler})))
    actions.register_import_actions(hass,lambda hass:[])
    with pytest.raises(actions.HomeAssistantError,match='Cannot select a feed') as caught:
        await registry['import_gpx'](types.SimpleNamespace(data={'filename':'history.gpx'},return_response=True))
    assert caught.value.translation_key == 'import_failed'
    assert caught.value.translation_placeholders == {'error':'Cannot select a feed'}
    assert actions.persistent_notification.async_create.call_args.kwargs['title'] == 'History import failed'


def test_empty_report_does_not_invent_date_range():
    result = {'added':0,'duplicates':0,'skipped':0,'total':0,'start_time':None,'end_time':None,'destinations':[]}
    assert 'date range' not in import_message(result)
