"""HTTP views that mimic the first HubConnect remote endpoint calls."""

from __future__ import annotations

from asyncio import sleep

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.const import ATTR_FRIENDLY_NAME, ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_HUBITAT_CONNECTION_TYPE,
    CONF_HUBITAT_TOKEN,
    CONF_HUBITAT_TYPE,
    CONF_HUBITAT_URI,
    DOMAIN,
    HTTP_BASE,
)
from .pairing import PairingError, async_pair_with_hubitat, decode_connection_key
from .protocol import (
    async_execute_command,
    build_devices_payload,
    build_export_requirements,
    build_sync_payload,
    build_unsupported_exports,
)
from .shadow import (
    get_shadow_registry,
    async_save_shadow_registry,
    notify_shadow_devices_updated,
    notify_shadow_entity_updated,
)

APP_VERSION = {
    "platform": "Home Assistant",
    "major": 0,
    "minor": 0,
    "build": 1,
}


def async_register_http_views(hass: HomeAssistant) -> None:
    """Register HubConnect HTTP views once."""

    if hass.data.setdefault(DOMAIN, {}).get("_views_registered"):
        return

    hass.http.register_view(HubConnectPingView())
    hass.http.register_view(HubConnectVersionsView())
    hass.http.register_view(HubConnectModesView())
    hass.http.register_view(HubConnectDevicesView())
    hass.http.register_view(HubConnectDeviceSyncView())
    hass.http.register_view(HubConnectCommandView())
    hass.http.register_view(HubConnectSetConnectStringView())
    hass.http.register_view(HubConnectDriversSaveView())
    hass.http.register_view(HubConnectTroubleshootingReportView())
    hass.http.register_view(HubConnectDevicesSaveView())
    hass.http.register_view(HubConnectDeviceEventView())
    hass.http.register_view(HubConnectShadowDebugView())
    hass.data[DOMAIN]["_views_registered"] = True


class HubConnectView(HomeAssistantView):
    """Base view with HubConnect bearer-token authorization."""

    requires_auth = False

    def _authorized(self, request: web.Request) -> bool:
        """Return true if the request uses any configured HubConnect token."""

        return self._runtime_data(request) is not None

    def _runtime_data(self, request: web.Request):
        """Return runtime data for the bearer token, if any."""

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
        else:
            token = request.query.get("access_token", "")

        if not token:
            return None

        hass: HomeAssistant = request.app["hass"]

        for runtime_data in hass.data.get(DOMAIN, {}).values():
            if getattr(runtime_data, "token", None) == token:
                return runtime_data

        return None

    def _unauthorized(self) -> web.Response:
        """Return a HubConnect-shaped unauthorized response."""

        return self.json(
            {"status": "error", "message": "unauthorized"},
            status_code=401,
        )


class HubConnectPingView(HubConnectView):
    """Handle HubConnect health pings."""

    url = f"{HTTP_BASE}/ping"
    name = "api:hubconnect:ping"

    async def get(self, request: web.Request) -> web.Response:
        """Return a ping response."""

        if not self._authorized(request):
            get_shadow_registry(request.app["hass"]).log_request(
                "GET", request.path, "unauthorized", "device_event"
            )
            return self._unauthorized()

        return self.json({"status": "received"})


class HubConnectVersionsView(HubConnectView):
    """Return version data in the shape HubConnect expects."""

    url = f"{HTTP_BASE}/system/versions/get"
    name = "api:hubconnect:versions"

    async def get(self, request: web.Request) -> web.Response:
        """Return integration version data."""

        if not self._authorized(request):
            return self._unauthorized()

        return self.json(
            {
                "apps": [
                    {
                        "appName": "HubConnect for Home Assistant",
                        "appVersion": APP_VERSION,
                    }
                ],
                "drivers": {},
            }
        )


class HubConnectModesView(HubConnectView):
    """Return an empty mode list for the first test build."""

    url = f"{HTTP_BASE}/modes/get"
    name = "api:hubconnect:modes"

    async def get(self, request: web.Request) -> web.Response:
        """Return Home Assistant mode data."""

        if not self._authorized(request):
            return self._unauthorized()

        return self.json({"modes": [], "active": None})


