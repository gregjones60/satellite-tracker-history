"""Synthetic iOS exports test parsing and imports without private account data."""
import hashlib
from pathlib import Path
from contextlib import closing
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.spot_trace_history.import_paths import import_source
from custom_components.spot_trace_history.sqlite_import import parse_spot_sqlite, async_import_sqlite
from custom_components.spot_trace_history.store import Store


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'spot_app.db'
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
            CREATE TABLE devices(pk INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE message_types(pk INTEGER PRIMARY KEY, api_key TEXT);
            CREATE TABLE messages(device_pk INTEGER, message_type_pk INTEGER,
              public_key TEXT, latitude TEXT, longitude TEXT, unixtime DATETIME);
            INSERT INTO devices VALUES(1,'Bluey'),(2,'Ultimate');
            INSERT INTO message_types VALUES(1,'UNLIMITED-TRACK'),(2,'STOP');
            INSERT INTO messages VALUES(1,1,'one','-37.0','145.0',100),
              (2,2,'two','-38.0','146.0',200), (1,1,'bad','100','145',300);
        ''')
    return path


def test_parser_reads_valid_fixes_and_leaves_source_unchanged(source):
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    points = parse_spot_sqlite(source)
    assert points == [
        {'id': 'ios:1:one', 'device': '1', 'name': 'Bluey', 'time': 100,
         'lat': -37.0, 'lon': 145.0, 'type': 'UNLIMITED-TRACK'},
        {'id': 'ios:2:two', 'device': '2', 'name': 'Ultimate', 'time': 200,
         'lat': -38.0, 'lon': 146.0, 'type': 'STOP'},
    ]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    # No users/account table is required or queried.


@pytest.mark.parametrize('lat,lon,time', [
    ('nan','145',100), ('-37','inf',100), (None,'145',100),
    ('bad','145',100), ('-37','145',0), ('-37','145',100.5), ('-37','145','bad'),
])
def test_invalid_values_are_skipped(source, lat, lon, time):
    with closing(sqlite3.connect(source)) as db, db:
        db.execute('INSERT INTO messages VALUES(1,1,?,?,?,?)', ('invalid', lat, lon, time))
    assert len(parse_spot_sqlite(source)) == 2


@pytest.mark.parametrize('problem', ['not-sqlite', 'wrong-schema', 'empty', 'duplicate-name', 'orphan'])
def test_invalid_database_reports_actionable_error(source, problem):
    if problem == 'not-sqlite':
        source.write_text('not a database')
    else:
        with closing(sqlite3.connect(source)) as db, db:
            if problem == 'wrong-schema':
                db.execute('DROP TABLE messages')
            elif problem == 'empty':
                db.execute('DELETE FROM messages')
            elif problem == 'duplicate-name':
                db.execute("UPDATE devices SET name='Bluey'")
            else:
                db.execute('DELETE FROM devices WHERE pk=2')
    with pytest.raises(ValueError):
        parse_spot_sqlite(source)


def test_missing_database_is_not_created(tmp_path):
    missing = tmp_path / 'absent.db'
    with pytest.raises(ValueError):
        parse_spot_sqlite(missing)
    assert not missing.exists()


@pytest.mark.asyncio
async def test_multifeed_import_preserves_types_ids_deduplicates_and_refreshes(source, tmp_path):
    store = Store(tmp_path / 'history.sqlite')
    entries = [SimpleNamespace(feed=feed, device=device, entry=SimpleNamespace(entry_id=entry), store=store,
                               async_set_latest=Mock())
               for feed, device, entry in [('vehicle-feed', 'vehicle-id', 'vehicle-entry'),
                                           ('trailer-feed', 'trailer-id', 'trailer-entry')]]
    async def execute(fn, *args):
        return fn(*args)
    hass = SimpleNamespace(async_add_executor_job=execute)
    data = {'device_mapping': {'Bluey':'vehicle-id', 'Ultimate':'trailer-id'},
            'feed_mapping': {'Bluey':'vehicle-feed', 'Ultimate':'trailer-feed'}}
    # The same fix already obtained through XML must not be duplicated.
    store.insert('vehicle-feed', [{'id':'xml-message', 'device':'vehicle-id', 'name':'Bluey',
                                  'time':100, 'lat':-37, 'lon':145, 'type':'UNLIMITED-TRACK'}])
    for _ in range(2):
        result = await async_import_sqlite(hass, entries, source, data)
        assert result['total'] == 3
        assert result['valid'] == 2
        assert result['skipped'] == 1
        assert result['added'] == (1 if _ == 0 else 0)
        assert result['duplicates'] == (1 if _ == 0 else 2)
        assert result['start_time'] == '1970-01-01T00:01:40+00:00'
        assert result['end_time'] == '1970-01-01T00:03:20+00:00'
    assert store.list_devices('vehicle-feed')[0]['count'] == 1
    assert store.list_devices('trailer-feed')[0]['count'] == 1
    assert store.latest('trailer-feed')['trailer-id']['type'] == 'STOP'
    with store.connect() as db:
        assert db.execute("SELECT id FROM positions WHERE feed='trailer-feed'").fetchone()[0] == 'ios:2:two'
    for entry in entries:
        assert entry.async_set_latest.call_count == 2
    # Routing failures are detected before importing any valid fixes.
    with pytest.raises(ValueError, match='Cannot uniquely select'):
        await async_import_sqlite(hass, entries, source, {
            'device_mapping': data['device_mapping'], 'feed_mapping': {'Ultimate':'missing'},
        })
    assert store.list_devices('vehicle-feed')[0]['count'] == 1


def test_import_paths_reject_traversal_symlinks_and_extensions(source, tmp_path):
    base = tmp_path / 'config'
    base.mkdir()
    (base / 'link.db').symlink_to(source)
    for filename in ['../spot_app.db', str(source), 'link.db', 'file.txt']:
        with pytest.raises(ValueError):
            import_source(base, filename, {'.db', '.sqlite', '.sqlite3'})
    target = base / 'export.DB'
    target.write_bytes(source.read_bytes())
    assert import_source(base, 'export.DB', {'.db', '.sqlite', '.sqlite3'}) == target
