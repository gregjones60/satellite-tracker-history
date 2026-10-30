"""Persistent GPS archive."""
import os
import sqlite3
import json
from contextlib import closing, contextmanager
from datetime import date
import re
from uuid import uuid4
from pathlib import Path

from .const import ARCHIVE_FILENAME, DOMAIN, LEGACY_ARCHIVE_FILENAME


SIDE_FILES = ('-wal', '-shm', '-journal')


def _rename_with_side_files(source, target):
    # SQLite's side files go first, so committed data never sits apart from its database.
    for suffix in SIDE_FILES:
        side = source.with_name(source.name + suffix)
        if side.exists():
            os.replace(side, target.with_name(target.name + suffix))
    os.replace(source, target)


def adopt_legacy_archive(path):
    """Bring in the archive kept under the integration's old name, next to `path`.

    If `path` does not exist yet the old archive is renamed to it. Otherwise (for example a setup form
    opened the new archive first) the old archive's positions and trips are merged in, skipping any
    already there, and the old file is kept as `<old name>.migrated`. Returns 'moved', 'merged' or None.
    """
    path = Path(path)
    old = path.with_name(LEGACY_ARCHIVE_FILENAME)
    if not old.exists():
        return None
    if not path.exists():
        _rename_with_side_files(old, path)
        return 'moved'
    with closing(sqlite3.connect(path)) as db:
        Store._create_schema(db)
        db.execute('ATTACH DATABASE ? AS legacy', (str(old),))
        try:
            with db:
                tables = {r[0] for r in db.execute("SELECT name FROM legacy.sqlite_master WHERE type='table'")}
                if 'positions' in tables:
                    db.execute('INSERT OR IGNORE INTO positions (feed,id,device,name,time,lat,lon,type) '
                               'SELECT feed,id,device,name,time,lat,lon,type FROM legacy.positions')
                if 'trips' in tables:
                    columns = {r[1] for r in db.execute('PRAGMA legacy.table_info(trips)')}
                    devices = 'devices' if 'devices' in columns else 'NULL'
                    # A trip whose name is already used in the new archive keeps the new one.
                    db.execute('INSERT OR IGNORE INTO trips (id,name,start_date,end_date,devices) '
                               f'SELECT id,name,start_date,end_date,{devices} FROM legacy.trips')
        finally:
            db.execute('DETACH DATABASE legacy')
    kept = old.with_name(old.name + '.migrated')
    number = 1
    while kept.exists():
        number += 1
        kept = old.with_name(f'{old.name}.migrated{number}')
    _rename_with_side_files(old, kept)
    return 'merged'