class HubConnectDevicesView(HubConnectView):
    """Return the currently mappable Home Assistant entities."""

    url = f"{HTTP_BASE}/devices/get"
    name = "api:hubconnect:devices"

    async def get(self, request: web.Request) -> web.Response:
        """Return HubConnect device inventory data."""

        if not self._authorized(request):
            return self._unauthorized()

        hass: HomeAssistant = request.app["hass"]
        runtime_data = self._runtime_data(request)
        return self.json(
            build_devices_payload(
                hass,
                runtime_data.exported_entity_ids if runtime_data else [],
            )
        )


class HubConnectDeviceSyncView(HubConnectView):
    """Return current state for one mapped Home Assistant entity."""

    url = f"{HTTP_BASE}/device/{{device_id}}/sync/{{device_class}}"
    name = "api:hubconnect:device_sync"

    async def get(
        self,
        request: web.Request,
        device_id: str,
        device_class: str,
    ) -> web.Response:
        """Return a HubConnect sync payload for one HA entity."""

        if not self._authorized(request):
            return self._unauthorized()

        hass: HomeAssistant = request.app["hass"]
        runtime_data = self._runtime_data(request)
        return self.json(
            build_sync_payload(
                hass,
                device_id,
                device_class,
                runtime_data.exported_entity_ids if runtime_data else [],
            )
        )


class HubConnectCommandView(HubConnectView):
    """Execute a HubConnect command against an HA entity."""

    url = f"{HTTP_BASE}/event/{{device_id}}/{{device_command}}/{{command_params}}"
    name = "api:hubconnect:command"

    async def get(
        self,
        request: web.Request,
        device_id: str,
        device_command: str,
        command_params: str,
    ) -> web.Response:
        """Execute a HubConnect device command."""

        if not self._authorized(request):
            return self._unauthorized()

        hass: HomeAssistant = request.app["hass"]
        runtime_data = self._runtime_data(request)
        return self.json(
            await async_execute_command(
                hass,
                device_id,
                device_command,
                command_params,
                runtime_data.exported_entity_ids if runtime_data else [],
            )
        )


class HubConnectSetConnectStringView(HubConnectView):
    """Accept a Hubitat connection key over HTTP."""

    url = f"{HTTP_BASE}/system/setConnectString/{{connect_key}}"
    name = "api:hubconnect:set_connect_string"

    async def get(
        self,
        request: web.Request,
        connect_key: str,
    ) -> web.Response:
        """Pair this HA endpoint with a Hubitat HubConnect server instance."""

        runtime_data = self._runtime_data(request)
        if runtime_data is None:
            return self._unauthorized()

        hass: HomeAssistant = request.app["hass"]
        ha_base_url = f"{request.scheme}://{request.host}"

        try:
            hubitat_data = decode_connection_key(connect_key)
            await async_pair_with_hubitat(
                hass,
                hubitat_data,
                ha_base_url,
                runtime_data.remote_name,
                runtime_data.token,
                runtime_data.entry_id,
            )
        except PairingError as err:
            return self.json({"status": "error", "message": str(err)})

        runtime_data.hubitat_uri = hubitat_data["uri"]
        runtime_data.hubitat_token = hubitat_data["token"]
        runtime_data.hubitat_type = hubitat_data.get("type")
        runtime_data.hubitat_connection_type = hubitat_data.get("connectionType")
        if entry := hass.config_entries.async_get_entry(runtime_data.entry_id):
            hass.config_entries.async_update_entry(
                entry,
                options={
                    **entry.options,
                    CONF_HUBITAT_URI: hubitat_data["uri"],
                    CONF_HUBITAT_TOKEN: hubitat_data["token"],
                    CONF_HUBITAT_TYPE: hubitat_data.get("type"),
                    CONF_HUBITAT_CONNECTION_TYPE: hubitat_data.get("connectionType"),
                },
            )

        return self.json({"status": "success"})


