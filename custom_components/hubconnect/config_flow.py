"""Config flow for HubConnect."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol

from homeassistant import config_entries

from .const import (
    CONF_HA_BASE_URL,
    CONF_HUBITAT_CONNECTION_KEY,
    CONF_HUBITAT_CONNECTION_TYPE,
    CONF_HUBITAT_TOKEN,
    CONF_HUBITAT_TYPE,
    CONF_HUBITAT_URI,
    CONF_REMOTE_NAME,
    CONF_TOKEN,
    DEFAULT_REMOTE_NAME,
    DOMAIN,
)
from .pairing import PairingError, async_pair_with_hubitat, decode_connection_key


class HubConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a HubConnect config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_REMOTE_NAME],
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_REMOTE_NAME,
                    default=DEFAULT_REMOTE_NAME,
                ): str,
                vol.Required(
                    CONF_TOKEN,
                    default=secrets.token_urlsafe(24),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors={},
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""

        return HubConnectOptionsFlow(config_entry)


class HubConnectOptionsFlow(config_entries.OptionsFlow):
    """Handle HubConnect options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""

        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle options."""

        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                hubitat_data = decode_connection_key(
                    user_input[CONF_HUBITAT_CONNECTION_KEY]
                )
                await async_pair_with_hubitat(
                    self.hass,
                    hubitat_data,
                    user_input[CONF_HA_BASE_URL],
                    self._config_entry.data[CONF_REMOTE_NAME],
                    self._config_entry.data[CONF_TOKEN],
                    self._config_entry.entry_id,
                )
            except PairingError as err:
                errors["base"] = str(err)
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_HA_BASE_URL: user_input[CONF_HA_BASE_URL],
                        CONF_HUBITAT_URI: hubitat_data["uri"],
                        CONF_HUBITAT_TOKEN: hubitat_data["token"],
                        CONF_HUBITAT_TYPE: hubitat_data.get("type"),
                        CONF_HUBITAT_CONNECTION_TYPE: hubitat_data.get(
                            "connectionType"
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HA_BASE_URL,
                    default=self._config_entry.options.get(
                        CONF_HA_BASE_URL,
                        "http://192.168.7.70:8123",
                    ),
                ): str,
                vol.Required(CONF_HUBITAT_CONNECTION_KEY): str,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
