"""Combined SPOT exports route per track into configured vehicles without copying history."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.satellite_tracker_history.gpx_import import async_import_gpx
from custom_components.satellite_tracker_history.store import Store

SAMPLE = Path(__file__).parent / 'fixtures/activity_report.gpx'
MAPPING = {'Bluey': 'vehicle-123', 'Ultimate': 'trailer-456'}


def vehicle(store, feed, device, entry):
    return SimpleNamespace(feed=feed, device=device, entry=SimpleNamespace(entry_id=entry), store=store,
                           async_set_latest=Mock())


@pytest.fixture
def importer(tmp_path):
    store = Store(tmp_path / 'archive.sqlite')
    vehicles = [vehicle(store, 'vehicle-feed', 'vehicle-123', 'vehicle-entry'),
                vehicle(store, 'trailer-feed', 'trailer-456', 'trailer-entry')]

    async def execute(fn, *args):
        return fn(*args)

    return SimpleNamespace(async_add_executor_job=execute), vehicles, store


def seed(store, feed, device, name):
    store.insert(feed, [{'id': f'live:{device}', 'device': device, 'name': name, 'time': 100,
                        'lat': -37, 'lon': 145, 'type': 'TRACK'}])


@pytest.mark.asyncio
async def test_combined_export_routes_known_ids_and_deduplicates(importer):
    hass, entries, store = importer
    seed(store, 'vehicle-feed', 'vehicle-123', 'Vehicle renamed')
    seed(store, 'trailer-feed', 'trailer-456', 'Trailer renamed')
    for _ in range(2):
        result = await async_import_gpx(hass, entries, SAMPLE, {'device_mapping': MAPPING})
        assert result['valid'] == 4
        assert result['added'] == (4 if _ == 0 else 0)
        assert result['duplicates'] == (0 if _ == 0 else 4)
        assert result['skipped'] == 0
    assert set(store.latest('vehicle-feed')) == {'vehicle-123'}
    assert set(store.latest('trailer-feed')) == {'trailer-456'}
    assert store.list_devices('vehicle-feed')[0]['count'] == 3
    assert store.list_devices('trailer-feed')[0]['count'] == 3
    for entry in entries:
        assert entry.async_set_latest.call_count == 2
    assert {(d['entry_id'], d['device']) for d in result['destinations']} == {
        ('vehicle-entry', 'vehicle-123'), ('trailer-entry', 'trailer-456')}


@pytest.mark.asyncio
async def test_vehicles_without_history_are_found_by_messenger_id(importer):
    hass, entries, store = importer
    result = await async_import_gpx(hass, entries, SAMPLE, {'device_mapping': MAPPING})
    assert result['added'] == 4
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
async def test_feed_mapping_selects_the_only_vehicle_on_each_feed(importer):
    hass, entries, store = importer
    await async_import_gpx(hass, entries, SAMPLE, {
        'feed_mapping': {'Bluey': 'vehicle-feed', 'Ultimate': 'trailer-feed'},
    })
    assert set(store.latest('vehicle-feed')) == {'vehicle-123'}
    assert set(store.latest('trailer-feed')) == {'trailer-456'}


@pytest.mark.asyncio
async def test_other_vehicles_on_an_imported_feed_are_refreshed(importer):
    hass, entries, store = importer
    spare = vehicle(store, 'vehicle-feed', 'spare-789', 'spare-entry')
    await async_import_gpx(hass, entries + [spare], SAMPLE, {'device_mapping': MAPPING})
    assert spare.async_set_latest.call_count == 1
    assert set(spare.async_set_latest.call_args.args[0]) == {'vehicle-123'}


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['unconfigured-messenger', 'ambiguous', 'unconfigured-feed', 'conflicting'])
async def test_routing_errors_do_not_import_any_tracks(importer, mode):
    hass, entries, store = importer
    seed(store, 'vehicle-feed', 'vehicle-123', 'Bluey')
    data = {'device_mapping': dict(MAPPING)}
    if mode == 'unconfigured-messenger':
        data['device_mapping']['Ultimate'] = 'missing-456'
    if mode == 'ambiguous':
        # The same messenger ID configured as a vehicle on two feeds.
        entries = entries + [vehicle(store, 'vehicle-feed', 'trailer-456', 'other-entry')]
    if mode == 'unconfigured-feed':
        data['feed_mapping'] = {'Ultimate': 'missing-feed'}
    if mode == 'conflicting':
        data.update(feed_id='vehicle-feed', feed_mapping={'Ultimate': 'trailer-feed'})
    before = {entry.feed: store.list_devices(entry.feed) for entry in entries}
    with pytest.raises(ValueError, match='Cannot uniquely select a vehicle'):
        await async_import_gpx(hass, entries, SAMPLE, data)
    assert {entry.feed: store.list_devices(entry.feed) for entry in entries} == before
    for entry in entries:
        entry.async_set_latest.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('selection', [{'feed_id': 'vehicle-feed'}, {'entry_id': 'vehicle-entry'}])
async def test_one_destination_takes_a_track_it_does_not_recognise_only_on_its_own(importer, selection, tmp_path):
    hass, entries, store = importer
    with pytest.raises(ValueError, match="'Ultimate' would be imported into the same vehicle as 'Bluey'"):
        await async_import_gpx(hass, entries, SAMPLE, {**selection, 'device_mapping': {'Bluey': 'vehicle-123'}})
    with pytest.raises(ValueError, match='would be imported into the same vehicle'):
        await async_import_gpx(hass, entries, SAMPLE, selection)
    assert store.list_devices('vehicle-feed') == []
    single = tmp_path / 'single.gpx'
    text = SAMPLE.read_text()
    single.write_text(text[:text.index('<trk>', text.index('<trk>') + 1)] + '</gpx>')
    result = await async_import_gpx(hass, entries, single, selection)
    assert result['added'] == result['valid'] > 0
    assert set(store.latest('vehicle-feed')) == {'vehicle-123'}
    assert store.list_devices('trailer-feed') == []
    entries[1].async_set_latest.assert_not_called()


@pytest.mark.asyncio
async def test_no_matching_vehicle_is_reported(importer):
    hass, entries, store = importer
    with pytest.raises(ValueError, match='No matching configured vehicle'):
        await async_import_gpx(hass, entries, SAMPLE, {'entry_id': 'missing'})