class HubConnectDriversSaveView(HubConnectView):
    """Accept HubConnect custom driver metadata from Hubitat."""

    url = f"{HTTP_BASE}/system/drivers/save"
    name = "api:hubconnect:drivers_save"

    async def post(self, request: web.Request) -> web.Response:
        """Accept custom driver metadata.

        Home Assistant does not use Hubitat driver code, but Hubitat expects this
        endpoint during pairing when its custom driver database version changes.
        """

        if not self._authorized(request):
            return self._unauthorized()

        hass: HomeAssistant = request.app["hass"]
        get_shadow_registry(hass).log_request("POST", request.path, "success")
        return self.json({"status": "success"})


class HubConnectTroubleshootingReportView(HubConnectView):
    """Return the HubConnect troubleshooting report expected by Verify."""

    url = f"{HTTP_BASE}/system/tsreport/get"
    name = "api:hubconnect:tsreport"

    async def get(self, request: web.Request) -> web.Response:
        """Return a minimal HubConnect troubleshooting report."""

        runtime_data = self._runtime_data(request)
        if runtime_data is None:
            return self._unauthorized()

        hass: HomeAssistant = request.app["hass"]
        get_shadow_registry(hass).log_request("GET", request.path, "success")
        device_count = len(build_devices_payload(hass, runtime_data.exported_entity_ids))

        return self.json(
            {
                "app": {
                    "appId": runtime_data.entry_id,
                    "appVersion": APP_VERSION,
                    "installedVersion": APP_VERSION,
                },
                "prefs": {
                    "thisClientName": runtime_data.remote_name,
                    "pushModes": False,
                    "pushHSM": False,
                    "enableDebug": False,
                },
                "state": {
                    "clientURI": runtime_data.hubitat_uri,
                    "connectionType": runtime_data.hubitat_connection_type or "http",
                    "customDrivers": {},
                    "commDisabled": False,
                },
                "devices": {
                    "incomingDevices": 0,
                    "deviceIdList": [],
                    "availableDeviceClasses": device_count,
                },
                "hub": {
                    "deviceStatus": "Installed",
                    "connectionType": runtime_data.hubitat_connection_type or "http",
                    "eventSocketStatus": "none",
                    "presence": "present",
                    "switch": "on",
                    "version": "0.0.1",
                },
            }
        )


class HubConnectDevicesSaveView(HubConnectView):
    """Create or update HA shadow entities from Hubitat devices."""

    url = f"{HTTP_BASE}/devices/save"
    name = "api:hubconnect:devices_save"

    async def post(self, request: web.Request) -> web.Response:
        """Accept selected Hubitat devices."""

        if not self._authorized(request):
            return self._unauthorized()

        hass: HomeAssistant = request.app["hass"]
        data = await request.json()
        registry = get_shadow_registry(hass)
        removed_unique_ids: list[str] = []

        if "cleanupDevices" in data:
            cleanup_device_ids = data["cleanupDevices"]
            removed_unique_ids = registry.cleanup(cleanup_device_ids)
            removed_unique_ids.extend(
                _orphaned_unique_ids_for_cleanup(hass, cleanup_device_ids)
            )
            _async_remove_shadow_entities(hass, removed_unique_ids)
            removed_device_ids = _async_remove_orphan_shadow_devices(
                hass, cleanup_device_ids
            )
            detail = (
                f"cleanup:{len(cleanup_device_ids)} "
                f"removed:{len(set(removed_unique_ids))} "
                f"devices:{len(removed_device_ids)}"
            )
        elif data.get("deviceclass") and data.get("devices"):
            registry.upsert_devices(str(data["deviceclass"]), data["devices"])
            detail = f"{data['deviceclass']}:{len(data['devices'])}"
        else:
            registry.log_request("POST", request.path, "error", "invalid payload")
            return self.json({"status": "error", "message": "invalid payload"})

        registry.log_request("POST", request.path, "complete", detail)
        await async_save_shadow_registry(hass)
        notify_shadow_devices_updated(hass)
        for unique_id in registry.entities:
            notify_shadow_entity_updated(hass, unique_id)
        async_call_later(hass, 1, lambda _: notify_shadow_devices_updated(hass))
        runtime_data = self._runtime_data(request)
        if runtime_data is not None:
            async_call_later(
                hass,
                2,
                lambda _: hass.async_create_task(
                    hass.config_entries.async_reload(runtime_data.entry_id)
                ),
            )
        return self.json({"status": "complete"})


