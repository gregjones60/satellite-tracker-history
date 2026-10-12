"""SPOT public XML feed reader."""
import asyncio
import xml.etree.ElementTree as ET
from urllib.parse import quote
from homeassistant.helpers.aiohttp_client import async_get_clientsession

class SpotAPI:
    def __init__(self, hass, feed, password):
        self.session = async_get_clientsession(hass)
        self.url = f"https://api.findmespot.com/spot-main-web/consumer/rest-api/2.0/public/feed/{quote(feed, safe='')}/message.xml"
        self.password = password

    async def page(self, start=1):
        params = {'start': start}
        if self.password:
            params['feedPassword'] = self.password
        async with self.session.get(self.url, params=params, timeout=30) as response:
            response.raise_for_status()
            raw = await response.text()
        root = ET.fromstring(raw)
        error = root.find('.//errors/error')
        if error is not None:
            raise ValueError('SPOT API error: ' + ''.join(error.itertext()))
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
