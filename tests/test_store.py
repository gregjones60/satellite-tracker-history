import sqlite3

import pytest

import custom_components.satellite_tracker_history.store as store_module
import types

from custom_components.satellite_tracker_history.store import Store, async_get_store


def point(identifier, device="Bluey", time=100, lat=-37.0, lon=145.0):
    return {"id": identifier, "device": device, "name": device,
            "time": time, "lat": lat, "lon": lon, "type": "TRACK"}


def test_feed_isolation_and_deduplication(tmp_path):
    store = Store(tmp_path / "gps.sqlite")
    store.insert("feed-a", [point("1"), point("1"), point("2")])
    store.insert("feed-b", [point("1")])
    assert store.list_devices("feed-a")[0]["count"] == 1
    assert store.list_devices("feed-b")[0]["count"] == 1
    assert store.latest("feed-a")["Bluey"]["lat"] == -37.0


def test_history_filter_order_and_latest(tmp_path):
    store = Store(tmp_path / "gps.sqlite")
    store.insert("feed-a", [point("3", time=300), point("1", time=100),
                            point("2", time=200), point("other", device="Ultimate", time=250)])
    assert [p["time"] for p in store.tracks("feed-a", "Bluey", 150, 350)] == [200, 300]
    assert store.latest("feed-a")["Bluey"]["time"] == 300
    assert set(store.latest("feed-a")) == {"Bluey", "Ultimate"}


def test_imported_and_api_records_same_fix_deduplicated(tmp_path):
    store = Store(tmp_path / "gps.sqlite")
    store.insert("f", [point("gpx:1")])
    store.insert("f", [point("api:1")])
    assert store.list_devices("f")[0]["count"] == 1


def test_device_name_mapping_prefers_latest_record_and_isolates_feeds(tmp_path):
    store = Store(tmp_path / "gps.sqlite")
    old = {**point("old", device="old-tracker", time=100), "name": "Vehicle"}
    recent = {**point("recent", device="new-tracker", time=200), "name": "Vehicle"}
    unnamed = {**point("unnamed", device="unnamed", time=300), "name": ""}
    store.insert("feed-a", [recent, old, unnamed])
    store.insert("feed-b", [{**old, "device": "other-feed-tracker"}])

    assert store.device_names("feed-a") == {"Vehicle": "new-tracker"}
    assert store.device_names("feed-b") == {"Vehicle": "other-feed-tracker"}


def test_connections_closed_and_schema_created_once(tmp_path, monkeypatch):
    opened = []
    real_connect = sqlite3.connect
    def tracking_connect(*args, **kwargs):
        opened.append(real_connect(*args, **kwargs))
        return opened[-1]
    monkeypatch.setattr(store_module.sqlite3, "connect", tracking_connect)
    schema_calls = []
    real_schema = Store._create_schema
    monkeypatch.setattr(Store, "_create_schema", staticmethod(lambda db: (schema_calls.append(1), real_schema(db))))
    store = Store(tmp_path / "gps.sqlite")
    store.insert("f", [point("1")])
    store.latest("f")
    store.list_devices("f")
    assert len(opened) == 3
    assert len(schema_calls) == 1
    for db in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            db.execute("SELECT 1")


def test_one_archive_is_shared_by_every_caller(tmp_path):
    hass = types.SimpleNamespace(data={}, config=types.SimpleNamespace(path=lambda name: str(tmp_path / name)))
    store = async_get_store(hass)
    assert store.path == tmp_path / "satellite_tracker_history.sqlite"
    assert async_get_store(hass) is store


def fix(id_, time, device='d'):
    return {'id': id_, 'device': device, 'name': 'n', 'time': time, 'lat': 0, 'lon': 0, 'type': 'T'}


