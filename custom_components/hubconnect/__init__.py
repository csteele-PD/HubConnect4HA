"""HubConnect endpoint integration for Home Assistant.

HubConnect for Hubitat was created by Steve White / Retail Media Concepts LLC.
This integration is an independent Python implementation of a compatible Home
Assistant remote endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_HUBITAT_CONNECTION_TYPE,
    CONF_HUBITAT_TOKEN,
    CONF_HUBITAT_TYPE,
    CONF_HUBITAT_URI,
    CONF_REMOTE_NAME,
    CONF_TOKEN,
    DOMAIN,
    PLATFORMS,
)
from .http import async_register_http_views
from .shadow import async_load_shadow_registry


@dataclass(slots=True)
class HubConnectRuntimeData:
    """Runtime data for one HubConnect endpoint."""

    entry_id: str
    remote_name: str
    token: str
    hubitat_uri: str | None
    hubitat_token: str | None
    hubitat_type: str | None
    hubitat_connection_type: str | None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HubConnect from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = HubConnectRuntimeData(
        entry_id=entry.entry_id,
        remote_name=entry.data[CONF_REMOTE_NAME],
        token=entry.data[CONF_TOKEN],
        hubitat_uri=entry.options.get(CONF_HUBITAT_URI),
        hubitat_token=entry.options.get(CONF_HUBITAT_TOKEN),
        hubitat_type=entry.options.get(CONF_HUBITAT_TYPE),
        hubitat_connection_type=entry.options.get(CONF_HUBITAT_CONNECTION_TYPE),
    )

    await async_load_shadow_registry(hass)
    async_register_http_views(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    if entry.options.get(CONF_HUBITAT_URI) and entry.options.get(CONF_HUBITAT_TOKEN):
        entry.async_on_unload(
            async_track_time_interval(
                hass,
                lambda _: hass.async_create_task(_async_ping_hubitat(hass, entry)),
                timedelta(minutes=1),
            )
        )
        hass.async_create_task(_async_ping_hubitat(hass, entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a HubConnect config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload HubConnect when options change."""

    await hass.config_entries.async_reload(entry.entry_id)


async def _async_ping_hubitat(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Send the HubConnect health ping to Hubitat."""

    hubitat_uri = entry.options.get(CONF_HUBITAT_URI)
    hubitat_token = entry.options.get(CONF_HUBITAT_TOKEN)
    if not hubitat_uri or not hubitat_token:
        return

    url = f"{hubitat_uri.rstrip('/')}/ping?access_token={hubitat_token}"
    session = async_get_clientsession(hass)
    try:
        await session.get(
            url,
            headers={"Authorization": f"Bearer {hubitat_token}"},
            timeout=10,
        )
    except (ClientError, TimeoutError):
        return
