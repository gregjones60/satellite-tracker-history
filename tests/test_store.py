from custom_components.spot_trace_history.store import Store


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
