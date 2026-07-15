"""HubConnect endpoint integration for Home Assistant.

HubConnect for Hubitat was created by Steve White / Retail Media Concepts LLC.
This integration is an independent Python implementation of a compatible Home
Assistant remote endpoint.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
import json
from urllib.parse import quote, urlencode

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_EXPORTED_ENTITY_IDS,
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
from .protocol import (
    build_attribute_payload,
    export_device_id_for_state,
    friendly_name,
    get_entity_mapping,
)
from .shadow import async_load_shadow_registry, get_shadow_registry

EXPORT_LISTENER_MARKER = "state-helper-v1"
EXPORT_POLL_INTERVAL = 5
ExportAttributeSignature = tuple[str, str, object, str]


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
    exported_entity_ids: tuple[str, ...]
    ping_task: asyncio.Task[None] | None = None
    export_poll_task: asyncio.Task[None] | None = None
    export_state_unsub: Callable[[], None] | None = None
    export_last_attributes: dict[str, ExportAttributeSignature] = field(
        default_factory=dict
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HubConnect from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    runtime_data = HubConnectRuntimeData(
        entry_id=entry.entry_id,
        remote_name=entry.data[CONF_REMOTE_NAME],
        token=entry.data[CONF_TOKEN],
        hubitat_uri=entry.options.get(CONF_HUBITAT_URI),
        hubitat_token=entry.options.get(CONF_HUBITAT_TOKEN),
        hubitat_type=entry.options.get(CONF_HUBITAT_TYPE),
        hubitat_connection_type=entry.options.get(CONF_HUBITAT_CONNECTION_TYPE),
        exported_entity_ids=tuple(entry.options.get(CONF_EXPORTED_ENTITY_IDS, [])),
    )
    hass.data[DOMAIN][entry.entry_id] = runtime_data

    await async_load_shadow_registry(hass)
    async_register_http_views(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    runtime_data.ping_task = hass.async_create_task(
        _async_ping_hubitat_forever(hass, entry)
    )
    if runtime_data.exported_entity_ids:
        runtime_data.export_state_unsub = async_track_state_change_event(
            hass,
            runtime_data.exported_entity_ids,
            lambda event: hass.async_create_task(
                _async_send_hubitat_state_event(hass, entry, event)
            ),
        )
        get_shadow_registry(hass).log_platform_event(
            "ha_export",
            "listen",
            len(runtime_data.exported_entity_ids),
            f"{EXPORT_LISTENER_MARKER}:"
            + ",".join(runtime_data.exported_entity_ids),
        )
        runtime_data.export_poll_task = hass.async_create_task(
            _async_poll_hubitat_export_states_forever(hass, entry)
        )
        get_shadow_registry(hass).log_platform_event(
            "ha_export",
            "poll",
            len(runtime_data.exported_entity_ids),
            f"interval={EXPORT_POLL_INTERVAL}s",
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a HubConnect config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    runtime_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime_data and runtime_data.ping_task:
        runtime_data.ping_task.cancel()
        with suppress(asyncio.CancelledError):
            await runtime_data.ping_task

    if runtime_data and runtime_data.export_poll_task:
        runtime_data.export_poll_task.cancel()
        with suppress(asyncio.CancelledError):
            await runtime_data.export_poll_task

    if runtime_data and runtime_data.export_state_unsub:
        runtime_data.export_state_unsub()

    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload HubConnect when options change."""

    await hass.config_entries.async_reload(entry.entry_id)