class HubConnectDeviceEventView(HubConnectView):
    """Update an HA shadow entity from a Hubitat device event."""

    url = f"{HTTP_BASE}/device/{{device_id}}/event/{{event:.+}}"
    name = "api:hubconnect:device_event"

    async def get(
        self,
        request: web.Request,
        device_id: str,
        event: str,
    ) -> web.Response:
        """Accept one Hubitat event."""

        if not self._authorized(request):
            return self._unauthorized()

        hass: HomeAssistant = request.app["hass"]
        data = await _decode_event(event)
        registry = get_shadow_registry(hass)
        if not registry.update_event(device_id, data):
            registry.log_request("GET", request.path, "error", "device not found")
            return self.json({"status": "error", "message": "device not found"})

        unique_id = f"{device_id}_{data.get('name')}"
        live_entity = hass.data.get(DOMAIN, {}).get("_shadow_entities", {}).get(
            unique_id
        )
        if live_entity is not None:
            live_entity.async_refresh_from_shadow()
        else:
            notify_shadow_devices_updated(hass)
            async_call_later(
                hass,
                1,
                lambda _: (
                    _async_write_shadow_state(hass, unique_id),
                    notify_shadow_entity_updated(hass, unique_id),
                ),
            )
        _async_write_shadow_state(hass, unique_id)
        notify_shadow_entity_updated(hass, unique_id)
        await sleep(0)
        registry.log_request(
            "GET",
            request.path,
            "complete",
            f"{data.get('name')}={data.get('value')} live={_live_state_for_unique_id(hass, unique_id)}",
        )
        return self.json({"status": "complete"})


async def _decode_event(event: str) -> dict:
    """Decode a URL-encoded HubConnect event payload."""

    from json import loads
    from urllib.parse import unquote

    return loads(unquote(event))


def _entity_id_for_unique_id(hass: HomeAssistant, unique_id: str) -> str | None:
    """Return the registered HA entity id for a HubConnect shadow unique id."""

    entity_registry = er.async_get(hass)
    entry = next(
        (
            entry
            for entry in entity_registry.entities.values()
            if entry.platform == DOMAIN and entry.unique_id == unique_id
        ),
        None,
    )
    return entry.entity_id if entry else None


def _owning_entity_id_for_unique_id(hass: HomeAssistant, unique_id: str) -> str | None:
    """Return the HA entity id that represents a shadow unique id."""

    entity_id = _entity_id_for_unique_id(hass, unique_id)
    if entity_id is not None:
        return entity_id

    registry = get_shadow_registry(hass)
    description = registry.entities.get(unique_id)
    if description is None or description.platform.value != "climate":
        return None

    return _entity_id_for_unique_id(hass, description.device_id)


def _live_state_for_unique_id(hass: HomeAssistant, unique_id: str) -> str:
    """Return the live HA state for an exact or owning shadow entity."""

    entity_id = _owning_entity_id_for_unique_id(hass, unique_id)
    state = hass.states.get(entity_id) if entity_id else None
    return state.state if state else "missing"


def _orphaned_unique_ids_for_cleanup(
    hass: HomeAssistant,
    device_ids: list[object],
) -> list[str]:
    """Return HubConnect registry unique ids excluded by a cleanup payload."""

    keep_ids = {str(device_id) for device_id in device_ids}
    entity_registry = er.async_get(hass)
    return [
        str(entry.unique_id)
        for entry in entity_registry.entities.values()
        if entry.platform == DOMAIN
        and str(entry.unique_id).split("_", 1)[0] not in keep_ids
    ]


