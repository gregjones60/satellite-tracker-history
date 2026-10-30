"""Config and options flows for SPOT Trace History."""
from __future__ import annotations

from datetime import datetime, timezone
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import FEED_NOT_FOUND, SpotAPI, SpotFeedError
from .const import CONF_DEVICE, CONF_FEED_ID, CONF_ICON, CONF_NAME, CONF_PASSWORD, DOMAIN
from .device_tracker import vehicle_unique_id
from .store import async_get_store


def _password_selector():
    return selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


def _clean_options(user_input):
    """Keep only the name and icon the user filled in; empty means use the default."""
    return {key: user_input[key].strip() for key in (CONF_NAME, CONF_ICON) if user_input.get(key, "").strip()}


class SpotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one vehicle: a tracker in a SPOT feed."""

    # Version 1 entries were whole feeds; __init__.async_migrate_entry splits them into vehicles.
    VERSION = 2

    def __init__(self) -> None:
        self._feed: dict[str, str] = {}
        self._messengers: dict[str, str] = {}

    async def _async_validate(self, feed_id, password):
        """Make one test request; return (errors, description placeholders, positions)."""
        try:
            points = await SpotAPI(self.hass, feed_id, password).page()
        except SpotFeedError as exc:
            if exc.code == FEED_NOT_FOUND:
                return {CONF_FEED_ID: "feed_not_found"}, {}, []
            # Includes rejected passwords; SPOT's own explanation is the most useful detail.
            return {"base": "feed_rejected"}, {"spot_error": exc.text}, []
        except Exception:  # noqa: BLE001 - network and parse failures are presented as a flow error
            return {"base": "cannot_connect"}, {}, []
        return {}, {}, points

    async def async_step_user(self, user_input=None):
        errors, placeholders = {}, {}
        if user_input is not None:
            feed_id = user_input[CONF_FEED_ID].strip()
            password = user_input.get(CONF_PASSWORD, "")
            if not feed_id:
                errors[CONF_FEED_ID] = "feed_not_found"
            else:
                errors, placeholders, points = await self._async_validate(feed_id, password)
            if not errors:
                self._feed = {CONF_FEED_ID: feed_id, CONF_PASSWORD: password}
                # Offer messengers heard from recently or archived earlier; SPOT lists newest first,
                # so reading it oldest first lets each messenger's newest name win.
                store = async_get_store(self.hass)
                archived = await self.hass.async_add_executor_job(store.list_devices, feed_id)
                self._messengers = {point["device"]: point["name"] for point in reversed(points)}
                for device in archived:
                    self._messengers.setdefault(device["device"], device["name"])
                return await self.async_step_vehicle()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_FEED_ID): str,
                        vol.Optional(CONF_PASSWORD, default=""): _password_selector(),
                    }
                ),
                {CONF_FEED_ID: user_input[CONF_FEED_ID]} if user_input else {},
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_vehicle(self, user_input=None):
        """Choose the messenger that is this vehicle's tracker, and optionally name it."""
        feed_id = self._feed[CONF_FEED_ID]
        configured = {entry.data.get(CONF_DEVICE) for entry in self._async_current_entries(include_ignore=False)
                      if entry.data.get(CONF_FEED_ID) == feed_id}
        available = {device: name for device, name in self._messengers.items() if device not in configured}
        errors = {}
        if user_input is not None:
            device = user_input[CONF_DEVICE].strip()
            if not device:
                errors[CONF_DEVICE] = "no_messenger"
            else:
                await self.async_set_unique_id(vehicle_unique_id(feed_id, device))
                self._abort_if_unique_id_configured()
                options = _clean_options(user_input)
                return self.async_create_entry(
                    title=options.get(CONF_NAME) or self._messengers.get(device) or device,
                    data={**self._feed, CONF_DEVICE: device}, options=options,
                )
        choices = [selector.SelectOptionDict(value=device, label=f"{name} [{device}]" if name != device else device)
                   for device, name in available.items()]
        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema(
                {
                    # A quiet feed lists nothing, so the messenger ID can also be typed.
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
        """Create a vehicle split from a version 1 feed entry during migration."""
        feed_id, device = import_data["data"][CONF_FEED_ID], import_data["data"][CONF_DEVICE]
        await self.async_set_unique_id(vehicle_unique_id(feed_id, device))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=import_data["title"], data=import_data["data"],
                                       options=import_data["options"])

    async def async_step_reconfigure(self, user_input=None):
        """Change the feed password; the feed and messenger key the archive and tracker, so they are fixed."""
        entry = self._get_reconfigure_entry()
        feed_id = entry.data[CONF_FEED_ID]
        errors, placeholders = {}, {}
        if user_input is not None:
            password = user_input.get(CONF_PASSWORD, "")
            errors, placeholders, _ = await self._async_validate(feed_id, password)
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
        summary = await self.hass.async_add_executor_job(store.device_summary, feed_id, device) or {}
        latest = (await self.hass.async_add_executor_job(store.latest, feed_id)).get(device, {})
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
