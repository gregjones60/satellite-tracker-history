"""Persistent GPS archive."""
import sqlite3
from pathlib import Path

class Store:
    def __init__(self, path):
        self.path = Path(path)

    def connect(self):
        db = sqlite3.connect(self.path)
        db.execute('CREATE TABLE IF NOT EXISTS positions (feed TEXT NOT NULL, id TEXT NOT NULL, device TEXT NOT NULL, name TEXT, time INTEGER NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, type TEXT, PRIMARY KEY(feed,id))')
        db.execute('CREATE INDEX IF NOT EXISTS position_lookup ON positions(feed,device,time)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS position_fix_dedupe ON positions(feed,device,time,lat,lon)')
        return db

    def insert(self, feed, points):
        with self.connect() as db:
            db.executemany('INSERT OR IGNORE INTO positions VALUES (?,?,?,?,?,?,?,?)',
                [(feed, p['id'], p['device'], p['name'], p['time'], p['lat'], p['lon'], p['type']) for p in points])

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
