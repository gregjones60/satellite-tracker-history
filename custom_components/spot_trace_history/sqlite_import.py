"""Read location history from the SPOT iOS app's SQLite export."""
from contextlib import closing
import math
from pathlib import Path
import sqlite3

from .gpx_import import async_import_history


def parse_spot_sqlite(path):
    """Return valid fixes without modifying the export or reading account data."""
    source = Path(path).resolve()
    positions = []
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            required = {
                'devices': {'pk', 'name'},
                'messages': {'device_pk', 'message_type_pk', 'public_key', 'latitude', 'longitude', 'unixtime'},
                'message_types': {'pk', 'api_key'},
            }
            for table, columns in required.items():
                if not columns.issubset({r[1] for r in db.execute(f'PRAGMA table_info({table})')}):
                    raise ValueError('Expected a SPOT iOS database with devices, messages, and message_types tables')
            devices = {}
            for device_id, name in db.execute('SELECT pk, name FROM devices'):
                name = (name or '').strip() or str(device_id)
                if name in devices.values():
                    raise ValueError('Source devices have duplicate names; give them distinct names before exporting')
                devices[device_id] = name
            types = dict(db.execute('SELECT pk, api_key FROM message_types'))
            rows = db.execute('SELECT device_pk, message_type_pk, public_key, latitude, longitude, unixtime FROM messages')
            for device_id, type_id, message_id, lat, lon, timestamp in rows:
                if device_id not in devices or type_id not in types:
                    raise ValueError('SPOT database contains messages with missing device or message-type records')
                try:
                    lat, lon = float(lat), float(lon)
                    seconds = float(timestamp)
                    if not (math.isfinite(seconds) and seconds > 0 and seconds.is_integer()
                            and -90 <= lat <= 90 and -180 <= lon <= 180):
                        continue
                    time = int(seconds)
                except (TypeError, ValueError, OverflowError):
                    continue
                name = devices[device_id]
                positions.append({'id': f'ios:{device_id}:{message_id}', 'device': str(device_id),
                                  'name': name, 'time': time, 'lat': lat, 'lon': lon,
                                  'type': types[type_id] or 'TRACK'})
    except sqlite3.Error as exc:
        raise ValueError('Could not read the SPOT iOS SQLite database; check the file and export format') from exc
    if not positions:
        raise ValueError('SPOT iOS database contains no valid location records')
    return positions


async def async_import_sqlite(hass, coordinators, source, data):
    """Import iOS fixes using the same feed routing as GPX history."""
    return await async_import_history(hass, coordinators, source, data, parse_spot_sqlite)
