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


def test_the_archive_is_renamed_once_with_its_side_files(tmp_path):
    from custom_components.satellite_tracker_history.store import move_legacy_archive
    old = tmp_path / 'spot_trace_history.sqlite'
    new = tmp_path / 'satellite_tracker_history.sqlite'
    assert move_legacy_archive(tmp_path) is False
    Store(old).insert('feed', [{'id': '1', 'device': 'd', 'name': 'n', 'time': 1, 'lat': 0, 'lon': 0, 'type': 'T'}])
    (tmp_path / 'spot_trace_history.sqlite-wal').write_bytes(b'wal')
    assert move_legacy_archive(tmp_path) is True
    assert not old.exists() and not (tmp_path / 'spot_trace_history.sqlite-wal').exists()
    assert (tmp_path / 'satellite_tracker_history.sqlite-wal').read_bytes() == b'wal'
    assert Store(new).list_devices('feed')[0]['count'] == 1
    # A new archive is never overwritten by an old one that reappears, say from a restored backup.
    old.write_bytes(b'restored')
    assert move_legacy_archive(tmp_path) is False
    assert old.read_bytes() == b'restored'
    assert Store(new).list_devices('feed')[0]['count'] == 1
