"""Combined SPOT exports route per track without copying history to both feeds."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.spot_trace_history.gpx_import import async_import_gpx
from custom_components.spot_trace_history.store import Store

SAMPLE = Path(__file__).parent / 'fixtures/activity_report.gpx'
MAPPING = {'Bluey': 'vehicle-123', 'Ultimate': 'trailer-456'}


@pytest.fixture
def importer(tmp_path):
    store = Store(tmp_path / 'archive.sqlite')
    coordinators = [SimpleNamespace(feed=feed, entry=SimpleNamespace(entry_id=entry), store=store,
                                    async_set_updated_data=Mock())
                    for feed, entry in [('vehicle-feed', 'vehicle-entry'), ('trailer-feed', 'trailer-entry')]]

    async def execute(fn, *args):
        return fn(*args)

    return SimpleNamespace(async_add_executor_job=execute), coordinators, store


def seed(store, feed, device, name):
    store.insert(feed, [{'id': f'live:{device}', 'device': device, 'name': name, 'time': 100,
                        'lat': -37, 'lon': 145, 'type': 'TRACK'}])


@pytest.mark.asyncio
async def test_combined_export_routes_known_ids_and_deduplicates(importer):
    hass, entries, store = importer
    seed(store, 'vehicle-feed', 'vehicle-123', 'Vehicle renamed')
    seed(store, 'trailer-feed', 'trailer-456', 'Trailer renamed')
    for _ in range(2):
        assert await async_import_gpx(hass, entries, SAMPLE, {'device_mapping': MAPPING}) == 4
    assert set(store.latest('vehicle-feed')) == {'vehicle-123'}
    assert set(store.latest('trailer-feed')) == {'trailer-456'}
    assert store.list_devices('vehicle-feed')[0]['count'] == 3
    assert store.list_devices('trailer-feed')[0]['count'] == 3
    for entry in entries:
        assert entry.async_set_updated_data.call_count == 2


@pytest.mark.asyncio
async def test_explicit_feed_mapping_imports_into_empty_feeds(importer):
    hass, entries, store = importer
    assert await async_import_gpx(hass, entries, SAMPLE, {
        'device_mapping': MAPPING,
        'feed_mapping': {'Bluey': 'vehicle-feed', 'Ultimate': 'trailer-feed'},
    }) == 4
    assert set(store.latest('vehicle-feed')) == {'vehicle-123'}
    assert set(store.latest('trailer-feed')) == {'trailer-456'}


@pytest.mark.asyncio
async def test_combined_export_matches_archived_names(importer):
    hass, entries, store = importer
    seed(store, 'vehicle-feed', 'vehicle-123', 'Bluey')
    seed(store, 'trailer-feed', 'trailer-456', 'Ultimate')
    await async_import_gpx(hass, entries, SAMPLE, {})
    assert set(store.latest('vehicle-feed')) == {'vehicle-123'}
    assert set(store.latest('trailer-feed')) == {'trailer-456'}


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['unknown', 'ambiguous', 'unconfigured', 'conflicting'])
async def test_routing_errors_do_not_import_any_tracks(importer, mode):
    hass, entries, store = importer
    seed(store, 'vehicle-feed', 'vehicle-123', 'Bluey')
    data = {'device_mapping': MAPPING}
    if mode == 'ambiguous':
        seed(store, 'vehicle-feed', 'trailer-456', 'Ultimate')
        seed(store, 'trailer-feed', 'trailer-456', 'Ultimate')
    if mode == 'unconfigured':
        data['feed_mapping'] = {'Ultimate': 'missing-feed'}
    if mode == 'conflicting':
        data.update(feed_id='vehicle-feed', feed_mapping={'Ultimate': 'trailer-feed'})
    before = {entry.feed: store.list_devices(entry.feed) for entry in entries}
    with pytest.raises(ValueError, match='Cannot uniquely select a feed'):
        await async_import_gpx(hass, entries, SAMPLE, data)
    assert {entry.feed: store.list_devices(entry.feed) for entry in entries} == before
    for entry in entries:
        entry.async_set_updated_data.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('selection', [{'feed_id': 'vehicle-feed'}, {'entry_id': 'vehicle-entry'}])
async def test_legacy_single_destination_import(importer, selection):
    hass, entries, store = importer
    await async_import_gpx(hass, entries, SAMPLE, {**selection, 'device_mapping': MAPPING})
    assert set(store.latest('vehicle-feed')) == {'vehicle-123', 'trailer-456'}
    assert store.list_devices('trailer-feed') == []
    entries[1].async_set_updated_data.assert_not_called()


@pytest.mark.asyncio
async def test_single_configured_feed_preserves_archived_only_devices(importer):
    hass, entries, store = importer
    await async_import_gpx(hass, entries[:1], SAMPLE, {})
    assert set(store.latest('vehicle-feed')) == {'Bluey', 'Ultimate'}


@pytest.mark.asyncio
async def test_explicit_feed_mapping_can_keep_gpx_track_ids(importer):
    hass, entries, store = importer
    await async_import_gpx(hass, entries, SAMPLE, {
        'feed_mapping': {'Bluey': 'vehicle-feed', 'Ultimate': 'trailer-feed'},
    })
    assert set(store.latest('vehicle-feed')) == {'Bluey'}
    assert set(store.latest('trailer-feed')) == {'Ultimate'}
