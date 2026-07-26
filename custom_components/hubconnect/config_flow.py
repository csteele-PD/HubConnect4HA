"""Config flow for HubConnect."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_EXPORTED_ENTITY_IDS,
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
from .pairing import (
    PairingError,
    async_pair_with_hubitat,
    async_post_to_hubitat,
    decode_connection_key,
)
from .protocol import (
    build_cleanup_device_ids,
    build_devices_payload,
    build_export_requirements,
    build_unsupported_exports,
)
from .shadow import get_shadow_registry


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
        self._pending_options: dict[str, Any] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle options."""

        errors: dict[str, str] = {}

        if user_input is not None:
            options = {
                **self._config_entry.options,
                CONF_HA_BASE_URL: user_input[CONF_HA_BASE_URL],
                CONF_EXPORTED_ENTITY_IDS: user_input.get(
                    CONF_EXPORTED_ENTITY_IDS,
                    [],
                ),
            }
            if user_input.get(CONF_HUBITAT_CONNECTION_KEY):
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
                    options.update(
                        {
                            CONF_HUBITAT_URI: hubitat_data["uri"],
                            CONF_HUBITAT_TOKEN: hubitat_data["token"],
                            CONF_HUBITAT_TYPE: hubitat_data.get("type"),
                            CONF_HUBITAT_CONNECTION_TYPE: hubitat_data.get(
                                "connectionType"
                            ),
                        }
                    )

            if not errors:
                selected_entity_ids = options.get(CONF_EXPORTED_ENTITY_IDS, [])
                if selected_entity_ids and (
                    not options.get(CONF_HUBITAT_URI)
                    or not options.get(CONF_HUBITAT_TOKEN)
                ):
                    errors["base"] = "missing_hubitat_connection"
                else:
                    self._pending_options = options
                    return self.async_show_form(
                        step_id="confirm",
                        data_schema=vol.Schema({}),
                        description_placeholders=self._diagnostic_placeholders(
                            options
                        ),
                    )

            if not errors:
                return self.async_create_entry(title="", data=options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HA_BASE_URL,
                    default=self._config_entry.options.get(
                        CONF_HA_BASE_URL,
                        "http://homeassistant.local:8123",
                    ),
                ): str,
                vol.Optional(CONF_HUBITAT_CONNECTION_KEY, default=""): str,
                vol.Optional(
                    CONF_EXPORTED_ENTITY_IDS,
                    default=self._config_entry.options.get(
                        CONF_EXPORTED_ENTITY_IDS,
                        [],
                    ),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm export diagnostics and save options."""

        if user_input is not None and self._pending_options is not None:
            try:
                await self._async_push_selected_entities_to_hubitat(
                    self._pending_options
                )
            except PairingError as err:
                return self.async_show_form(
                    step_id="confirm",
                    data_schema=vol.Schema({}),
                    errors={"base": str(err)},
                    description_placeholders=self._diagnostic_placeholders(
                        self._pending_options
                    ),
                )

            return self.async_create_entry(title="", data=self._pending_options)

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders=self._diagnostic_placeholders(
                self._pending_options or self._config_entry.options
            ),
        )

    def _diagnostic_placeholders(self, options: dict[str, Any]) -> dict[str, str]:
        """Return export diagnostic text for the confirmation page."""

        selected_entity_ids = options.get(CONF_EXPORTED_ENTITY_IDS, [])
        requirements = build_export_requirements(self.hass, selected_entity_ids)
        unsupported = build_unsupported_exports(self.hass, selected_entity_ids)
        payloads = build_devices_payload(self.hass, selected_entity_ids)

        drivers = sorted({requirement["driver"] for requirement in requirements})
        exported_count = sum(len(payload["devices"]) for payload in payloads)

        return {
            "exported_count": str(exported_count),
            "required_drivers": "\n".join(f"- {driver}" for driver in drivers)
            or "- None",
            "unsupported_entities": "\n".join(
                f"- {entity['entity_id']}: {entity['reason']}"
                for entity in unsupported
            )
            or "- None",
        }

    async def _async_push_selected_entities_to_hubitat(
        self,
        options: dict[str, Any],
    ) -> None:
        """Push selected Home Assistant entities to Hubitat."""

        hubitat_uri = options.get(CONF_HUBITAT_URI)
        hubitat_token = options.get(CONF_HUBITAT_TOKEN)
        if not hubitat_uri or not hubitat_token:
            return

        selected_entity_ids = options.get(CONF_EXPORTED_ENTITY_IDS, [])
        payloads = build_devices_payload(self.hass, selected_entity_ids)
        cleanup_ids = build_cleanup_device_ids(self.hass, selected_entity_ids)
        registry = get_shadow_registry(self.hass)

        for payload in payloads:
            try:
                response = await async_post_to_hubitat(
                    self.hass,
                    hubitat_uri,
                    hubitat_token,
                    "/devices/save",
                    payload,
                )
            except PairingError as err:
                registry.log_export_push(
                    f"{hubitat_uri.rstrip('/')}/devices/save",
                    "error",
                    str(err),
                    payload,
                    err.response,
                )
                raise

            registry.log_export_push(
                f"{hubitat_uri.rstrip('/')}/devices/save",
                "complete",
                f"{payload['deviceclass']}:{len(payload['devices'])}",
                payload,
                response,
            )

        cleanup_payload = {"cleanupDevices": cleanup_ids}
        try:
            response = await async_post_to_hubitat(
                self.hass,
                hubitat_uri,
                hubitat_token,
                "/devices/save",
                cleanup_payload,
            )
        except PairingError as err:
            registry.log_export_push(
                f"{hubitat_uri.rstrip('/')}/devices/save",
                "error",
                str(err),
                cleanup_payload,
                err.response,
            )
            raise

        registry.log_export_push(
            f"{hubitat_uri.rstrip('/')}/devices/save",
            "complete",
            f"cleanup:{len(cleanup_ids)}",
            cleanup_payload,
            response,
        )
