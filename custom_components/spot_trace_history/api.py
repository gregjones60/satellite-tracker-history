"""SPOT public XML feed reader."""
import xml.etree.ElementTree as ET
from aiohttp import ClientTimeout
from urllib.parse import quote
from homeassistant.helpers.aiohttp_client import async_get_clientsession

REQUEST_TIMEOUT = ClientTimeout(total=30)

# SPOT error codes. A feed with no recent messages is reported as an error, not an empty list.
NO_MESSAGES = 'E-0195'
FEED_NOT_FOUND = 'E-0160'


class SpotAPIError(Exception):
    """Feed request failure whose message never includes the request URL or password."""


class SpotFeedError(ValueError):
    """SPOT answered with an error document, such as an unknown feed or rejected password."""

    def __init__(self, code, text):
        super().__init__('SPOT API error: ' + text)
        self.code = code
        self.text = text


class SpotAPI:
    def __init__(self, hass, feed, password):
        self.session = async_get_clientsession(hass)
        self.url = f"https://api.findmespot.com/spot-main-web/consumer/rest-api/2.0/public/feed/{quote(feed, safe='')}/message.xml"
        self.password = password

    async def page(self, start=1):
        params = {'start': start}
        if self.password:
            params['feedPassword'] = self.password
        try:
            async with self.session.get(self.url, params=params, timeout=REQUEST_TIMEOUT) as response:
                if response.status >= 400:
                    raise SpotAPIError(f'SPOT feed request failed with HTTP {response.status}')
                raw = await response.text()
        except SpotAPIError:
            raise
        except Exception as exc:
            # Client errors can embed the request URL, which carries the feed password.
            raise SpotAPIError(f'SPOT feed request failed: {type(exc).__name__}') from None
        root = ET.fromstring(raw)
        error = root.find('.//errors/error')
        if error is not None:
            code = error.findtext('code')
            if code == NO_MESSAGES:
                return []
            raise SpotFeedError(code, (error.findtext('text') or ''.join(error.itertext())).strip())
        items = []
        for msg in root.findall('.//messages/message'):
            def field(name):
                return msg.findtext(name)
            try:
                lat, lon = float(field('latitude')), float(field('longitude'))
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                device = field('messengerId')
                timestamp = int(field('unixTime'))
                if not device or timestamp <= 0:
                    continue
                items.append({'id': field('id') or f'{device}:{timestamp}', 'device': device,
                              'name': field('messengerName') or device, 'time': timestamp,
                              'lat': lat, 'lon': lon, 'type': field('messageType') or 'TRACK'})
            except (TypeError, ValueError):
                continue
        return items
