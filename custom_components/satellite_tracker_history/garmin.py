"""Garmin inReach MapShare KML feed reader.

A MapShare feed returns only each device's latest point unless asked for history with `d1`, a UTC start
time. Each position is a Placemark whose ExtendedData names its device by IMEI; the feed also contains a
track line, which is not a position. A MapShare password is sent as HTTP Basic auth with any user name.
"""
import base64
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import REQUEST_TIMEOUT, TrackerAPIError

FEED_URL = 'https://share.garmin.com/Feed/Share/{}'
KML = '{http://www.opengis.net/kml/2.2}'
MAPSHARE_NAME = re.compile(r'[A-Za-z0-9_.-]+')

# Reasons a feed was refused, for the config flow's errors.
NOT_FOUND = 'not_found'
REJECTED = 'rejected'


class GarminAPIError(TrackerAPIError):
    """MapShare request failure whose message never includes the password."""


class GarminFeedError(ValueError):
    """Garmin refused the MapShare: it does not exist, or its password is missing or wrong."""

    def __init__(self, reason, text):
        super().__init__('Garmin MapShare error: ' + text)
        self.reason = reason


def mapshare_name(value):
    """The MapShare name from a name or a MapShare, feed or loader link; None if there is none."""
    value = value.strip()
    if '/' in value:
        segments = [s for s in urlparse(value if '://' in value else 'https://' + value).path.split('/') if s]
        value = segments[-1] if segments else ''
    return value if MAPSHARE_NAME.fullmatch(value) else None


class GarminAPI:
    def __init__(self, hass, mapshare, password):
        self.session = async_get_clientsession(hass)
        self.url = FEED_URL.format(quote(mapshare, safe=''))
        self.password = password

    async def fetch(self, since=None):
        """Positions since `since` (a datetime), or only the latest ones when it is None."""
        params = {'d1': since.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} if since else {}
        # HTTP Basic auth with an empty user name; Garmin ignores the name.
        headers = ({'Authorization': 'Basic ' + base64.b64encode(f':{self.password}'.encode()).decode()}
                   if self.password else {})
        try:
            async with self.session.get(self.url, params=params, headers=headers,
                                        timeout=REQUEST_TIMEOUT) as response:
                if response.status == 401:
                    raise GarminFeedError(REJECTED, 'the MapShare password is missing or wrong')
                if response.status >= 400:
                    raise GarminAPIError(f'Garmin MapShare request failed with HTTP {response.status}')
                # Bytes, not text: the feed starts with a byte order mark.
                raw = await response.read()
        except (GarminFeedError, GarminAPIError):
            raise
        except Exception as exc:
            raise GarminAPIError(f'Garmin MapShare request failed: {type(exc).__name__}') from None
        # Garmin answers an unknown MapShare name with an empty page.
        if not raw.strip():
            raise GarminFeedError(NOT_FOUND, 'there is no MapShare with this name')
        return parse_kml(raw)


def _message_type(data):
    if data.get('In Emergency') == 'True':
        return 'EMERGENCY'
    return 'MESSAGE' if data.get('Text') else 'TRACK'


def parse_kml(raw):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # Garmin reports some request errors as a plain-text page.
        raise GarminAPIError('Garmin returned a page that is not a MapShare feed') from None
    items = []
    for placemark in root.iter(f'{KML}Placemark'):
        data = {d.get('name'): (d.findtext(f'{KML}value') or '').strip() for d in placemark.iter(f'{KML}Data')}
        device = data.get('IMEI')
        if not device or data.get('Valid GPS Fix') == 'False':
            continue
        try:
            lat, lon = float(data['Latitude']), float(data['Longitude'])
            # "Time UTC" is a 12-hour local-format string; the KML timestamp is ISO 8601.
            when = placemark.findtext(f'{KML}TimeStamp/{KML}when').strip()
            # A trailing Z means UTC; fromisoformat only accepts it from Python 3.11.
            when = datetime.fromisoformat(when[:-1] + '+00:00' if when.endswith('Z') else when)
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        timestamp = int((when if when.tzinfo else when.replace(tzinfo=timezone.utc)).timestamp())
        items.append({'id': data.get('Id') or f'{device}:{timestamp}', 'device': device,
                      'name': data.get('Map Display Name') or data.get('Name') or device, 'time': timestamp,
                      'lat': lat, 'lon': lon, 'type': _message_type(data)})
    return items
