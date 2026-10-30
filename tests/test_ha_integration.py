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

from custom_components.satellite_tracker_history.const import DOMAIN  # noqa: E402

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


def add_entry(hass, feed, device="vehicle", password="", options=None, title=None):
    """A version 2 entry: one vehicle, the messenger `device` in `feed`."""
    entry = MockConfigEntry(domain=DOMAIN, version=2, unique_id=f"spot:{feed}:{device}", title=title or device,
                            data={"feed_id": feed, "password": password, "device": device}, options=options or {})
    entry.add_to_hass(hass)
    return entry


def feed_entry(hass, feed, options=None):
    """A version 1 entry: a whole feed, as created before vehicles had their own entries."""
    entry = MockConfigEntry(domain=DOMAIN, version=1, unique_id=feed, title=f"SPOT {feed[-6:]}",
                            data={"feed_id": feed, "password": "pw"}, options=options or {})
    entry.add_to_hass(hass)
    return entry


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def tracker_id(hass, feed, device):
    return er.async_get(hass).async_get_entity_id("device_tracker", DOMAIN, f"{feed}_{device}")


async def test_entry_creates_tracker_device_and_archive(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.5, 145.25),
                                                                ("trailer", "Camper", 100, -38.0, 146.0)))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert (entry.runtime_data.feed, entry.runtime_data.device) == ("feed-a", "vehicle")
    state = hass.states.get(tracker_id(hass, "feed-a", "vehicle"))
    assert state.attributes["latitude"] == -37.5
    assert state.attributes["longitude"] == 145.25
    assert state.attributes["messenger_id"] == "vehicle"
    # Only this vehicle gets a tracker, but the whole feed is archived.
    assert hass.states.async_entity_ids("device_tracker") == [state.entity_id]
    assert {d["device"] for d in hass.data[DOMAIN].list_devices("feed-a")} == {"vehicle", "trailer"}
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, "feed-a_vehicle"), entry.entry_id)
    assert device.manufacturer == "SPOT"
    assert (config_dir / "satellite_tracker_history.sqlite").is_file()


async def test_vehicles_on_one_feed_share_each_poll(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0),
                                                                ("trailer", "Camper", 200, -38.0, 146.0)))
    vehicle, trailer = add_entry(hass, "feed-a"), add_entry(hass, "feed-a", "trailer")
    await setup(hass, vehicle)
    assert trailer.state is ConfigEntryState.LOADED
    assert aioclient_mock.call_count == 1
    assert hass.states.get(tracker_id(hass, "feed-a", "trailer")).attributes["latitude"] == -38.0
    # Once the shared fetch is stale, the next refresh fetches again.
    from custom_components.satellite_tracker_history import coordinator as module
    vehicle.runtime_data.poller._fetched -= module.FRESH_SECONDS
    await vehicle.runtime_data.async_refresh()
    await trailer.runtime_data.async_refresh()
    assert aioclient_mock.call_count == 2


async def test_a_wrong_password_on_one_vehicle_does_not_affect_another(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0)))
    good, bad = add_entry(hass, "feed-a", password="right"), add_entry(hass, "feed-a", "trailer", password="wrong")
    await setup(hass, good)
    assert good.runtime_data.poller is not bad.runtime_data.poller
    assert bad.runtime_data.poller.api.password == "wrong"


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
    urls = [url for url in hass.data[DATA_EXTRA_MODULE_URL].urls if "satellite-tracker-history-card.js" in url]
    assert len(urls) == 1

    # Reloading one vehicle must not re-register domain-wide actions or commands.
    assert await hass.config_entries.async_reload(first.entry_id)
    await hass.async_block_till_done()
    assert first.state is ConfigEntryState.LOADED
    assert hass.services.has_service(DOMAIN, "import_gpx")


async def test_bundled_leaflet_is_served_at_the_version_the_card_requests(hass, config_dir, aioclient_mock, hass_client):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml())
    await setup(hass, add_entry(hass, "feed-a"))
    client = await hass_client()
    card = await (await client.get("/satellite_tracker_history/satellite-tracker-history-card.js")).text()
    for name, content in (("leaflet-src.esm.js", "Leaflet 1.9.4"), ("leaflet.css", ".leaflet-container")):
        response = await client.get(f"/satellite_tracker_history/leaflet/{name}?v=1.9.4")
        assert response.status == 200
        assert content in await response.text()
    assert "LEAFLET_VERSION='1.9.4'" in card
    assert (await client.get("/satellite_tracker_history/leaflet/../manifest.json")).status == 404