def _async_remove_shadow_entities(
    hass: HomeAssistant,
    removed_unique_ids: list[str],
) -> None:
    """Remove HA state and registry entries for discarded shadow entities."""

    removed_unique_ids = sorted(set(removed_unique_ids))
    if not removed_unique_ids:
        return

    entity_registry = er.async_get(hass)
    live_entities = hass.data.get(DOMAIN, {}).get("_shadow_entities", {})

    for unique_id in removed_unique_ids:
        entity_id = _entity_id_for_unique_id(hass, unique_id)
        live_entities.pop(unique_id, None)
        if entity_id is not None:
            hass.states.async_remove(entity_id)
            entity_registry.async_remove(entity_id)


def _async_remove_orphan_shadow_devices(
    hass: HomeAssistant,
    keep_device_ids: list[object],
) -> list[str]:
    """Remove HA device-registry entries for discarded shadow devices."""

    keep_ids = {str(device_id) for device_id in keep_device_ids}
    device_registry = dr.async_get(hass)
    removed_device_ids: list[str] = []

    for device_entry in list(device_registry.devices.values()):
        shadow_device_ids = {
            str(identifier[1])
            for identifier in device_entry.identifiers
            if len(identifier) == 2 and identifier[0] == DOMAIN
        }
        if not shadow_device_ids or shadow_device_ids & keep_ids:
            continue

        device_registry.async_remove_device(device_entry.id)
        removed_device_ids.extend(sorted(shadow_device_ids))

    return removed_device_ids


def _async_write_shadow_state(hass: HomeAssistant, unique_id: str) -> None:
    """Write a shadow entity directly into Home Assistant's state machine."""

    registry = get_shadow_registry(hass)
    description = registry.entities.get(unique_id)
    entity_id = _entity_id_for_unique_id(hass, unique_id)
    if description is None or entity_id is None:
        return

    if description.value is None:
        state = "unknown"
    elif description.platform.value == "binary_sensor":
        state = "on" if str(description.value) in description.on_values else "off"
    else:
        state = str(description.value)

    current = hass.states.get(entity_id)
    attributes = dict(current.attributes) if current else {}
    attributes.update(
        {
            ATTR_FRIENDLY_NAME: f"{description.label} {description.attribute}",
            "hubconnect_device_id": description.device_id,
            "hubconnect_device_class": description.device_class,
            "hubconnect_attribute": description.attribute,
        }
    )
    if description.unit:
        attributes[ATTR_UNIT_OF_MEASUREMENT] = description.unit
    elif ATTR_UNIT_OF_MEASUREMENT in attributes:
        del attributes[ATTR_UNIT_OF_MEASUREMENT]
    if description.ha_device_class is not None:
        attributes["device_class"] = description.ha_device_class

    hass.states.async_set(entity_id, state, attributes)


