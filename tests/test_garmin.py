"""Garmin MapShare KML parsing and requests, against a synthetic feed shaped like a real one."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

import custom_components.spot_trace_history.garmin as module
from custom_components.spot_trace_history.api import TrackerAPIError
from custom_components.spot_trace_history.garmin import (
    NOT_FOUND, REJECTED, GarminAPI, GarminAPIError, GarminFeedError, mapshare_name, parse_kml)

SAMPLE = (Path(__file__).parent / 'fixtures/garmin_mapshare.kml').read_bytes()


class Response:
    def __init__(self, body=b'', status=200):
        self.body = body
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def read(self):
        return self.body


def session(monkeypatch, response=None, error=None):
    captured = {}

    class Session:
        def get(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            if error:
                raise error
            return response

    monkeypatch.setattr(module, 'async_get_clientsession', lambda hass: Session())
    return captured


def test_positions_come_from_placemarks_with_a_valid_fix():
    positions = parse_kml(SAMPLE)
    # The invalid fix and the track line are not positions; the byte order mark is accepted.
    assert [p['id'] for p in positions] == ['900000001', '900000002', '900000004']
    assert positions[0] == {'id': '900000001', 'device': '300000000000001', 'name': 'Test Ute',
                            'time': int(datetime(2026, 10, 29, 20, tzinfo=timezone.utc).timestamp()),
                            'lat': -37.5, 'lon': 145.25, 'type': 'TRACK'}
    assert [p['type'] for p in positions] == ['TRACK', 'MESSAGE', 'EMERGENCY']
    assert positions[2]['device'] == '300000000000002'


def test_a_feed_with_no_points_has_no_positions():
    assert parse_kml(b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document/></kml>') == []


@pytest.mark.parametrize('value', ['6Q2XE7DS42', ' 6Q2XE7DS42 ', 'https://share.garmin.com/6Q2XE7DS42',
                                   'share.garmin.com/6Q2XE7DS42/', 'https://share.garmin.com/Feed/Share/6Q2XE7DS42',
                                   'https://share.garmin.com/Feed/ShareLoader/6Q2XE7DS42?d1=2026-01-01',
                                   'https://aus-share.explore.garmin.com/Feed/Share/6Q2XE7DS42'])
def test_mapshare_name_from_a_name_or_any_link(value):
    assert mapshare_name(value) == '6Q2XE7DS42'


@pytest.mark.parametrize('value', ['', 'two words', 'https://share.garmin.com/', 'name?x'])
def test_mapshare_name_rejects_anything_else(value):
    assert mapshare_name(value) is None


@pytest.mark.asyncio
async def test_history_is_requested_from_a_utc_start_time_with_the_password_as_basic_auth(monkeypatch):
    captured = session(monkeypatch, Response(SAMPLE))
    since = datetime(2026, 10, 30, 9, 30, tzinfo=timezone(__import__('datetime').timedelta(hours=10)))
    positions = await GarminAPI(Mock(), 'My Share', 'secret').fetch(since)
    assert len(positions) == 3
    assert captured['url'] == 'https://share.garmin.com/Feed/Share/My%20Share'
    assert captured['params'] == {'d1': '2026-10-29T23:30:00Z'}
    assert captured['headers'] == {'Authorization': 'Basic ' + __import__('base64').b64encode(b':secret').decode()}
    assert captured['timeout'].total == 30


@pytest.mark.asyncio
async def test_without_a_start_time_or_password_neither_is_sent(monkeypatch):
    captured = session(monkeypatch, Response(SAMPLE))
    await GarminAPI(Mock(), 'share', '').fetch()
    assert captured['params'] == {}
    assert captured['headers'] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(('response', 'reason'), [(Response(status=401), REJECTED), (Response(b' \n'), NOT_FOUND)])
async def test_refused_mapshares_say_why(monkeypatch, response, reason):
    session(monkeypatch, response)
    with pytest.raises(GarminFeedError) as caught:
        await GarminAPI(Mock(), 'share', 'secret').fetch()
    assert caught.value.reason == reason
    assert isinstance(caught.value, ValueError)


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [Response(status=500), Response(b'An error occured.')])
async def test_server_errors_and_error_pages_are_api_errors(monkeypatch, response):
    session(monkeypatch, response)
    with pytest.raises(GarminAPIError) as caught:
        await GarminAPI(Mock(), 'share', 'secret').fetch()
    assert isinstance(caught.value, TrackerAPIError)


@pytest.mark.asyncio
async def test_client_errors_are_sanitized(monkeypatch):
    session(monkeypatch, error=OSError('failed for https://:secret@share.garmin.com/Feed/Share/share'))
    with pytest.raises(GarminAPIError) as caught:
        await GarminAPI(Mock(), 'share', 'secret').fetch()
    assert 'secret' not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
