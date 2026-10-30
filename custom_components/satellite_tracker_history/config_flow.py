"""Config and options flows for Satellite Tracker History."""
from __future__ import annotations

from datetime import datetime, timezone
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import FEED_NOT_FOUND, SpotAPI, SpotFeedError
from .const import (CONF_DEVICE, CONF_FEED_ID, CONF_ICON, CONF_MAPSHARE, CONF_NAME, CONF_PASSWORD, CONF_PROVIDER,
                    DOMAIN, LEGACY_DOMAIN, PROVIDER_GARMIN, PROVIDER_SPOT)
from .coordinator import BACKFILL
from .garmin import NOT_FOUND, GarminAPI, GarminFeedError, mapshare_name
from .store import async_get_store
from .vehicle import archive_feed, provider, vehicle_unique_id


def _password_selector():
    return selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


def _clean_options(user_input):
    """Keep only the name and icon the user filled in; empty means use the default."""
    return {key: user_input[key].strip() for key in (CONF_NAME, CONF_ICON) if user_input.get(key, "").strip()}


async def _async_validate(hass, provider_name, feed_id, password):
    """Make one test request; return (errors, description placeholders, positions)."""
    try:
        if provider_name == PROVIDER_GARMIN:
            # A MapShare lists only its latest points unless asked for history.
            points = await GarminAPI(hass, feed_id, password).fetch(datetime.now(timezone.utc) - BACKFILL)
        else:
            points = await SpotAPI(hass, feed_id, password).page()
    except SpotFeedError as exc:
        if exc.code == FEED_NOT_FOUND:
            return {CONF_FEED_ID: "feed_not_found"}, {}, []
        # Includes rejected passwords; SPOT's own explanation is the most useful detail.
        return {"base": "feed_rejected"}, {"spot_error": exc.text}, []
    except GarminFeedError as exc:
        if exc.reason == NOT_FOUND:
            return {CONF_MAPSHARE: "mapshare_not_found"}, {}, []
        return {"base": "mapshare_rejected"}, {}, []
    except Exception:  # noqa: BLE001 - network and parse failures are presented as a flow error
        return {"base": "cannot_connect"}, {}, []
    return {}, {}, points


class SpotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one vehicle: a tracker in a SPOT feed or a Garmin MapShare."""

    # Version 1 entries were whole feeds; __init__.async_migrate_entry splits them into vehicles.
    VERSION = 2

    def __init__(self) -> None:
        self._feed: dict[str, str] = {}
        self._devices: dict[str, str] = {}

    async def async_step_user(self, user_input=None):
        # Home Assistant does not load this integration at startup until it has entries, so adding
        # it is where vehicles still under its old name are found.
        if self.hass.config_entries.async_entries(LEGACY_DOMAIN):
            return await self.async_step_legacy()
        return self.async_show_menu(step_id="user", menu_options=[PROVIDER_SPOT, PROVIDER_GARMIN])

    async def async_step_legacy(self, user_input=None):
        """Bring over the vehicles set up under the integration's old name."""
        if LEGACY_DOMAIN in self.hass.config.components:
            return self.async_abort(reason="legacy_installed")
        if user_input is None:
            count = len(self.hass.config_entries.async_entries(LEGACY_DOMAIN))
            return self.async_show_form(step_id="legacy", description_placeholders={"count": str(count)})
        from . import async_take_over_legacy  # noqa: PLC0415 - the integration imports this module
        created = await async_take_over_legacy(self.hass)
        return self.async_abort(reason="legacy_imported", description_placeholders={"count": str(created)})

    async def async_step_spot(self, user_input=None):
        """A SPOT shared feed, by its feed ID."""
        return await self._async_feed_step(PROVIDER_SPOT, CONF_FEED_ID, user_input,
                                           lambda value: value.strip() or None, "feed_not_found")

    async def async_step_garmin(self, user_input=None):
        """A Garmin inReach MapShare, by its name or any MapShare link."""
        return await self._async_feed_step(PROVIDER_GARMIN, CONF_MAPSHARE, user_input, mapshare_name,
                                           "mapshare_invalid")

    async def _async_feed_step(self, provider_name, field, user_input, parse, invalid):
        errors, placeholders = {}, {}
        if user_input is not None:
            feed_id = parse(user_input[field])
            password = user_input.get(CONF_PASSWORD, "")
            if feed_id is None:
                errors[field] = invalid
            else:
                errors, placeholders, points = await _async_validate(self.hass, provider_name, feed_id, password)
            if not errors:
                self._feed = {CONF_PROVIDER: provider_name, CONF_FEED_ID: feed_id, CONF_PASSWORD: password}
                # Offer devices heard from recently, most recent first and by their newest name,
                # then any others archived earlier.
                store = async_get_store(self.hass)
                archived = await self.hass.async_add_executor_job(store.list_devices, archive_feed(self._feed))
                self._devices = {}
                for point in sorted(points, key=lambda p: p["time"], reverse=True):
                    self._devices.setdefault(point["device"], point["name"])
                for device in archived:
                    self._devices.setdefault(device["device"], device["name"])
                return await self.async_step_vehicle()
        return self.async_show_form(
            step_id=provider_name,
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(field): str,
                        vol.Optional(CONF_PASSWORD, default=""): _password_selector(),
                    }
                ),
                {field: user_input[field]} if user_input else {},
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_vehicle(self, user_input=None):
        """Choose the device that is this vehicle's tracker, and optionally name it."""
        feed_id, archive = self._feed[CONF_FEED_ID], archive_feed(self._feed)
        configured = {entry.data.get(CONF_DEVICE) for entry in self._async_current_entries(include_ignore=False)
                      if archive_feed(entry.data) == archive}
        available = {device: name for device, name in self._devices.items() if device not in configured}
        errors = {}
        if user_input is not None:
            device = user_input[CONF_DEVICE].strip()
            if not device:
                errors[CONF_DEVICE] = "no_messenger"
            else:
                await self.async_set_unique_id(vehicle_unique_id(self._feed[CONF_PROVIDER], feed_id, device))
                self._abort_if_unique_id_configured()
                options = _clean_options(user_input)
                return self.async_create_entry(
                    title=options.get(CONF_NAME) or self._devices.get(device) or device,
                    data={**self._feed, CONF_DEVICE: device}, options=options,
                )
        choices = [selector.SelectOptionDict(value=device, label=f"{name} [{device}]" if name != device else device)
                   for device, name in available.items()]
        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema(
                {
                    # A quiet feed lists nothing, so the device ID can also be typed.
                    vol.Required(CONF_DEVICE): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=choices, custom_value=True,
                                                      mode=selector.SelectSelectorMode.DROPDOWN)
                    ),
                    vol.Optional(CONF_NAME, default=""): str,
                    vol.Optional(CONF_ICON, default=""): selector.IconSelector(),
                }
            ),
            errors=errors,
            description_placeholders={"feed_id": feed_id, "count": str(len(available))},
        )

    async def async_step_import(self, import_data):
        """Create a vehicle split from a version 1 feed entry, or taken over from the old domain."""
        feed_id, device = import_data["data"][CONF_FEED_ID], import_data["data"][CONF_DEVICE]
        await self.async_set_unique_id(vehicle_unique_id(provider(import_data["data"]), feed_id, device))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=import_data["title"], data=import_data["data"],
                                       options=import_data["options"])

    async def async_step_reconfigure(self, user_input=None):
        """Change the feed password; the feed and device key the archive and tracker, so they are fixed."""
        entry = self._get_reconfigure_entry()
        feed_id = entry.data[CONF_FEED_ID]
        errors, placeholders = {}, {}
        if user_input is not None:
            password = user_input.get(CONF_PASSWORD, "")
            errors, placeholders, _ = await _async_validate(self.hass, provider(entry.data), feed_id, password)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PASSWORD: password})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Optional(CONF_PASSWORD, default=""): _password_selector()}),
            errors=errors,
            description_placeholders={"feed_id": feed_id, **placeholders},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return SpotOptionsFlow()


class SpotOptionsFlow(config_entries.OptionsFlow):
    """Name a vehicle and choose its icon."""

    @staticmethod
    def _position_time(timestamp) -> str:
        """Display archived timestamps with an explicit timezone."""
        if timestamp is None:
            return "—"
        try:
            return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, OverflowError, OSError):
            return "—"

    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        feed_id, device = entry.data[CONF_FEED_ID], entry.data[CONF_DEVICE]
        # Read the archive directly so the vehicle stays manageable while its entry is unloaded.
        store = async_get_store(self.hass)
        archive = archive_feed(entry.data)
        summary = await self.hass.async_add_executor_job(store.device_summary, archive, device) or {}
        latest = (await self.hass.async_add_executor_job(store.latest, archive)).get(device, {})
        default_name = summary.get("name") or device
        if user_input is not None:
            options = {**{k: v for k, v in entry.options.items() if k not in (CONF_NAME, CONF_ICON)},
                       **_clean_options(user_input)}
            self.hass.config_entries.async_update_entry(entry, title=options.get(CONF_NAME) or default_name)
            return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Optional(CONF_NAME, default=""): str,
                        vol.Optional(CONF_ICON, default=""): selector.IconSelector(),
                    }
                ),
                {CONF_NAME: entry.options.get(CONF_NAME, ""), CONF_ICON: entry.options.get(CONF_ICON, "")},
            ),
            description_placeholders={
                "feed_id": feed_id,
                "device_id": device,
                "default_name": default_name,
                "message_count": str(summary.get("count", 0)),
                "first_position": self._position_time(summary.get("first")),
                "latest_position": self._position_time(summary.get("last")),
                "coordinates": (
                    f"{latest['lat']:.6f}, {latest['lon']:.6f}"
                    if latest.get("lat") is not None and latest.get("lon") is not None
                    else "—"
                ),
            },
        )
