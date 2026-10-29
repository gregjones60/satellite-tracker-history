"""Plan and perform GPX imports across independently configured feeds."""
from datetime import datetime, timezone
from .gpx import parse_gpx_report


def plan_import(points, feeds, device_mapping=None, feed_mapping=None, feed_id=None, entry_id=None):
    """Resolve every track before writing any positions; never guess a feed."""
    device_mapping = device_mapping or {}
    feed_mapping = feed_mapping or {}
    eligible = [f for f in feeds if (feed_id is None or f['feed_id'] == feed_id)
                and (entry_id is None or f['entry_id'] == entry_id)]
    if not eligible:
        raise ValueError('No matching configured SPOT feed')
    if (feed_id is not None or entry_id is not None) and len(eligible) != 1:
        raise ValueError('Specify entry_id to select one configured SPOT feed')
    plan = {}
    destinations = {}
    for point in points:
        name = point['name']
        if name not in destinations:
            mapped_device = device_mapping.get(name)
            candidates = eligible
            if name in feed_mapping:
                candidates = [f for f in eligible if f['feed_id'] == feed_mapping[name]]
            elif len(eligible) > 1:
                candidates = [f for f in eligible if (
                    mapped_device in f['devices'] if mapped_device is not None
                    else name in f['devices'] or name in f['names']
                )]
            if len(candidates) != 1:
                raise ValueError(
                    f'Cannot uniquely select a feed for source device/track {name!r}. '
                    'Provide feed_mapping from this name to a configured feed ID.'
                )
            target = candidates[0]
            device = mapped_device or target['names'].get(name, name)
            destinations[name] = (target['entry_id'], device)
        target_id, device = destinations[name]
        identifier = (point['id'] if point['id'].startswith('ios:') else
                      f"gpx:{device}:{point['time']}:{point['lat']:.6f}:{point['lon']:.6f}")
        remapped = {**point, 'device': device, 'id': identifier}
        plan.setdefault(target_id, []).append(remapped)
    return plan


async def async_import_gpx(hass, coordinators, source, data):
    return await async_import_history(hass, coordinators, source, data, parse_gpx_report)


async def async_import_history(hass, coordinators, source, data, parser):
    """Read once, validate all destinations, insert and refresh affected feeds."""
    feeds = []
    by_entry = {}
    for coordinator in coordinators:
        entry_id = coordinator.entry.entry_id
        by_entry[entry_id] = coordinator
        names = await hass.async_add_executor_job(coordinator.store.device_names, coordinator.feed)
        latest = await hass.async_add_executor_job(coordinator.store.latest, coordinator.feed)
        feeds.append({'entry_id': entry_id, 'feed_id': coordinator.feed,
                      'names': names, 'devices': set(latest)})
    parsed = await hass.async_add_executor_job(parser, source)
    points = parsed['positions']
    plan = plan_import(points, feeds, data.get('device_mapping'), data.get('feed_mapping'),
                       data.get('feed_id'), data.get('entry_id'))
    destinations = []
    for entry_id, positions in plan.items():
        target = by_entry[entry_id]
        added = await hass.async_add_executor_job(target.store.insert, target.feed, positions)
        destinations.append({'entry_id': entry_id, 'feed_id': target.feed, 'valid':len(positions),
                             'added':added, 'duplicates':len(positions)-added})
        target.async_set_updated_data(await hass.async_add_executor_job(target.store.latest, target.feed))
    timestamps = [p['time'] for p in points]
    return {'filename':source.name, 'total':parsed['total'], 'valid':len(points),
            'added':sum(d['added'] for d in destinations),
            'duplicates':sum(d['duplicates'] for d in destinations), 'skipped':parsed['skipped'],
            'start_time':datetime.fromtimestamp(min(timestamps),timezone.utc).isoformat() if timestamps else None,
            'end_time':datetime.fromtimestamp(max(timestamps),timezone.utc).isoformat() if timestamps else None,
            'destinations':destinations}