def test_the_old_archive_is_renamed_with_its_side_files_when_there_is_no_new_one(tmp_path):
    from custom_components.satellite_tracker_history.store import adopt_legacy_archive
    old = tmp_path / 'spot_trace_history.sqlite'
    new = tmp_path / 'satellite_tracker_history.sqlite'
    assert adopt_legacy_archive(new) is None
    Store(old).insert('feed', [fix('1', 1)])
    (tmp_path / 'spot_trace_history.sqlite-wal').write_bytes(b'wal')
    assert adopt_legacy_archive(new) == 'moved'
    assert not old.exists() and not (tmp_path / 'spot_trace_history.sqlite-wal').exists()
    assert (tmp_path / 'satellite_tracker_history.sqlite-wal').read_bytes() == b'wal'
    (tmp_path / 'satellite_tracker_history.sqlite-wal').unlink()
    assert Store(new).list_devices('feed')[0]['count'] == 1


def test_an_old_archive_found_beside_a_new_one_is_merged_in_and_kept(tmp_path):
    from custom_components.satellite_tracker_history.store import adopt_legacy_archive
    # The new archive already exists, as a setup form or a poll opened it first.
    new_path = tmp_path / 'satellite_tracker_history.sqlite'
    new = Store(new_path)
    new.insert('feed', [fix('2', 2), fix('9', 9)])
    newer = new.create_trip('Shared name', '2026-03-01', '2026-03-02')
    old = Store(tmp_path / 'spot_trace_history.sqlite')
    old.insert('feed', [fix('1', 1), fix('2', 2), fix('3', 3, 'other')])
    kept_trip = old.create_trip('Camping', '2026-01-01', '2026-01-05', [{'feed_id': 'feed', 'device': 'd'}])
    clash = old.create_trip('Shared name', '2026-02-01', '2026-02-02')
    assert adopt_legacy_archive(new_path) == 'merged'
    assert {d['device']: d['count'] for d in Store(new_path).list_devices('feed')} == {'d': 3, 'other': 1}
    trips = {t['name']: t for t in Store(new_path).list_trips()}
    assert trips['Camping'] == kept_trip
    assert trips['Shared name'] == newer and clash['id'] != newer['id']
    # The old file is kept, renamed so it is never merged twice.
    assert not (tmp_path / 'spot_trace_history.sqlite').exists()
    assert Store(tmp_path / 'spot_trace_history.sqlite.migrated').list_devices('feed')[0]['count'] == 2
    assert adopt_legacy_archive(new_path) is None
    # Another old archive later (say from a restored backup) is merged too and kept under a new name.
    Store(tmp_path / 'spot_trace_history.sqlite').insert('feed', [fix('4', 4)])
    assert adopt_legacy_archive(new_path) == 'merged'
    assert (tmp_path / 'spot_trace_history.sqlite.migrated2').exists()
    assert Store(new_path).list_devices('feed')[0]['count'] == 4


def test_old_archives_without_participants_or_trips_merge(tmp_path):
    import sqlite3
    from contextlib import closing
    from custom_components.satellite_tracker_history.store import adopt_legacy_archive
    new_path = tmp_path / 'satellite_tracker_history.sqlite'
    Store(new_path).insert('feed', [fix('1', 1)])
    with closing(sqlite3.connect(tmp_path / 'spot_trace_history.sqlite')) as db:
        db.execute('CREATE TABLE trips (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, start_date TEXT, end_date TEXT)')
        db.execute("INSERT INTO trips VALUES ('t', 'Old trip', '2026-01-01', '2026-01-02')")
        db.commit()
    assert adopt_legacy_archive(new_path) == 'merged'
    assert Store(new_path).list_trips()[0]['devices'] is None


def test_opening_the_archive_brings_in_the_old_one_but_other_files_do_not(tmp_path):
    Store(tmp_path / 'spot_trace_history.sqlite').insert('feed', [fix('1', 1)])
    other = Store(tmp_path / 'archive.sqlite')
    assert other.list_devices('feed') == []
    assert (tmp_path / 'spot_trace_history.sqlite').exists()
    archive = Store(tmp_path / 'satellite_tracker_history.sqlite')
    assert archive.list_devices('feed')[0]['count'] == 1
    assert not (tmp_path / 'spot_trace_history.sqlite').exists()
