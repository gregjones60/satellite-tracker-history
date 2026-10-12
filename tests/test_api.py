from unittest.mock import Mock
import pytest
from custom_components.spot_trace_history.api import SpotAPI


class Response:
    def __init__(self, body):
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def raise_for_status(self):
        pass

    async def text(self):
        return self.body


@pytest.mark.asyncio
async def test_xml_paging_and_validation(monkeypatch):
    import custom_components.spot_trace_history.api as module
    captured = {}
    xml = """<response><feedMessageResponse><messages>
    <message><id>1</id><messengerId>device1</messengerId><messengerName>Bluey</messengerName>
    <unixTime>100</unixTime><latitude>-37</latitude><longitude>145</longitude>
    <messageType>TRACK</messageType></message>
    <message><id>2</id><messengerId>device1</messengerId><unixTime>101</unixTime>
    <latitude>100</latitude><longitude>145</longitude></message>
    </messages></feedMessageResponse></response>"""
    class Session:
        def get(self, url, **kwargs):
            captured.update(kwargs)
            return Response(xml)
    monkeypatch.setattr(module, "async_get_clientsession", lambda hass: Session())
    api = SpotAPI(Mock(), "feed-123", "secret")
    records = await api.page(start=51)
    assert captured["params"] == {"start": 51, "feedPassword": "secret"}
    assert len(records) == 1
    assert records[0]["device"] == "device1"


@pytest.mark.asyncio
async def test_api_error_response(monkeypatch):
    import custom_components.spot_trace_history.api as module
    class Session:
        def get(self, *_args, **_kwargs):
            return Response("<response><errors><error>Bad feed</error></errors></response>")
    monkeypatch.setattr(module, "async_get_clientsession", lambda hass: Session())
    with pytest.raises(ValueError, match="Bad feed"):
        await SpotAPI(Mock(), "invalid", "").page()
