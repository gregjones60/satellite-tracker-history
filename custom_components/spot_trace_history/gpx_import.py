"""Plan and perform GPX imports across independently configured feeds."""
from .gpx import parse_gpx


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
                    f'Cannot uniquely select a feed for GPX track {name!r}. '
                    'Provide feed_mapping from this track name to a configured feed ID.'
                )
            target = candidates[0]
            device = mapped_device or target['names'].get(name, name)
            destinations[name] = (target['entry_id'], device)
        target_id, device = destinations[name]
        remapped = {**point, 'device': device,
                    'id': f"gpx:{device}:{point['time']}:{point['lat']:.6f}:{point['lon']:.6f}"}
        plan.setdefault(target_id, []).append(remapped)
    return plan


async def async_import_gpx(hass, coordinators, source, data):
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
    points = await hass.async_add_executor_job(parse_gpx, source)
    plan = plan_import(points, feeds, data.get('device_mapping'), data.get('feed_mapping'),
                       data.get('feed_id'), data.get('entry_id'))
    for entry_id, positions in plan.items():
        target = by_entry[entry_id]
        await hass.async_add_executor_job(target.store.insert, target.feed, positions)
        target.async_set_updated_data(await hass.async_add_executor_job(target.store.latest, target.feed))
    return sum(len(positions) for positions in plan.values())