class HubConnectShadowDebugView(HubConnectView):
    """Return current Hubitat shadow entities for debugging."""

    url = f"{HTTP_BASE}/system/shadows/get"
    name = "api:hubconnect:shadows"

    async def get(self, request: web.Request) -> web.Response:
        """Return the shadow registry."""

        if not self._authorized(request):
            return self._unauthorized()

        hass: HomeAssistant = request.app["hass"]
        runtime_data = self._runtime_data(request)
        registry = get_shadow_registry(hass)
        entity_registry = er.async_get(hass)
        device_registry = dr.async_get(hass)
        hubconnect_entries = {
            entry.unique_id: entry
            for entry in entity_registry.entities.values()
            if entry.platform == DOMAIN
        }
        hubconnect_entity_ids = {
            entry.entity_id for entry in hubconnect_entries.values()
        }
        shadow_unique_ids = set(registry.entities)
        shadow_device_ids = {
            entity.device_id for entity in registry.entities.values()
        }
        orphaned_entries = {
            unique_id: entry
            for unique_id, entry in hubconnect_entries.items()
            if unique_id not in shadow_unique_ids and unique_id not in shadow_device_ids
        }
        live_entities = hass.data.get(DOMAIN, {}).get("_shadow_entities", {})
        orphaned_live_entities = sorted(
            unique_id
            for unique_id in live_entities
            if unique_id not in shadow_unique_ids and unique_id not in shadow_device_ids
        )
        hubconnect_devices = []
        orphaned_devices = []
        for device_entry in device_registry.devices.values():
            device_shadow_ids = sorted(
                str(identifier[1])
                for identifier in device_entry.identifiers
                if len(identifier) == 2 and identifier[0] == DOMAIN
            )
            if not device_shadow_ids:
                continue

            device_data = {
                "id": device_entry.id,
                "name": getattr(device_entry, "name_by_user", None)
                or getattr(device_entry, "name", None),
                "identifiers": device_shadow_ids,
            }
            hubconnect_devices.append(device_data)
            if not set(device_shadow_ids) & shadow_device_ids:
                orphaned_devices.append(device_data)

        return self.json(
            {
                "status": "success",
                "count": len(registry.entities),
                "entities": registry.as_dict(),
                "requests": registry.requests,
                "platform_events": registry.platform_events,
                "ha_export": {
                    "selected_entity_ids": list(runtime_data.exported_entity_ids)
                    if runtime_data
                    else [],
                    "current_payload": build_devices_payload(
                        hass,
                        runtime_data.exported_entity_ids if runtime_data else [],
                    ),
                    "required_drivers": build_export_requirements(
                        hass,
                        runtime_data.exported_entity_ids if runtime_data else [],
                    ),
                    "unsupported_entities": build_unsupported_exports(
                        hass,
                        runtime_data.exported_entity_ids if runtime_data else [],
                    ),
                    "pushes": registry.export_pushes,
                },
                "entity_registry": [
                    {
                        "entity_id": entry.entity_id,
                        "unique_id": entry.unique_id,
                        "platform": entry.platform,
                        "disabled_by": entry.disabled_by,
                    }
                    for entry in entity_registry.entities.values()
                    if entry.platform == DOMAIN
                ],
                "orphaned_entity_registry": [
                    {
                        "entity_id": entry.entity_id,
                        "unique_id": entry.unique_id,
                        "disabled_by": entry.disabled_by,
                        "state": hass.states.get(entry.entity_id).state
                        if hass.states.get(entry.entity_id)
                        else "missing",
                    }
                    for entry in orphaned_entries.values()
                ],
                "live_entities": sorted(live_entities),
                "orphaned_live_entities": orphaned_live_entities,
                "device_registry": hubconnect_devices,
                "orphaned_device_registry": orphaned_devices,
                "shadow_states": [
                    {
                        "unique_id": unique_id,
                        "entity_id": entry.entity_id if entry else None,
                        "state": state.state if state else "missing",
                        "friendly_name": state.attributes.get("friendly_name")
                        if state
                        else None,
                    }
                    for unique_id in sorted(registry.entities)
                    for entry in [hubconnect_entries.get(unique_id)]
                    for state in [
                        hass.states.get(entry.entity_id) if entry else None
                    ]
                ],
                "ha_states": [
                    {
                        "entity_id": state.entity_id,
                        "state": state.state,
                        "friendly_name": state.attributes.get("friendly_name"),
                    }
                    for state in hass.states.async_all()
                    if "multisensor" in state.entity_id.lower()
                    or "office" in state.entity_id.lower()
                    or "hubconnect" in state.entity_id.lower()
                    or "hubitat" in state.entity_id.lower()
                    or "pseudo" in state.entity_id.lower()
                    or "2834" in state.entity_id
                    or state.entity_id in hubconnect_entity_ids
                    or "multisensor" in str(state.attributes.get("friendly_name", "")).lower()
                    or "office" in str(state.attributes.get("friendly_name", "")).lower()
                    or "pseudo" in str(state.attributes.get("friendly_name", "")).lower()
                ],
            }
        )
