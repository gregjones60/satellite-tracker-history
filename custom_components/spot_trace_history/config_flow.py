"""Config and options flows for SPOT Trace History."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import SpotAPI
from .const import CONF_DEVICES, CONF_ENABLED, CONF_NAME, DOMAIN


class SpotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a SPOT feed."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await SpotAPI(
                    self.hass,
                    user_input["feed_id"],
                    user_input.get("password", ""),
                ).page()
            except Exception:  # noqa: BLE001 - API failures are presented as a flow error
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input["feed_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="SPOT " + user_input["feed_id"][-6:], data=user_input
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("feed_id"): str,
                    vol.Optional("password", default=""): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return SpotOptionsFlow(config_entry)


class SpotOptionsFlow(config_entries.OptionsFlow):
    """Manage devices discovered in a SPOT feed."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._selected_device: str | None = None
        self._devices: list[dict[str, Any]] = []

    async def _async_load_devices(self) -> list[dict[str, Any]]:
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if coordinator is None:
            return []
        return await self.hass.async_add_executor_job(
            coordinator.store.list_devices, coordinator.feed
        )

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
                    label=f"{display_name} ({state})",
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
                CONF_NAME: name,
                CONF_ENABLED: user_input[CONF_ENABLED],
            }
            new_options = dict(self.config_entry.options)
            new_options[CONF_DEVICES] = settings
            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=default_name): str,
                    vol.Required(CONF_ENABLED, default=default_enabled): bool,
                }
            ),
            description_placeholders={
                "device_id": self._selected_device,
                "message_count": str(device.get("count", 0)),
            },
        )
