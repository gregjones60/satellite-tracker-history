"""Entry lifecycle, entities, actions and WebSocket commands in a real Home Assistant instance."""
import pytest

pytest.importorskip("pytest_homeassistant_custom_component",
                    reason="needs pip install -r requirements_test.txt (Python 3.14)")

from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.helpers import device_registry as dr, entity_registry as er  # noqa: E402
from homeassistant.setup import async_setup_component  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402
from pytest_homeassistant_custom_component.components.diagnostics import (  # noqa: E402
    get_diagnostics_for_config_entry,
)

from custom_components.spot_trace_history.const import DOMAIN  # noqa: E402

pytestmark = pytest.mark.ha

FEED_URL = "https://api.findmespot.com/spot-main-web/consumer/rest-api/2.0/public/feed/{}/message.xml"


def feed_xml(*messages):
    body = "".join(
        f"<message><id>{device}-{time}</id><messengerId>{device}</messengerId>"
        f"<messengerName>{name}</messengerName><unixTime>{time}</unixTime>"
        f"<latitude>{lat}</latitude><longitude>{lon}</longitude><messageType>TRACK</messageType></message>"
        for device, name, time, lat, lon in messages
    )
    return f"<response><feedMessageResponse><messages>{body}</messages></feedMessageResponse></response>"


@pytest.fixture
def config_dir(hass, tmp_path):
    """Keep the archive out of the harness's shared testing config directory."""
    hass.config.config_dir = str(tmp_path)
    return tmp_path


def add_entry(hass, feed, password="", options=None):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=feed, title=f"SPOT {feed}",
                            data={"feed_id": feed, "password": password}, options=options or {})
    entry.add_to_hass(hass)
    return entry


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entry_creates_tracker_device_and_archive(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.5, 145.25)))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.feed == "feed-a"
    entity_id = er.async_get(hass).async_get_entity_id("device_tracker", DOMAIN, "feed-a_vehicle")
    state = hass.states.get(entity_id)
    assert state.attributes["latitude"] == -37.5
    assert state.attributes["longitude"] == 145.25
    assert state.attributes["messenger_id"] == "vehicle"
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, "feed-a_vehicle"), entry.entry_id)
    assert device.manufacturer == "SPOT"
    assert (config_dir / "spot_trace_history.sqlite").is_file()


async def test_bundled_card_and_domain_actions_registered_once(hass, config_dir, aioclient_mock):
    for feed in ("feed-a", "feed-b"):
        aioclient_mock.get(FEED_URL.format(feed), text=feed_xml())
    first, second = add_entry(hass, "feed-a"), add_entry(hass, "feed-b")
    # Setting up the domain loads every entry already added.
    await setup(hass, first)
    assert second.state is ConfigEntryState.LOADED

    assert hass.services.has_service(DOMAIN, "import_gpx")
    assert hass.services.has_service(DOMAIN, "import_sqlite")
    from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
    urls = [url for url in hass.data[DATA_EXTRA_MODULE_URL].urls if "spot-trace-history-card.js" in url]
    assert len(urls) == 1

    # Reloading one feed must not re-register domain-wide actions or commands.
    assert await hass.config_entries.async_reload(first.entry_id)
    await hass.async_block_till_done()
    assert first.state is ConfigEntryState.LOADED
    assert hass.services.has_service(DOMAIN, "import_gpx")


async def test_unload_keeps_archive_and_stops_listing_feed(hass, config_dir, aioclient_mock, hass_ws_client):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0)))
    aioclient_mock.get(FEED_URL.format("feed-b"), text=feed_xml(("trailer", "Camper", 200, -38.0, 146.0)))
    first, second = add_entry(hass, "feed-a"), add_entry(hass, "feed-b")
    await setup(hass, first)
    assert second.state is ConfigEntryState.LOADED
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "spot_trace_history/devices"})
    response = await client.receive_json()
    assert {(d["feed_id"], d["device"]) for d in response["result"]} == {
        ("feed-a", "vehicle"), ("feed-b", "trailer"),
    }

    assert await hass.config_entries.async_unload(second.entry_id)
    await hass.async_block_till_done()
    assert second.state is ConfigEntryState.NOT_LOADED
    await client.send_json_auto_id({"type": "spot_trace_history/devices"})
    response = await client.receive_json()
    assert [d["feed_id"] for d in response["result"]] == ["feed-a"]

    await client.send_json_auto_id({"type": "spot_trace_history/track", "entry_id": second.entry_id,
                                    "device": "trailer", "start": 0, "end": 1000})
    response = await client.receive_json()
    assert response["error"]["code"] == "not_found"
    # History is archived independently of config entries.
    assert hass.data[DOMAIN].list_devices("feed-b")[0]["device"] == "trailer"