def async_get_store(hass):
    """Return the archive shared by every feed; it outlives config entries."""
    store = hass.data.get(DOMAIN)
    if store is None:
        store = hass.data[DOMAIN] = Store(hass.config.path(ARCHIVE_FILENAME))
    return store


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self._schema_ready = False

    @contextmanager
    def connect(self):
        """Yield a connection inside one transaction, then close it."""
        if not self._schema_ready and self.path.name == ARCHIVE_FILENAME:
            # Whoever opens the archive first, polling or a setup form, brings in the old one.
            adopt_legacy_archive(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            if not self._schema_ready:
                self._create_schema(db)
                self._schema_ready = True
            with db:
                yield db

    @staticmethod
    def _create_schema(db):
        db.execute('CREATE TABLE IF NOT EXISTS positions (feed TEXT NOT NULL, id TEXT NOT NULL, device TEXT NOT NULL, name TEXT, time INTEGER NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, type TEXT, PRIMARY KEY(feed,id))')
        db.execute('CREATE INDEX IF NOT EXISTS position_lookup ON positions(feed,device,time)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS position_fix_dedupe ON positions(feed,device,time,lat,lon)')
        db.execute('CREATE TABLE IF NOT EXISTS trips (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, start_date TEXT NOT NULL, end_date TEXT NOT NULL)')
        if 'devices' not in {row[1] for row in db.execute('PRAGMA table_info(trips)')}:
            try:
                db.execute('ALTER TABLE trips ADD COLUMN devices TEXT')
            except sqlite3.OperationalError as exc:
                if 'duplicate column name' not in str(exc):
                    raise
        db.commit()

    def list_trips(self):
        with self.connect() as db:
            rows = db.execute('SELECT id,name,start_date,end_date,devices FROM trips ORDER BY start_date DESC,name').fetchall()
        return [{'id':r[0], 'name':r[1], 'start_date':r[2], 'end_date':r[3],
                 'devices':json.loads(r[4]) if r[4] is not None else None} for r in rows]

    @staticmethod
    def _trip_devices(devices):
        if devices is None:
            return None
        if not isinstance(devices, list) or not devices:
            raise ValueError('Select at least one vehicle or choose all vehicles')
        result = []
        for device in devices:
            if (not isinstance(device, dict) or set(device) != {'feed_id', 'device'}
                    or not all(isinstance(v, str) and v.strip() for v in device.values())):
                raise ValueError('Trip vehicles require a feed ID and messenger ID')
            if device not in result:
                result.append(dict(device))
        return result

    @staticmethod
    def _validate_trip(name, start_date, end_date):
        name = name.strip()
        if not name or len(name) > 100:
            raise ValueError('Trip name must contain 1–100 characters')
        try:
            if not all(re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) for value in (start_date, end_date)):
                raise ValueError
            start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        except ValueError as exc:
            raise ValueError('Trip dates must be valid dates in YYYY-MM-DD format') from exc
        if end < start or (end - start).days >= 366:
            raise ValueError('Choose a trip period of 1–366 days')
        return name

    def create_trip(self, name, start_date, end_date, devices=None):
        name = self._validate_trip(name, start_date, end_date)
        devices = self._trip_devices(devices)
        trip = {'id': str(uuid4()), 'name': name, 'start_date': start_date, 'end_date': end_date, 'devices':devices}
        try:
            with self.connect() as db:
                db.execute('INSERT INTO trips (id,name,start_date,end_date,devices) VALUES (?,?,?,?,?)',
                           (trip['id'], name, start_date, end_date, json.dumps(devices) if devices is not None else None))
        except sqlite3.IntegrityError as exc:
            raise ValueError('A trip with this name already exists') from exc
        return trip

    def update_trip(self, trip_id, name, start_date, end_date, devices=...):
        name = self._validate_trip(name, start_date, end_date)
        if devices is not ...:
            devices = self._trip_devices(devices)
        try:
            with self.connect() as db:
                cursor = db.execute('UPDATE trips SET name=?,start_date=?,end_date=? WHERE id=?',
                                    (name, start_date, end_date, trip_id))
                if cursor.rowcount != 1:
                    raise KeyError('Trip not found; refresh the saved-trip list')
                if devices is not ...:
                    db.execute('UPDATE trips SET devices=? WHERE id=?',
                               (json.dumps(devices) if devices is not None else None, trip_id))
                stored = db.execute('SELECT devices FROM trips WHERE id=?', (trip_id,)).fetchone()[0]
        except sqlite3.IntegrityError as exc:
            raise ValueError('A trip with this name already exists') from exc
        return {'id': trip_id, 'name': name, 'start_date': start_date, 'end_date': end_date,
                'devices':json.loads(stored) if stored is not None else None}

    def delete_trip(self, trip_id):
        with self.connect() as db:
            if db.execute('DELETE FROM trips WHERE id=?', (trip_id,)).rowcount != 1:
                raise KeyError('Trip not found; refresh the saved-trip list')

    def insert(self, feed, points):
        with self.connect() as db:
            before = db.total_changes
            db.executemany('INSERT OR IGNORE INTO positions VALUES (?,?,?,?,?,?,?,?)',
                [(feed, p['id'], p['device'], p['name'], p['time'], p['lat'], p['lon'], p['type']) for p in points])
            return db.total_changes - before

    def device_names(self, feed):
        with self.connect() as db:
            rows = db.execute('SELECT device, name FROM positions WHERE feed=? ORDER BY time DESC', (feed,)).fetchall()
        names = {}
        for device, name in rows:
            if name:
                names.setdefault(name, device)
        return names

    def latest(self, feed):
        with self.connect() as db:
            rows = db.execute('SELECT p.device,p.name,p.time,p.lat,p.lon,p.type FROM positions p JOIN (SELECT device, MAX(time) AS t FROM positions WHERE feed=? GROUP BY device) q ON p.device=q.device AND p.time=q.t WHERE p.feed=? GROUP BY p.device', (feed,feed)).fetchall()
        return {r[0]: {'device':r[0], 'name':r[1], 'time':r[2], 'lat':r[3], 'lon':r[4], 'type':r[5]} for r in rows}

    def tracks(self, feed, device, start, end, limit=10000):
        with self.connect() as db:
            rows=db.execute('SELECT time,lat,lon,type FROM positions WHERE feed=? AND device=? AND time BETWEEN ? AND ? ORDER BY time LIMIT ?', (feed,device,start,end,limit)).fetchall()
        return [{'time':r[0], 'lat':r[1], 'lon':r[2], 'type':r[3]} for r in rows]

    def list_devices(self, feed):
        with self.connect() as db:
            rows = db.execute('''SELECT p.device, COALESCE((SELECT q.name FROM positions q
              WHERE q.feed=p.feed AND q.device=p.device AND q.name IS NOT NULL
              ORDER BY q.time DESC LIMIT 1), p.device), COUNT(*), MIN(p.time), MAX(p.time)
              FROM positions p WHERE p.feed=? GROUP BY p.device ORDER BY 2''', (feed,)).fetchall()
        return [{'device':r[0], 'name':r[1], 'count':r[2], 'first':r[3], 'last':r[4]} for r in rows]

    def latest_time(self, feed):
        """The time of the feed's newest archived position, or None."""
        with self.connect() as db:
            return db.execute('SELECT MAX(time) FROM positions WHERE feed=?', (feed,)).fetchone()[0]

    def device_summary(self, feed, device):
        """One device's entry from list_devices, or None if nothing is archived for it."""
        return next((d for d in self.list_devices(feed) if d['device'] == device), None)
