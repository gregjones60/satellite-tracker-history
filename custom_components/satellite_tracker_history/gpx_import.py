"""Plan and perform history imports into configured vehicles."""
from datetime import datetime, timezone
from .gpx import parse_gpx_report


def plan_import(points, vehicles, device_mapping=None, feed_mapping=None, feed_id=None, entry_id=None):
    """Resolve every track to exactly one vehicle before writing any positions; never guess."""
    device_mapping = device_mapping or {}
    feed_mapping = feed_mapping or {}
    eligible = [v for v in vehicles if (feed_id is None or v['feed_id'] == feed_id)
                and (entry_id is None or v['entry_id'] == entry_id)]
    if not eligible:
        raise ValueError('No matching configured vehicle')
    plan = {}
    destinations = {}
    # A track the vehicle does not recognise may only be imported into it on its own;
    # alongside any other track it would merge two trackers' history.
    unrecognised = {}
    for point in points:
        name = point['name']
        if name not in destinations:
            mapped_device = device_mapping.get(name)
            candidates = eligible
            if name in feed_mapping:
                candidates = [v for v in candidates if v['feed_id'] == feed_mapping[name]]
            if mapped_device is not None:
                candidates = [v for v in candidates if v['device'] == mapped_device]
            else:
                recognised = [v for v in candidates if name == v['device'] or name in v['names']]
                if recognised:
                    candidates = recognised
                elif len(candidates) == 1:
                    unrecognised[candidates[0]['entry_id']] = name
            if len(candidates) != 1:
                raise ValueError(
                    f'Cannot uniquely select a vehicle for source device/track {name!r}. '
                    'Provide device_mapping from this name to a configured messenger ID, or entry_id.'
                )
            destinations[name] = candidates[0]
        target = destinations[name]
        device = target['device']
        identifier = (point['id'] if point['id'].startswith('ios:') else
                      f"gpx:{device}:{point['time']}:{point['lat']:.6f}:{point['lon']:.6f}")
        plan.setdefault(target['entry_id'], []).append({**point, 'device': device, 'id': identifier})
    for entry_id, name in unrecognised.items():
        others = sorted({n for n, v in destinations.items() if v['entry_id'] == entry_id} - {name})
        if others:
            raise ValueError(
                f'Track {name!r} would be imported into the same vehicle as {others[0]!r}. '
                'Provide device_mapping from each track name to its messenger ID.'
            )
    return plan


async def async_import_gpx(hass, coordinators, source, data):
    return await async_import_history(hass, coordinators, source, data, parse_gpx_report)


async def async_import_history(hass, coordinators, source, data, parser):
    """Read once, validate all destinations, insert and refresh the vehicles on affected feeds."""
    vehicles = []
    by_entry = {}
    for coordinator in coordinators:
        entry_id = coordinator.entry.entry_id
        by_entry[entry_id] = coordinator
        names = await hass.async_add_executor_job(coordinator.store.device_names, coordinator.feed)
        vehicles.append({'entry_id': entry_id, 'feed_id': coordinator.feed, 'device': coordinator.device,
                         'names': {name for name, device in names.items() if device == coordinator.device}})
    parsed = await hass.async_add_executor_job(parser, source)
    points = parsed['positions']
    plan = plan_import(points, vehicles, data.get('device_mapping'), data.get('feed_mapping'),
                       data.get('feed_id'), data.get('entry_id'))
    destinations = []
    for entry_id, positions in plan.items():
        target = by_entry[entry_id]
        added = await hass.async_add_executor_job(target.store.insert, target.feed, positions)
        destinations.append({'entry_id': entry_id, 'feed_id': target.feed, 'device': target.device,
                             'valid':len(positions), 'added':added, 'duplicates':len(positions)-added})
    stores = {by_entry[entry_id].feed: by_entry[entry_id].store for entry_id in plan}
    for feed, store in stores.items():
        latest = await hass.async_add_executor_job(store.latest, feed)
        # Other vehicles on the same feed see the new history too.
        for coordinator in coordinators:
            if coordinator.feed == feed:
                coordinator.async_set_latest(latest)
    timestamps = [p['time'] for p in points]
    return {'filename':source.name, 'total':parsed['total'], 'valid':len(points),
            'added':sum(d['added'] for d in destinations),
            'duplicates':sum(d['duplicates'] for d in destinations), 'skipped':parsed['skipped'],
            'start_time':datetime.fromtimestamp(min(timestamps),timezone.utc).isoformat() if timestamps else None,
            'end_time':datetime.fromtimestamp(max(timestamps),timezone.utc).isoformat() if timestamps else None,
            'destinations':destinations}
