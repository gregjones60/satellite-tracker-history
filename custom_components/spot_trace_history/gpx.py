"""Parse SPOT Mapping Activity Report GPX exports without external dependencies."""
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {'g': 'http://www.topografix.com/GPX/1/1'}

def parse_gpx(path, device_ids=None, *, report=False):
    """Return feed-compatible positions; device_ids maps GPX track names to messenger IDs."""
    device_ids = device_ids or {}
    if Path(path).stat().st_size > 100 * 1024 * 1024:
        raise ValueError('GPX exceeds 100 MB; split the export into smaller files')
    root = ET.parse(path).getroot()
    if root.tag != '{http://www.topografix.com/GPX/1/1}gpx':
        raise ValueError('Expected a GPX 1.1 document')
    positions = []
    total = 0
    for track in root.findall('g:trk', NS):
        track_points = track.findall('.//g:trkpt', NS)
        total += len(track_points)
        name = (track.findtext('g:name', default='', namespaces=NS) or '').strip()
        if not name:
            continue
        device = device_ids.get(name, name)
        for pt in track_points:
            try:
                lat, lon = float(pt.attrib['lat']), float(pt.attrib['lon'])
                stamp = pt.findtext('g:time', namespaces=NS)
                if not stamp or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                time = int(datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp())
                if time <= 0:
                    continue
                positions.append({'id': f'gpx:{device}:{time}:{lat:.6f}:{lon:.6f}',
                                  'device': device, 'name': name, 'time': time,
                                  'lat': lat, 'lon': lon, 'type': 'TRACK'})
            except (KeyError, ValueError, OverflowError):
                continue
    if report:
        return {'positions': positions, 'total': total, 'skipped': total - len(positions)}
    return positions


def parse_gpx_report(path):
    return parse_gpx(path, report=True)