async def test_device_list_has_each_vehicle_with_its_name_and_icon(hass, config_dir, aioclient_mock, hass_ws_client):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0),
                                                                ("trailer", "Camper", 200, -38.0, 146.0),
                                                                ("spare", "Spare", 300, -39.0, 147.0)))
    await setup(hass, add_entry(hass, "feed-a"))
    add_entry(hass, "feed-a", "trailer", options={"name": "Touring trailer", "icon": "mdi:caravan"})
    await hass.config_entries.async_setup(hass.config_entries.async_entries(DOMAIN)[1].entry_id)
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "satellite_tracker_history/devices"})
    response = await client.receive_json()
    # The spare messenger is archived but is not a configured vehicle.
    assert {d["device"]: (d["name"], d["icon"]) for d in response["result"]} == {
        "vehicle": ("Bluey", None), "trailer": ("Touring trailer", "mdi:caravan")}


async def test_unload_keeps_archive_and_stops_listing_vehicle(hass, config_dir, aioclient_mock, hass_ws_client):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0)))
    aioclient_mock.get(FEED_URL.format("feed-b"), text=feed_xml(("trailer", "Camper", 200, -38.0, 146.0)))
    first, second = add_entry(hass, "feed-a"), add_entry(hass, "feed-b", "trailer")
    await setup(hass, first)
    assert second.state is ConfigEntryState.LOADED
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "satellite_tracker_history/devices"})
    response = await client.receive_json()
    assert {(d["feed_id"], d["device"]) for d in response["result"]} == {
        ("feed-a", "vehicle"), ("feed-b", "trailer"),
    }

    assert await hass.config_entries.async_unload(second.entry_id)
    await hass.async_block_till_done()
    assert second.state is ConfigEntryState.NOT_LOADED
    await client.send_json_auto_id({"type": "satellite_tracker_history/devices"})
    response = await client.receive_json()
    assert [d["feed_id"] for d in response["result"]] == ["feed-a"]

    await client.send_json_auto_id({"type": "satellite_tracker_history/track", "entry_id": second.entry_id,
                                    "device": "trailer", "start": 0, "end": 1000})
    response = await client.receive_json()
    assert response["error"]["code"] == "not_found"
    # History is archived independently of config entries.
    assert hass.data[DOMAIN].list_devices("feed-b")[0]["device"] == "trailer"


async def test_track_command_returns_only_the_vehicles_positions(hass, config_dir, aioclient_mock, hass_ws_client):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(
        ("vehicle", "Bluey", 100, -37.0, 145.0), ("vehicle", "Bluey", 200, -37.1, 145.1),
        ("trailer", "Camper", 150, -38.0, 146.0)))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "satellite_tracker_history/track", "entry_id": entry.entry_id,
                                    "device": "vehicle", "start": 0, "end": 1000})
    response = await client.receive_json()
    assert [p["time"] for p in response["result"]] == [100, 200]
    # Another messenger in the same feed is not this vehicle's history.
    await client.send_json_auto_id({"type": "satellite_tracker_history/track", "entry_id": entry.entry_id,
                                    "device": "trailer", "start": 0, "end": 1000})
    response = await client.receive_json()
    assert response["error"]["code"] == "not_found"


async def test_feed_failure_retries_setup_without_logging_password(hass, config_dir, aioclient_mock, caplog):
    aioclient_mock.get(FEED_URL.format("feed-a"), status=500)
    entry = add_entry(hass, "feed-a", password="hunter2-secret")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "HTTP 500" in caplog.text
    assert "hunter2-secret" not in caplog.text


async def test_quiet_feed_loads_with_a_tracker_awaiting_its_first_fix(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=(
        "<response><errors><error><code>E-0195</code><text>No Messages to display</text>"
        "</error></errors></response>"))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get(tracker_id(hass, "feed-a", "vehicle"))
    assert state.state == "unknown"
    assert state.attributes["messenger_id"] == "vehicle"