async def test_track_command_returns_archived_positions(hass, config_dir, aioclient_mock, hass_ws_client):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(
        ("vehicle", "Bluey", 100, -37.0, 145.0), ("vehicle", "Bluey", 200, -37.1, 145.1)))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "spot_trace_history/track", "entry_id": entry.entry_id,
                                    "device": "vehicle", "start": 0, "end": 1000})
    response = await client.receive_json()
    assert [p["time"] for p in response["result"]] == [100, 200]


async def test_feed_failure_retries_setup_without_logging_password(hass, config_dir, aioclient_mock, caplog):
    aioclient_mock.get(FEED_URL.format("feed-a"), status=500)
    entry = add_entry(hass, "feed-a", password="hunter2-secret")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "HTTP 500" in caplog.text
    assert "hunter2-secret" not in caplog.text


async def test_quiet_feed_loads_with_no_trackers(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=(
        "<response><errors><error><code>E-0195</code><text>No Messages to display</text>"
        "</error></errors></response>"))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.async_entity_ids("device_tracker") == []


async def test_disabled_device_has_no_tracker_after_options_change(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(
        ("vehicle", "Bluey", 100, -37.0, 145.0), ("trailer", "Camper", 100, -38.0, 146.0)))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("device_tracker", DOMAIN, "feed-a_trailer")

    hass.config_entries.async_update_entry(entry, options={"devices": {"trailer": {"enabled": False}}})
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    trailer = registry.async_get_entity_id("device_tracker", DOMAIN, "feed-a_trailer")
    # The entity is not created, so HA reports the registry entry as unavailable rather than tracking it.
    assert hass.states.get(trailer) is None or hass.states.get(trailer).state == "unavailable"
    vehicle = registry.async_get_entity_id("device_tracker", DOMAIN, "feed-a_vehicle")
    assert hass.states.get(vehicle).state != "unavailable"


async def test_options_flow_lists_and_saves_device_settings(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0)))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "manage_devices"})
    assert result["step_id"] == "manage_devices"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"device": "vehicle"})
    assert result["step_id"] == "device"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Touring vehicle", "enabled": True, "icon": "mdi:car"})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["devices"]["vehicle"] == {"name": "Touring vehicle", "enabled": True, "icon": "mdi:car"}
    entity_id = er.async_get(hass).async_get_entity_id("device_tracker", DOMAIN, "feed-a_vehicle")
    assert hass.states.get(entity_id).attributes["friendly_name"] == "Touring vehicle"


async def test_config_flow_creates_entry_and_rejects_duplicates(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-new"), text=feed_xml())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"feed_id": "feed-new"})
    assert result["type"] == "create_entry"
    assert result["data"] == {"feed_id": "feed-new", "password": ""}
    await hass.async_block_till_done()

    calls = aioclient_mock.call_count
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"feed_id": " feed-new "})
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    # A duplicate is rejected before contacting SPOT.
    assert aioclient_mock.call_count == calls


async def test_config_flow_reports_unreadable_feed(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("bad-feed"), status=500)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"feed_id": "bad-feed"})
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_integration_setup_without_entries(hass, config_dir):
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert hass.services.has_service(DOMAIN, "import_gpx")


def spot_error(code, text):
    return f"<response><errors><error><code>{code}</code><text>{text}</text></error></errors></response>"


async def test_config_flow_masks_password_and_trims_feed_id(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-new"), text=feed_xml())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    password = next(v for k, v in result["data_schema"].schema.items() if k == "password")
    assert password.config["type"] == "password"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"feed_id": "  feed-new\n", "password": "secret"})
    assert result["type"] == "create_entry"
    assert result["data"] == {"feed_id": "feed-new", "password": "secret"}
    assert result["result"].unique_id == "feed-new"


@pytest.mark.parametrize(("body", "errors", "placeholders"), [
    (spot_error("E-0160", "Feed Not Found"), {"feed_id": "feed_not_found"}, {}),
    (spot_error("E-0999", "Invalid password"), {"base": "feed_rejected"}, {"spot_error": "Invalid password"}),
])
async def test_config_flow_explains_spot_errors(hass, config_dir, aioclient_mock, body, errors, placeholders):
    aioclient_mock.get(FEED_URL.format("feed-x"), text=body)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"feed_id": "feed-x", "password": "pw"})
    assert result["type"] == "form"
    assert result["errors"] == errors
    assert result["description_placeholders"] == placeholders
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_reconfigure_changes_password_and_reloads(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0)))
    entry = add_entry(hass, "feed-a", password="old")
    await setup(hass, entry)
    coordinator = entry.runtime_data

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    assert result["description_placeholders"]["feed_id"] == "feed-a"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new"})
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data == {"feed_id": "feed-a", "password": "new"}
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not coordinator
    assert entry.runtime_data.api.password == "new"


