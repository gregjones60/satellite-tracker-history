"""Config and options flows for SPOT Trace History."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import FEED_NOT_FOUND, SpotAPI, SpotFeedError
from .const import CONF_DEVICES, CONF_ENABLED, CONF_ICON, CONF_NAME, DOMAIN
from .store import async_get_store


def _password_selector():
    return selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


class SpotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a SPOT feed."""

    VERSION = 1

    async def _async_validate(self, feed_id, password):
        """Make one test request; return (errors, description placeholders)."""
        try:
            await SpotAPI(self.hass, feed_id, password).page()
        except SpotFeedError as exc:
            if exc.code == FEED_NOT_FOUND:
                return {"feed_id": "feed_not_found"}, {}
            # Includes rejected passwords; SPOT's own explanation is the most useful detail.
            return {"base": "feed_rejected"}, {"spot_error": exc.text}
        except Exception:  # noqa: BLE001 - network and parse failures are presented as a flow error
            return {"base": "cannot_connect"}, {}
        return {}, {}

    async def async_step_user(self, user_input=None):
        errors, placeholders = {}, {}
        if user_input is not None:
            feed_id = user_input["feed_id"].strip()
            password = user_input.get("password", "")
            if not feed_id:
                errors["feed_id"] = "feed_not_found"
            else:
                await self.async_set_unique_id(feed_id)
                self._abort_if_unique_id_configured()
                errors, placeholders = await self._async_validate(feed_id, password)
            if not errors:
                return self.async_create_entry(
                    title="SPOT " + feed_id[-6:], data={"feed_id": feed_id, "password": password}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required("feed_id"): str,
                        vol.Optional("password", default=""): _password_selector(),
                    }
                ),
                {"feed_id": user_input["feed_id"]} if user_input else {},
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Change the feed password; the feed ID keys the archive and trackers, so it is fixed."""
        entry = self._get_reconfigure_entry()
        feed_id = entry.data["feed_id"]
        errors, placeholders = {}, {}
        if user_input is not None:
            password = user_input.get("password", "")
            errors, placeholders = await self._async_validate(feed_id, password)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates={"password": password})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Optional("password", default=""): _password_selector()}),
            errors=errors,
            description_placeholders={"feed_id": feed_id, **placeholders},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return SpotOptionsFlow()


class SpotOptionsFlow(config_entries.OptionsFlow):
    """Manage devices discovered in a SPOT feed."""

    def __init__(self) -> None:
        super().__init__()
        self._selected_device: str | None = None
        self._devices: list[dict[str, Any]] = []

    async def _async_load_devices(self) -> list[dict[str, Any]]:
        # Read the archive directly so devices remain manageable while the feed is unloaded.
        store = async_get_store(self.hass)
        feed = self.config_entry.data["feed_id"]
        devices = await self.hass.async_add_executor_job(store.list_devices, feed)
        latest = await self.hass.async_add_executor_job(store.latest, feed)
        return [{**device, "lat": latest.get(device["device"], {}).get("lat"),
                 "lon": latest.get(device["device"], {}).get("lon")} for device in devices]

    @staticmethod
    def _position_time(timestamp) -> str:
        """Display archived timestamps with an explicit timezone."""
        if timestamp is None:
            return "—"
        try:
            return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, OverflowError, OSError):
            return "—"

    def _device_settings(self) -> dict[str, dict[str, Any]]:
        return dict(self.config_entry.options.get(CONF_DEVICES, {}))

    async def async_step_init(self, user_input=None):
        """Show the device-management landing page."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["manage_devices"],
        )

    async def async_step_manage_devices(self, user_input=None):
        """Choose a discovered device to manage."""
        self._devices = await self._async_load_devices()
        if not self._devices:
            return self.async_abort(reason="no_devices")

        settings = self._device_settings()
        options = []
        for device in self._devices:
            device_id = device["device"]
            configured = settings.get(device_id, {})
            display_name = configured.get(CONF_NAME) or device.get("name") or device_id
            state = "enabled" if configured.get(CONF_ENABLED, True) else "disabled"
            options.append(
                selector.SelectOptionDict(
                    value=device_id,
                    label=f"{display_name} [{device_id}] ({state})",
                )
            )

        if user_input is not None:
            self._selected_device = user_input["device"]
            return await self.async_step_device()

        return self.async_show_form(
            step_id="manage_devices",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_device(self, user_input=None):
        """Edit settings for one SPOT device."""
        if self._selected_device is None:
            return await self.async_step_manage_devices()

        if not self._devices:
            self._devices = await self._async_load_devices()

        device = next(
            (item for item in self._devices if item["device"] == self._selected_device),
            None,
        )
        if device is None:
            return self.async_abort(reason="device_not_found")

        settings = self._device_settings()
        current = settings.get(self._selected_device, {})
        default_name = current.get(CONF_NAME) or device.get("name") or self._selected_device
        default_enabled = current.get(CONF_ENABLED, True)

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            settings[self._selected_device] = {
                **current,
                CONF_NAME: name,
                CONF_ENABLED: user_input[CONF_ENABLED],
            }
            if CONF_ICON in user_input:
                icon = user_input[CONF_ICON].strip()
                if icon:
                    settings[self._selected_device][CONF_ICON] = icon
                else:
                    settings[self._selected_device].pop(CONF_ICON, None)
            new_options = dict(self.config_entry.options)
            new_options[CONF_DEVICES] = settings
            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=default_name): str,
                    vol.Required(CONF_ENABLED, default=default_enabled): bool,
                    vol.Optional(CONF_ICON, default=current.get(CONF_ICON, '')): selector.IconSelector(),
                }
            ),
            description_placeholders={
                "feed_id": self.config_entry.data["feed_id"],
                "device_id": self._selected_device,
                "message_count": str(device.get("count", 0)),
                "first_position": self._position_time(device.get("first")),
                "latest_position": self._position_time(device.get("last")),
                "coordinates": (
                    f"{device['lat']:.6f}, {device['lon']:.6f}"
                    if device.get("lat") is not None and device.get("lon") is not None
                    else "—"
                ),
            },
        )