async def test_options_flow_names_the_vehicle_and_chooses_its_icon(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0)))
    entry = add_entry(hass, "feed-a", title="Bluey")
    await setup(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    placeholders = result["description_placeholders"]
    assert (placeholders["device_id"], placeholders["default_name"], placeholders["message_count"]) == (
        "vehicle", "Bluey", "1")
    assert placeholders["coordinates"] == "-37.000000, 145.000000"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": " Touring vehicle ", "icon": "mdi:car"})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options == {"name": "Touring vehicle", "icon": "mdi:car"}
    assert entry.title == "Touring vehicle"
    state = hass.states.get(tracker_id(hass, "feed-a", "vehicle"))
    assert state.attributes["friendly_name"] == "Touring vehicle"
    assert state.attributes["icon"] == "mdi:car"

    # Clearing both restores SPOT's name and the default icon.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"name": "", "icon": ""})
    await hass.async_block_till_done()
    assert entry.options == {}
    assert entry.title == "Bluey"
    assert "icon" not in hass.states.get(tracker_id(hass, "feed-a", "vehicle")).attributes


async def start_flow(hass, service="spot"):
    """Open the add-vehicle flow and choose the tracker service from its menu."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "menu"
    assert result["menu_options"] == ["spot", "garmin"]
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": service})


async def add_vehicle(hass, feed_id, device, **fields):
    result = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"feed_id": feed_id})
    assert result["step_id"] == "vehicle", result
    return result, await hass.config_entries.flow.async_configure(result["flow_id"], {"device": device, **fields})


async def test_config_flow_adds_each_messenger_as_its_own_vehicle(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-new"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0),
                                                                  ("trailer", "Camper", 200, -38.0, 146.0)))
    form, result = await add_vehicle(hass, "feed-new", "trailer", name="Touring trailer", icon="mdi:caravan")
    choices = form["data_schema"].schema["device"].config
    assert [o["value"] for o in choices["options"]] == ["trailer", "vehicle"]
    assert choices["custom_value"] is True
    assert result["type"] == "create_entry"
    assert result["title"] == "Touring trailer"
    assert result["data"] == {"provider": "spot", "feed_id": "feed-new", "password": "", "device": "trailer"}
    assert result["options"] == {"name": "Touring trailer", "icon": "mdi:caravan"}
    assert result["result"].unique_id == "spot:feed-new:trailer"
    await hass.async_block_till_done()

    # The same feed lists only the messenger not set up yet, and makes a second vehicle.
    form, result = await add_vehicle(hass, "feed-new", "vehicle")
    assert [o["value"] for o in form["data_schema"].schema["device"].config["options"]] == ["vehicle"]
    assert (result["type"], result["title"], result["options"]) == ("create_entry", "Bluey", {})
    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2
    assert aioclient_mock.call_count == 3  # two flow checks, one shared poll


async def test_config_flow_rejects_a_vehicle_already_set_up(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0)))
    await setup(hass, add_entry(hass, "feed-a"))
    _, result = await add_vehicle(hass, "feed-a", " vehicle ")
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_quiet_feed_accepts_a_typed_messenger_id(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-q"), text=spot_error("E-0195", "No Messages to display"))
    form, result = await add_vehicle(hass, "feed-q", "0-123456")
    assert form["description_placeholders"]["count"] == "0"
    assert result["type"] == "create_entry"
    assert result["title"] == "0-123456"


async def test_config_flow_requires_a_messenger(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-q"), text=spot_error("E-0195", "No Messages to display"))
    _, result = await add_vehicle(hass, "feed-q", "  ")
    assert result["type"] == "form"
    assert result["errors"] == {"device": "no_messenger"}


async def test_config_flow_reports_unreadable_feed(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("bad-feed"), status=500)
    result = await start_flow(hass)
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
    aioclient_mock.get(FEED_URL.format("feed-new"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0)))
    result = await start_flow(hass)
    password = next(v for k, v in result["data_schema"].schema.items() if k == "password")
    assert password.config["type"] == "password"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"feed_id": "  feed-new\n", "password": "secret"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device": "vehicle"})
    assert result["type"] == "create_entry"
    assert result["data"] == {"provider": "spot", "feed_id": "feed-new", "password": "secret", "device": "vehicle"}


@pytest.mark.parametrize(("body", "errors", "placeholders"), [
    (spot_error("E-0160", "Feed Not Found"), {"feed_id": "feed_not_found"}, {}),
    (spot_error("E-0999", "Invalid password"), {"base": "feed_rejected"}, {"spot_error": "Invalid password"}),
])
async def test_config_flow_explains_spot_errors(hass, config_dir, aioclient_mock, body, errors, placeholders):
    aioclient_mock.get(FEED_URL.format("feed-x"), text=body)
    result = await start_flow(hass)
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
    assert entry.data == {"feed_id": "feed-a", "password": "new", "device": "vehicle"}
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not coordinator
    assert entry.runtime_data.poller.api.password == "new"


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
    entry = add_entry(hass, "feed-a", "0-123456")
    await setup(hass, entry)
    entity = er.async_get(hass).async_get(tracker_id(hass, "feed-a", "0-123456"))
    assert entity.has_entity_name
    assert entity.config_entry_id == entry.entry_id
    assert hass.states.get(entity.entity_id).attributes["friendly_name"] == "Bluey"
    device = dr.async_get(hass).async_get(entity.device_id)
    assert (device.name, device.manufacturer, device.serial_number) == ("Bluey", "SPOT", "0-123456")


async def test_only_leftover_devices_can_be_removed(hass, config_dir, aioclient_mock):
    from custom_components.satellite_tracker_history import async_remove_config_entry_device
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0)))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)
    devices = dr.async_get(hass)
    vehicle = devices.async_get_device_by_identifier((DOMAIN, "feed-a_vehicle"), entry.entry_id)
    leftover = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "feed-a_old")})
    # The vehicle's own device goes only with its entry.
    assert not await async_remove_config_entry_device(hass, entry, vehicle)
    assert await async_remove_config_entry_device(hass, entry, leftover)


async def test_feed_entry_splits_into_vehicles_keeping_identity_settings_and_history(
        hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 300, -37.0, 145.0),
                                                                ("trailer", "Camper", 300, -38.0, 146.0)))
    from custom_components.satellite_tracker_history.store import async_get_store
    store = async_get_store(hass)
    store.insert("feed-a", [
        {"id": f"old-{device}", "device": device, "name": name, "time": 100, "lat": -36.0, "lon": 144.0, "type": "TRACK"}
        for device, name in (("vehicle", "Bluey"), ("trailer", "Camper"), ("Beacon", "Beacon"))])
    trip = store.create_trip("Camping", "2026-01-01", "2026-01-10", [{"feed_id": "feed-a", "device": "trailer"}])
    entry = feed_entry(hass, "feed-a", options={"devices": {
        "vehicle": {"name": "Ute", "enabled": False},
        "trailer": {"name": "Touring trailer", "enabled": True, "icon": "mdi:caravan"},
        "spare": {"name": "Spare", "enabled": True}}})
    # The registry as version 1 left it: both trackers' devices and entities belong to the feed entry.
    devices, entities = dr.async_get(hass), er.async_get(hass)
    for device in ("vehicle", "trailer"):
        made = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"feed-a_{device}")})
        entities.async_get_or_create("device_tracker", DOMAIN, f"feed-a_{device}", config_entry=entry,
                                     device_id=made.id, suggested_object_id=f"my_{device}")
    devices.async_update_device(devices.async_get_device_by_identifier(
        (DOMAIN, "feed-a_trailer"), entry.entry_id).id, area_id="garage")

    await setup(hass, entry)
    vehicles = {e.data["device"]: e for e in hass.config_entries.async_entries(DOMAIN)}
    assert set(vehicles) == {"vehicle", "trailer", "Beacon", "spare"}
    assert all(e.version == 2 and e.state is ConfigEntryState.LOADED for e in vehicles.values())
    # An enabled messenger keeps the original entry; a switched-off one gets a new entry.
    assert vehicles["trailer"] is entry
    assert entry.unique_id == "spot:feed-a:trailer"
    assert (entry.title, entry.options) == ("Touring trailer", {"name": "Touring trailer", "icon": "mdi:caravan"})
    assert entry.data == {"feed_id": "feed-a", "password": "pw", "device": "trailer"}
    assert (vehicles["vehicle"].title, vehicles["vehicle"].options) == ("Ute", {"name": "Ute", "enabled": False})
    assert vehicles["Beacon"].title == "Beacon"
    assert {e.unique_id for e in vehicles.values()} == {f"spot:feed-a:{d}" for d in vehicles}

    for device, vehicle in vehicles.items():
        tracker = entities.async_get(tracker_id(hass, "feed-a", device))
        assert tracker.config_entry_id == vehicle.entry_id
        assert devices.async_get(tracker.device_id).config_entry_id == vehicle.entry_id
    # Entity IDs and areas survive, and a tracker that was switched off stays off.
    assert tracker_id(hass, "feed-a", "trailer") == "device_tracker.my_trailer"
    assert tracker_id(hass, "feed-a", "vehicle") == "device_tracker.my_vehicle"
    assert devices.async_get(entities.async_get("device_tracker.my_trailer").device_id).area_id == "garage"
    assert entities.async_get("device_tracker.my_vehicle").disabled is False  # it existed already
    assert entities.async_get(tracker_id(hass, "feed-a", "Beacon")).disabled is False
    # One device per vehicle, and none left behind on the original entry.
    assert [len(dr.async_entries_for_config_entry(devices, v.entry_id)) for v in vehicles.values()] == [1] * 4
    # No history or trips are touched.
    assert {d["device"]: d["count"] for d in store.list_devices("feed-a")} == {"vehicle": 2, "trailer": 2, "Beacon": 1}
    assert store.list_trips() == [trip]


async def test_switched_off_messenger_without_a_tracker_gets_a_disabled_one(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0),
                                                                ("trailer", "Camper", 100, -38.0, 146.0)))
    from custom_components.satellite_tracker_history.store import async_get_store
    async_get_store(hass).insert("feed-a", [{"id": f"old-{d}", "device": d, "name": d, "time": 50, "lat": -36.0,
                                             "lon": 144.0, "type": "TRACK"} for d in ("vehicle", "trailer")])
    entry = feed_entry(hass, "feed-a", options={"devices": {"vehicle": {"enabled": False}}})
    await setup(hass, entry)
    assert entry.data["device"] == "trailer"
    tracker = er.async_get(hass).async_get(tracker_id(hass, "feed-a", "vehicle"))
    assert tracker.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(tracker.entity_id) is None


async def test_feed_entry_with_no_known_messenger_explains_how_to_add_the_vehicle(hass, config_dir, aioclient_mock):
    entry = feed_entry(hass, "feed-empty")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 2
    assert entry.data["device"] is None
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert "feed-empty" in entry.reason and "add the vehicle again" in entry.reason
    assert aioclient_mock.call_count == 0


async def test_diagnostics_redact_feed_access_hardware_and_locations(hass, config_dir, aioclient_mock, hass_client):
    feed = "feed-secret-123456"
    aioclient_mock.get(FEED_URL.format(feed), text=feed_xml(
        ("0-8812345", "Bluey Van", 100, -37.5, 145.25), ("0-7754321", "Camper Trailer", 200, -38.25, 146.5)))
    entry = add_entry(hass, feed, "0-8812345", password="hunter2-secret", title="Touring Van",
                      options={"name": "Touring Van", "icon": "mdi:van-utility"})
    await setup(hass, entry)
    # A later failed poll whose SPOT error text echoes the feed ID.
    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL.format(feed), text=(
        f"<response><errors><error>Feed with Id: {feed} is unavailable</error></errors></response>"))
    entry.runtime_data.poller._fetched = None
    await entry.runtime_data.async_refresh()
    assert await async_setup_component(hass, "diagnostics", {})

    result = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = str(result)
    for secret in (feed, "123456", "hunter2-secret", "-37.5", "145.25", "-38.25",
                   "0-8812345", "0-7754321", "Bluey", "Camper", "Touring"):
        assert secret not in text, secret
    assert result["entry"]["data"] == {"feed_id": "**REDACTED**", "password": "**REDACTED**", "device": "**REDACTED**"}
    assert result["entry"]["options"] == {"name": "**REDACTED**", "icon": "mdi:van-utility"}
    assert result["coordinator"]["last_update_success"] is False
    assert result["coordinator"]["last_exception"] == "SPOT API error: Feed with Id: **REDACTED** is unavailable"
    # Only this vehicle's history is summarised, not the other messenger in the feed.
    assert result["archive"] == {"positions": 1, "first_position": "1970-01-01T00:01:40+00:00",
                                 "latest_position": "1970-01-01T00:01:40+00:00", "latest_message_type": "TRACK"}


async def test_import_action_error_is_translated_and_readable(hass, config_dir, aioclient_mock):
    from homeassistant.exceptions import HomeAssistantError
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml())
    await setup(hass, add_entry(hass, "feed-a"))
    with pytest.raises(HomeAssistantError, match="must have a supported extension") as caught:
        await hass.services.async_call(DOMAIN, "import_gpx", {"filename": "../outside.gpx"}, blocking=True)
    assert caught.value.translation_domain == DOMAIN
    assert caught.value.translation_key == "import_failed"


async def test_form_descriptions_use_exactly_the_placeholders_the_flows_supply(hass, config_dir, aioclient_mock):
    import json
    import re
    from pathlib import Path
    strings = json.loads((Path(__file__).resolve().parents[1] /
                          "custom_components/satellite_tracker_history/translations/en.json").read_text())
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 100, -37.0, 145.0)))
    entry = add_entry(hass, "feed-a")
    await setup(hass, entry)
    options = await hass.config_entries.options.async_init(entry.entry_id)
    form, _ = await add_vehicle(hass, "feed-a", "")
    reconfigure = await entry.start_reconfigure_flow(hass)
    for result, description in ((options, strings["options"]["step"]["init"]["description"]),
                                (form, strings["config"]["step"]["vehicle"]["description"]),
                                (reconfigure, strings["config"]["step"]["reconfigure"]["description"])):
        assert set(re.findall(r"\{(\w+)\}", description)) == set(result["description_placeholders"])


@pytest.mark.parametrize("timestamp", [None, 10**100])
def test_unavailable_or_unrepresentable_time_has_a_display_fallback(timestamp):
    from custom_components.satellite_tracker_history.config_flow import SpotOptionsFlow
    assert SpotOptionsFlow._position_time(timestamp) == "—"


GARMIN_URL = "https://share.garmin.com/Feed/Share/{}"
GARMIN_SAMPLE = (__import__("pathlib").Path(__file__).parent / "fixtures/garmin_mapshare.kml").read_bytes()
UTE, TRAILER = "300000000000001", "300000000000002"


def garmin_entry(hass, mapshare="TestShare", device=UTE, password=""):
    entry = MockConfigEntry(domain=DOMAIN, version=2, unique_id=f"garmin:{mapshare}:{device}", title=device,
                            data={"provider": "garmin", "feed_id": mapshare, "password": password, "device": device})
    entry.add_to_hass(hass)
    return entry


async def test_garmin_vehicle_is_set_up_from_a_mapshare_link(hass, config_dir, aioclient_mock):
    aioclient_mock.get(GARMIN_URL.format("TestShare"), content=GARMIN_SAMPLE)
    result = await start_flow(hass, "garmin")
    assert result["step_id"] == "garmin"
    password = next(v for k, v in result["data_schema"].schema.items() if k == "password")
    assert password.config["type"] == "password"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "mapshare": "https://share.garmin.com/Feed/ShareLoader/TestShare", "password": "pw"})
    assert result["step_id"] == "vehicle"
    # The most recently heard device is offered first.
    assert [o["value"] for o in result["data_schema"].schema["device"].config["options"]] == [TRAILER, UTE]
    # Setup asks for the last 30 days, since a MapShare otherwise lists only the latest points.
    assert "d1" in aioclient_mock.mock_calls[-1][1].query
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device": UTE})
    assert result["type"] == "create_entry"
    assert (result["title"], result["result"].unique_id) == ("Test Ute", f"garmin:TestShare:{UTE}")
    assert result["data"] == {"provider": "garmin", "feed_id": "TestShare", "password": "pw", "device": UTE}


@pytest.mark.parametrize(("response", "mapshare", "errors"), [
    ({"content": b""}, "TestShare", {"mapshare": "mapshare_not_found"}),
    ({"status": 401}, "TestShare", {"base": "mapshare_rejected"}),
    ({"text": "An error occured."}, "TestShare", {"base": "cannot_connect"}),
    ({"content": GARMIN_SAMPLE}, "https://share.garmin.com/", {"mapshare": "mapshare_invalid"}),
])
async def test_garmin_setup_explains_refused_mapshares(hass, config_dir, aioclient_mock, response, mapshare, errors):
    aioclient_mock.get(GARMIN_URL.format("TestShare"), **response)
    result = await start_flow(hass, "garmin")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"mapshare": mapshare})
    assert result["type"] == "form"
    assert result["errors"] == errors


async def test_garmin_tracker_polls_archives_and_names_by_imei(hass, config_dir, aioclient_mock):
    aioclient_mock.get(GARMIN_URL.format("TestShare"), content=GARMIN_SAMPLE)
    entry = garmin_entry(hass)
    await setup(hass, entry)
    assert entry.runtime_data.feed == "garmin:TestShare"
    state = hass.states.get(tracker_id(hass, "garmin:TestShare", UTE))
    # The newest valid fix, not the later point without a GPS fix.
    assert (state.attributes["latitude"], state.attributes["longitude"]) == (-37.6, 145.3)
    assert state.attributes["imei"] == UTE
    assert state.attributes["message_type"] == "MESSAGE"
    assert state.attributes["last_message"] == "2026-10-29T21:15:30+00:00"
    assert state.attributes["friendly_name"] == "Test Ute"
    entity = er.async_get(hass).async_get(state.entity_id)
    device = dr.async_get(hass).async_get(entity.device_id)
    assert (device.manufacturer, device.serial_number) == ("Garmin", UTE)
    archive = hass.data[DOMAIN]
    assert {d["device"] for d in archive.list_devices("garmin:TestShare")} == {UTE, TRAILER}
    assert archive.list_devices("TestShare") == []
    # The next poll resumes from the newest archived fix.
    entry.runtime_data.poller._fetched = None
    await entry.runtime_data.async_refresh()
    assert aioclient_mock.mock_calls[-1][1].query["d1"] == "2026-10-29T22:00:00Z"


async def test_garmin_and_spot_feeds_with_the_same_name_stay_apart(hass, config_dir, aioclient_mock):
    aioclient_mock.get(GARMIN_URL.format("shared-name"), content=GARMIN_SAMPLE)
    aioclient_mock.get(FEED_URL.format("shared-name"), text=feed_xml((UTE, "SPOT Ute", 100, -30.0, 140.0)))
    garmin, spot = garmin_entry(hass, "shared-name"), add_entry(hass, "shared-name", UTE)
    await setup(hass, garmin)
    assert spot.state is ConfigEntryState.LOADED
    assert garmin.runtime_data.poller is not spot.runtime_data.poller
    assert hass.states.get(tracker_id(hass, "shared-name", UTE)).attributes["latitude"] == -30.0
    assert hass.states.get(tracker_id(hass, "garmin:shared-name", UTE)).attributes["latitude"] == -37.6


async def test_garmin_diagnostics_redact_the_mapshare_and_imei(hass, config_dir, aioclient_mock, hass_client):
    aioclient_mock.get(GARMIN_URL.format("SecretShare"), content=GARMIN_SAMPLE)
    entry = garmin_entry(hass, "SecretShare", password="hunter2")
    await setup(hass, entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(GARMIN_URL.format("SecretShare"), status=500)
    entry.runtime_data.poller._fetched = None
    await entry.runtime_data.async_refresh()
    assert await async_setup_component(hass, "diagnostics", {})
    result = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    for secret in ("SecretShare", UTE, "hunter2", "-37.6", "Test Ute"):
        assert secret not in str(result), secret
    assert result["entry"]["data"]["provider"] == "garmin"
    assert result["coordinator"]["last_exception"] == "Garmin MapShare request failed with HTTP 500"


LEGACY = "spot_trace_history"


def legacy_registry(hass, entry, feed, device, area=None, object_id=None):
    """A tracker as the old integration registered it: its own platform, device and identifiers."""
    devices, entities = dr.async_get(hass), er.async_get(hass)
    made = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(LEGACY, f"{feed}_{device}")})
    if area:
        devices.async_update_device(made.id, area_id=area)
    return entities.async_get_or_create("device_tracker", LEGACY, f"{feed}_{device}", config_entry=entry,
                                        device_id=made.id, suggested_object_id=object_id or device)


async def test_old_vehicles_are_taken_over_with_their_entities_devices_and_archive(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 300, -37.0, 145.0)))
    from custom_components.satellite_tracker_history.store import Store
    old_archive = config_dir / "spot_trace_history.sqlite"
    Store(old_archive).insert("feed-a", [{"id": "old", "device": "vehicle", "name": "Bluey", "time": 100,
                                          "lat": -36.0, "lon": 144.0, "type": "TRACK"}])
    old = MockConfigEntry(domain=LEGACY, version=2, unique_id="spot:feed-a:vehicle", title="Ute",
                          data={"feed_id": "feed-a", "password": "pw", "device": "vehicle"},
                          options={"name": "Ute", "icon": "mdi:car"})
    old.add_to_hass(hass)
    tracker = legacy_registry(hass, old, "feed-a", "vehicle", area="garage", object_id="my_ute")
    aioclient_mock.get(GARMIN_URL.format("TestShare"), content=GARMIN_SAMPLE)
    old_garmin = MockConfigEntry(domain=LEGACY, version=2, unique_id=f"garmin:TestShare:{UTE}", title="Trailer",
                                 data={"provider": "garmin", "feed_id": "TestShare", "password": "", "device": UTE})
    old_garmin.add_to_hass(hass)

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.config_entries.async_entries(LEGACY) == []
    entry, garmin = sorted(hass.config_entries.async_entries(DOMAIN), key=lambda e: e.unique_id, reverse=True)
    assert entry.state is ConfigEntryState.LOADED
    assert (garmin.unique_id, garmin.state) == (f"garmin:TestShare:{UTE}", ConfigEntryState.LOADED)
    assert (entry.title, entry.unique_id) == ("Ute", "spot:feed-a:vehicle")
    assert entry.data == {"feed_id": "feed-a", "password": "pw", "device": "vehicle"}
    assert entry.options == {"name": "Ute", "icon": "mdi:car"}
    entities, devices = er.async_get(hass), dr.async_get(hass)
    moved = entities.async_get(tracker.entity_id)
    assert tracker.entity_id == "device_tracker.my_ute"
    assert (moved.platform, moved.config_entry_id, moved.unique_id) == (DOMAIN, entry.entry_id, "feed-a_vehicle")
    assert entities.async_get_entity_id("device_tracker", LEGACY, "feed-a_vehicle") is None
    assert "device_tracker.my_ute" in hass.states.async_entity_ids("device_tracker")
    device = devices.async_get(moved.device_id)
    assert (device.config_entry_id, device.identifiers, device.area_id) == (
        entry.entry_id, {(DOMAIN, "feed-a_vehicle")}, "garage")
    # The archive moved to its new name, history and all.
    assert not old_archive.exists() and (config_dir / "satellite_tracker_history.sqlite").is_file()
    assert hass.data[DOMAIN].list_devices("feed-a")[0]["count"] == 2


async def test_old_feed_entries_from_before_vehicles_are_split_while_taken_over(hass, config_dir, aioclient_mock):
    aioclient_mock.get(FEED_URL.format("feed-a"), text=feed_xml(("vehicle", "Bluey", 300, -37.0, 145.0),
                                                                ("trailer", "Camper", 300, -38.0, 146.0)))
    old = MockConfigEntry(domain=LEGACY, version=1, unique_id="feed-a", title="SPOT feed-a",
                          data={"feed_id": "feed-a", "password": ""},
                          options={"devices": {"vehicle": {"name": "Ute"}, "trailer": {"enabled": False}}})
    old.add_to_hass(hass)
    legacy_registry(hass, old, "feed-a", "vehicle")

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    vehicles = {e.data["device"]: e for e in hass.config_entries.async_entries(DOMAIN)}
    assert set(vehicles) == {"vehicle", "trailer"}
    assert vehicles["vehicle"].options == {"name": "Ute"}
    assert vehicles["trailer"].options == {"enabled": False}
    assert hass.config_entries.async_entries(LEGACY) == []
    assert er.async_get(hass).async_get(tracker_id(hass, "feed-a", "vehicle")).config_entry_id == (
        vehicles["vehicle"].entry_id)


async def test_nothing_is_taken_over_while_the_old_integration_is_installed(hass, config_dir, aioclient_mock):
    from homeassistant.helpers import issue_registry as ir
    old = MockConfigEntry(domain=LEGACY, version=2, unique_id="spot:feed-a:vehicle",
                          data={"feed_id": "feed-a", "password": "", "device": "vehicle"})
    old.add_to_hass(hass)
    legacy_registry(hass, old, "feed-a", "vehicle")
    hass.config.components.add(LEGACY)

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert hass.config_entries.async_entries(LEGACY) == [old]
    assert hass.config_entries.async_entries(DOMAIN) == []
    assert er.async_get(hass).async_get_entity_id("device_tracker", LEGACY, "feed-a_vehicle")
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "legacy_installed")
    assert (issue.translation_key, issue.severity) == ("legacy_installed", ir.IssueSeverity.ERROR)
    assert aioclient_mock.call_count == 0