async def _async_ping_hubitat_forever(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Keep Hubitat's remote-client health check alive."""

    while True:
        await _async_ping_hubitat(hass, entry)
        await asyncio.sleep(60)


async def _async_ping_hubitat(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Send the HubConnect health ping to Hubitat."""

    runtime_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    hubitat_uri = (
        getattr(runtime_data, "hubitat_uri", None)
        or entry.options.get(CONF_HUBITAT_URI)
    )
    hubitat_token = (
        getattr(runtime_data, "hubitat_token", None)
        or entry.options.get(CONF_HUBITAT_TOKEN)
    )
    if not hubitat_uri or not hubitat_token:
        get_shadow_registry(hass).log_request(
            "GET",
            "/hubitat/ping",
            "skipped",
            "missing hubitat uri/token",
        )
        return

    url = f"{hubitat_uri.rstrip('/')}/ping?access_token={hubitat_token}"
    session = async_get_clientsession(hass)
    try:
        response = await session.get(
            url,
            headers={"Authorization": f"Bearer {hubitat_token}"},
            timeout=10,
        )
    except (ClientError, TimeoutError):
        get_shadow_registry(hass).log_request(
            "GET",
            "/hubitat/ping",
            "error",
            hubitat_uri,
        )
        return
    get_shadow_registry(hass).log_request(
        "GET",
        "/hubitat/ping",
        "complete" if response.status == 200 else "error",
        f"{hubitat_uri} status={response.status}",
    )


async def _async_poll_hubitat_export_states_forever(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Poll selected HA exports as a fallback for state-change callbacks."""

    while True:
        await _async_poll_hubitat_export_states(hass, entry)
        await asyncio.sleep(EXPORT_POLL_INTERVAL)


async def _async_poll_hubitat_export_states(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Push changed selected HA states to Hubitat from the state machine."""

    runtime_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime_data is None:
        return
    selected_entity_ids = (
        getattr(runtime_data, "exported_entity_ids", None)
        or tuple(entry.options.get(CONF_EXPORTED_ENTITY_IDS, []))
    )
    for entity_id in selected_entity_ids:
        state = hass.states.get(entity_id)
        if not isinstance(state, State):
            continue

        signature = _export_attribute_signature(state)
        if signature is None:
            continue

        old_signature = runtime_data.export_last_attributes.get(entity_id)
        if old_signature is None:
            runtime_data.export_last_attributes[entity_id] = signature
            continue
        if old_signature == signature:
            continue

        await _async_send_hubitat_state_change(
            hass,
            entry,
            state,
            None,
            source="poll",
        )


async def _async_send_hubitat_state_event(
    hass: HomeAssistant,
    entry: ConfigEntry,
    event: Event,
) -> None:
    """Push a selected Home Assistant state change to Hubitat."""

    new_state = event.data.get("new_state")
    old_state = event.data.get("old_state")
    await _async_send_hubitat_state_change(
        hass,
        entry,
        new_state,
        old_state,
        source="event",
    )


async def _async_send_hubitat_state_change(
    hass: HomeAssistant,
    entry: ConfigEntry,
    new_state: object,
    old_state: object,
    *,
    source: str,
) -> None:
    """Push a selected Home Assistant state change to Hubitat."""

    if not isinstance(new_state, State):
        return

    runtime_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime_data is None:
        return
    selected_entity_ids = (
        getattr(runtime_data, "exported_entity_ids", None)
        or tuple(entry.options.get(CONF_EXPORTED_ENTITY_IDS, []))
    )
    if new_state.entity_id not in selected_entity_ids:
        return

    get_shadow_registry(hass).log_request(
        "GET",
        "/hubitat/event",
        "seen",
        (
            f"{source} {new_state.entity_id} "
            f"{old_state.state if isinstance(old_state, State) else None}"
            f"->{new_state.state}"
        ),
    )

    mapping = get_entity_mapping(new_state)
    if mapping is None:
        get_shadow_registry(hass).log_request(
            "GET",
            "/hubitat/event",
            "skipped",
            f"{new_state.entity_id} unsupported",
        )
        return

    new_attribute = build_attribute_payload(new_state, mapping)
    runtime_data.export_last_attributes[new_state.entity_id] = (
        mapping.device_class,
        new_attribute["name"],
        new_attribute["value"],
        new_attribute["unit"],
    )
    if isinstance(old_state, State):
        old_mapping = get_entity_mapping(old_state)
        if (
            old_mapping == mapping
            and build_attribute_payload(old_state, mapping) == new_attribute
        ):
            get_shadow_registry(hass).log_request(
                "GET",
                "/hubitat/event",
                "skipped",
                f"{new_state.entity_id} unchanged {new_attribute['name']}",
            )
            return

    hubitat_uri = (
        getattr(runtime_data, "hubitat_uri", None)
        or entry.options.get(CONF_HUBITAT_URI)
    )
    hubitat_token = (
        getattr(runtime_data, "hubitat_token", None)
        or entry.options.get(CONF_HUBITAT_TOKEN)
    )
    if not hubitat_uri or not hubitat_token:
        get_shadow_registry(hass).log_request(
            "GET",
            "/hubitat/event",
            "skipped",
            "missing hubitat uri/token",
        )
        return

    payload = {
        "name": new_attribute["name"],
        "value": new_attribute["value"],
        "unit": new_attribute["unit"] or None,
        "displayName": friendly_name(new_state),
        "data": None,
    }
    encoded_event = quote(json.dumps(payload, separators=(",", ":")), safe="")
    export_device_id = export_device_id_for_state(
        hass,
        new_state,
        selected_entity_ids,
    )
    encoded_device_id = quote(export_device_id, safe="")
    url = (
        f"{hubitat_uri.rstrip('/')}/device/{encoded_device_id}/event/{encoded_event}"
        f"?{urlencode({'access_token': hubitat_token})}"
    )
    session = async_get_clientsession(hass)
    try:
        response = await session.get(
            url,
            headers={"Authorization": f"Bearer {hubitat_token}"},
            timeout=10,
        )
    except (ClientError, TimeoutError):
        get_shadow_registry(hass).log_request(
            "GET",
            "/hubitat/event",
            "error",
            new_state.entity_id,
        )
        return

    get_shadow_registry(hass).log_request(
        "GET",
        "/hubitat/event",
        "complete" if response.status == 200 else "error",
        (
            f"{export_device_id} {new_attribute['name']}="
            f"{new_attribute['value']} status={response.status}"
        ),
    )


def _export_attribute_signature(state: State) -> ExportAttributeSignature | None:
    """Return the HubConnect attribute signature for a HA export state."""

    mapping = get_entity_mapping(state)
    if mapping is None:
        return None
    attribute = build_attribute_payload(state, mapping)
    return (
        mapping.device_class,
        attribute["name"],
        attribute["value"],
        attribute["unit"],
    )