async def test_reconfigure_keeps_old_password_when_spot_rejects_new_one(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml())
    entry = add_entry(hass, "feed-a", password="old")
    await setup(hass, entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL.format("feed-a"), text=spot_error("E-0999", "Invalid password"))
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "wrong"})
    assert result["errors"] == {"base": "feed_rejected"}
    assert entry.data["password"] == "old"


async def test_tracker_is_named_by_its_device(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("0-123456", "Bluey", 100, -37.0, 145.0)))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)
    entity = er.async_get(hass).async_get(
        er.async_get(hass).async_get_entity_id("device_tracker", DOMAIN, "feed-a_0-123456"))
    assert entity.has_entity_name
    assert hass.states.get(entity.entity_id).attributes["friendly_name"] == "Bluey"
    device = dr.async_get(hass).async_get(entity.device_id)
    assert (device.name, device.manufacturer, device.serial_number) == ("Bluey", "SPOT", "0-123456")


async def test_only_disabled_devices_can_be_removed(hass, config_dir, aioclient_mock):
    from custom_components.spot_trace_history import async_remove_config_entry_device
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(
        ("vehicle", "Bluey", 100, -37.0, 145.0), ("trailer", "Camper", 100, -38.0, 146.0)))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)
    devices = dr.async_get(hass)
    vehicle = devices.async_get_device_by_identifier((DOMAIN, "feed-a_vehicle"), entry.entry_id)
    trailer = devices.async_get_device_by_identifier((DOMAIN, "feed-a_trailer"), entry.entry_id)
    assert not await async_remove_config_entry_device(hass, entry, trailer)

    hass.config_entries.async_update_entry(entry, options={"devices": {"trailer": {"enabled": False}}})
    await hass.async_block_till_done()
    assert not await async_remove_config_entry_device(hass, entry, vehicle)
    assert await async_remove_config_entry_device(hass, entry, trailer)
    # Removing a device never touches its archived history.
    assert {d["device"] for d in hass.data[DOMAIN].list_devices("feed-a")} == {"vehicle", "trailer"}


async def test_diagnostics_redact_feed_access_hardware_and_locations(hass, config_dir, aioclient_mock, hass_client):
    feed = "feed-secret-123456"
    aioclient_mock.get(FEED_URL.format(feed), text=feed_xml(
        ("0-8812345", "Bluey Van", 100, -37.5, 145.25), ("0-7754321", "Camper Trailer", 200, -38.25, 146.5)))
    entry = add_entry(hass, feed, password="hunter2-secret", options={"devices": {
        "0-7754321": {"name": "Touring Trailer", "enabled": False, "icon": "mdi:caravan"},
        "0-6600000": {"name": "Old Beacon", "enabled": True},
    }})
    await setup(hass, entry)
    # A later failed poll whose SPOT error text echoes the feed ID.
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL.format(feed), text=(
        f"<response><errors><error>Feed with Id: {feed} is unavailable</error></errors></response>"))
    await entry.runtime_data.async_refresh()
    assert await async_setup_component(hass, "diagnostics", {})

    result = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = str(result)
    for secret in (feed, "123456", "hunter2-secret", "-37.5", "145.25", "-38.25",
                   "0-8812345", "0-7754321", "0-6600000", "Bluey", "Camper", "Touring", "Old Beacon"):
        assert secret not in text, secret
    assert result["entry"]["data"] == {"feed_id": "**REDACTED**", "password": "**REDACTED**"}
    assert result["coordinator"]["last_update_success"] is False
    assert result["coordinator"]["last_exception"] == "SPOT API error: Feed with Id: **REDACTED** is unavailable"
    # Archive entries are sorted by name; aliases link each one to its device settings.
    assert result["archive"] == [
        {"device": "device_1", "positions": 1, "first_position": "1970-01-01T00:01:40+00:00",
         "latest_position": "1970-01-01T00:01:40+00:00", "latest_message_type": "TRACK", "tracker_enabled": True},
        {"device": "device_2", "positions": 1, "first_position": "1970-01-01T00:03:20+00:00",
         "latest_position": "1970-01-01T00:03:20+00:00", "latest_message_type": "TRACK", "tracker_enabled": False},
    ]
    assert result["entry"]["options"]["devices"] == {
        "device_2": {"name": "**REDACTED**", "enabled": False, "icon": "mdi:caravan"},
        "device_3": {"name": "**REDACTED**", "enabled": True},
    }


async def test_import_action_error_is_translated_and_readable(hass, config_dir, aioclient_mock):
    from homeassistant.exceptions import HomeAssistantError
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml())
    await setup(hass, add_entry(hass, "feed-a"))
    with pytest.raises(HomeAssistantError, match="must have a supported extension") as caught:
        await hass.services.async_call(DOMAIN, "import_gpx", {"filename": "../outside.gpx"}, blocking=True)
    assert caught.value.translation_domain == DOMAIN
    assert caught.value.translation_key == "import_failed"
