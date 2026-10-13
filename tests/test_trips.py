"""Trip definitions persist independently of feeds and preserve archive data."""
import importlib.util
from pathlib import Path
import sqlite3
import sys
import types
from unittest.mock import Mock

import pytest
import voluptuous as vol

from custom_components.spot_trace_history.store import Store


def test_trips_survive_reopening_legacy_archive(tmp_path):
    path = tmp_path / 'history.sqlite'
    # Simulate the existing archive before the trip table was introduced.
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE positions (feed TEXT NOT NULL,id TEXT NOT NULL,device TEXT NOT NULL,name TEXT,time INTEGER NOT NULL,lat REAL NOT NULL,lon REAL NOT NULL,type TEXT,PRIMARY KEY(feed,id))')
        db.execute("INSERT INTO positions VALUES ('f','1','d','Device',100,-37,145,'TRACK')")
    store = Store(path)
    first = store.create_trip('  Camping  ', '2026-01-01', '2026-01-05')
    recent = store.create_trip('Weekend', '2026-09-01', '2026-09-01')
    assert first['name'] == 'Camping'
    assert Store(path).list_trips() == [recent, first]
    assert store.latest('f')['d']['time'] == 100
    assert store.list_devices('f')[0]['count'] == 1


@pytest.mark.parametrize('name,start,end', [
    (' ', '2026-01-01', '2026-01-02'), ('x'*101, '2026-01-01', '2026-01-02'),
    ('Trip', '2026-02-30', '2026-03-01'), ('Trip','20260101','2026-01-02'),
    ('Trip', '2026-01-05','2026-01-01'), ('Trip','2025-01-01','2026-01-02'),
])
def test_invalid_trip_is_not_saved(tmp_path,name,start,end):
    store = Store(tmp_path / 'history.sqlite')
    with pytest.raises(ValueError):
        store.create_trip(name,start,end)
    assert store.list_trips() == []


def test_duplicate_name_returns_clear_error(tmp_path):
    store = Store(tmp_path / 'history.sqlite')
    store.create_trip('Camping','2026-01-01','2026-01-02')
    with pytest.raises(ValueError,match='already exists'):
        store.create_trip('Camping','2026-02-01','2026-02-02')
    assert len(store.list_trips()) == 1


@pytest.fixture
def websocket_module(monkeypatch):
    components = types.ModuleType('homeassistant.components')
    components.__path__ = []
    api = types.ModuleType('homeassistant.components.websocket_api')
    def command(schema):
        def decorate(fn):
            fn.schema = vol.Schema(schema)
            return fn
        return decorate
    api.websocket_command = command
    api.async_response = lambda fn: fn
    cv = types.ModuleType('homeassistant.helpers.config_validation')
    cv.string = str
    for module in (components,api,cv):
        monkeypatch.setitem(sys.modules,module.__name__,module)
    path = Path(__file__).resolve().parents[1] / 'custom_components/spot_trace_history/trips.py'
    spec = importlib.util.spec_from_file_location('custom_components.spot_trace_history.trips',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_websocket_create_list_and_validation(websocket_module,tmp_path):
    async def execute(fn,*args):
        return fn(*args)
    hass = types.SimpleNamespace(config=types.SimpleNamespace(path=lambda name:str(tmp_path/name)),
                                 async_add_executor_job=execute)
    connection = Mock()
    message = {'id':1,'type':'spot_trace_history/create_trip','name':'Camping',
               'start_date':'2026-01-01','end_date':'2026-01-02'}
    # HA adds the request id separately; validate the command payload.
    websocket_module.ws_create_trip.schema({k:v for k,v in message.items() if k!='id'})
    await websocket_module.ws_create_trip(hass,connection,message)
    trip = connection.send_result.call_args.args[1]
    assert trip['name'] == 'Camping'
    await websocket_module.ws_trips(hass,connection,{'id':2})
    connection.send_result.assert_called_with(2,[trip])
    connection.reset_mock()
    await websocket_module.ws_create_trip(hass,connection,{**message,'end_date':'2025-01-01'})
    assert connection.send_error.call_args.args[:2] == (1,'invalid_trip')
    connection.send_result.assert_not_called()
