"""Helpers for translating Home Assistant state into HubConnect payloads."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import unquote

from homeassistant.core import HomeAssistant, State


UNKNOWN_STATES = {"unknown", "unavailable"}


@dataclass(frozen=True, slots=True)
class EntityMapping:
    """HubConnect mapping for a Home Assistant entity."""

    device_class: str
    attribute: str
    unit: str = ""


# HubConnect deviceclass keys must match the Groovy NATIVE_DEVICES table. Prefer
# standard mirror drivers when they exist; use v_* only for standalone synthetic
# measurements where HubConnect has no plain native class.
HUBCONNECT_EXPORT_ATTRIBUTES: dict[str, set[str]] = {
    "contact": {"contact", "temperature", "battery"},
    "dimmer": {"switch", "level"},
    "energy": {"energy"},
    "moisture": {"water", "temperature", "battery"},
    "motion": {"motion", "temperature", "battery"},
    "power": {"power"},
    "presence": {"presence", "battery"},
    "smoke": {"smoke", "carbonMonoxide", "battery"},
    "switch": {"switch"},
    "v_humidity": {"humidity"},
    "v_illuminance": {"illuminance"},
    "v_temperature": {"temperature"},
}

HUBCONNECT_EXPORT_DRIVERS: dict[str, str] = {
    "contact": "HubConnect Contact Sensor",
    "dimmer": "HubConnect Dimmer",
    "energy": "HubConnect Energy Meter",
    "moisture": "HubConnect Moisture Sensor",
    "motion": "HubConnect Motion Sensor",
    "power": "HubConnect Power Meter",
    "presence": "HubConnect Presence Sensor",
    "smoke": "HubConnect SmokeCO",
    "switch": "HubConnect Switch",
    "v_humidity": "HubConnect Virtual Virtual Humidity Sensor",
    "v_illuminance": "HubConnect Virtual Illuminance Sensor",
    "v_temperature": "HubConnect Virtual Temperature Sensor",
}

SENSOR_DEVICE_CLASS_MAP: dict[str, EntityMapping] = {
    "energy": EntityMapping("energy", "energy"),
    "humidity": EntityMapping("v_humidity", "humidity", "%"),
    "illuminance": EntityMapping("v_illuminance", "illuminance"),
    "power": EntityMapping("power", "power", "W"),
    "temperature": EntityMapping("v_temperature", "temperature"),
}

BINARY_SENSOR_DEVICE_CLASS_MAP: dict[str, EntityMapping] = {
    "door": EntityMapping("contact", "contact"),
    "garage_door": EntityMapping("contact", "contact"),
    "gas": EntityMapping("smoke", "carbonMonoxide"),
    "moisture": EntityMapping("moisture", "water"),
    "motion": EntityMapping("motion", "motion"),
    "occupancy": EntityMapping("motion", "motion"),
    "opening": EntityMapping("contact", "contact"),
    "presence": EntityMapping("presence", "presence"),
    "smoke": EntityMapping("smoke", "smoke"),
    "window": EntityMapping("contact", "contact"),
}


def get_entity_mapping(state: State) -> EntityMapping | None:
    """Return the HubConnect mapping for a Home Assistant state."""

    domain = state.entity_id.split(".", 1)[0]
    device_class = state.attributes.get("device_class")

    if domain == "switch":
        return _validated_mapping(EntityMapping("switch", "switch"))

    if domain == "light":
        supported_color_modes = state.attributes.get("supported_color_modes") or set()
        if "brightness" in supported_color_modes:
            return _validated_mapping(EntityMapping("dimmer", "switch"))
        return _validated_mapping(EntityMapping("switch", "switch"))

    if domain == "sensor" and isinstance(device_class, str):
        return _validated_mapping(SENSOR_DEVICE_CLASS_MAP.get(device_class))

    if domain == "binary_sensor" and isinstance(device_class, str):
        return _validated_mapping(BINARY_SENSOR_DEVICE_CLASS_MAP.get(device_class))

    return None


def _validated_mapping(mapping: EntityMapping | None) -> EntityMapping | None:
    """Return a mapping only when HubConnect can resolve its class/attribute."""

    if mapping is None:
        return None

    allowed_attributes = HUBCONNECT_EXPORT_ATTRIBUTES.get(mapping.device_class)
    if allowed_attributes is None or mapping.attribute not in allowed_attributes:
        return None

    return mapping


def build_devices_payload(
    hass: HomeAssistant,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build a HubConnect /devices/get payload from current HA states."""

    grouped_devices: dict[str, list[dict[str, Any]]] = {}
    selected_entity_ids = set(selected_entity_ids or [])

    for state in hass.states.async_all():
        if state.entity_id not in selected_entity_ids:
            continue

        if state.state in UNKNOWN_STATES:
            continue

        mapping = get_entity_mapping(state)
        if mapping is None:
            continue

        grouped_devices.setdefault(mapping.device_class, []).append(
            {
                "id": state.entity_id,
                "label": friendly_name(state),
                "attr": [build_attribute_payload(state, mapping)],
                "commands": build_command_payload(state),
            }
        )

    return [
        {"deviceclass": device_class, "devices": devices}
        for device_class, devices in sorted(grouped_devices.items())
    ]


def build_export_requirements(
    hass: HomeAssistant,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build required HubConnect driver details for selected HA exports."""

    requirements: dict[str, dict[str, Any]] = {}

    for state in _selected_states(hass, selected_entity_ids):
        if state.state in UNKNOWN_STATES:
            continue

        mapping = get_entity_mapping(state)
        if mapping is None:
            continue

        requirement = requirements.setdefault(
            mapping.device_class,
            {
                "deviceclass": mapping.device_class,
                "driver": HUBCONNECT_EXPORT_DRIVERS[mapping.device_class],
                "attributes": set(),
                "entities": [],
            },
        )
        requirement["attributes"].add(mapping.attribute)
        requirement["entities"].append(
            {
                "entity_id": state.entity_id,
                "label": friendly_name(state),
                "attribute": mapping.attribute,
            }
        )

    return [
        {
            **requirement,
            "attributes": sorted(requirement["attributes"]),
            "entities": sorted(
                requirement["entities"],
                key=lambda entity: entity["entity_id"],
            ),
        }
        for requirement in sorted(
            requirements.values(),
            key=lambda requirement: requirement["deviceclass"],
        )
    ]


def build_unsupported_exports(
    hass: HomeAssistant,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return selected HA entities that will not be exported."""

    unsupported: list[dict[str, Any]] = []

    for state in _selected_states(hass, selected_entity_ids):
        reason = ""
        if state.state in UNKNOWN_STATES:
            reason = f"state is {state.state}"
        elif get_entity_mapping(state) is None:
            reason = "unsupported domain or device_class"

        if reason:
            unsupported.append(
                {
                    "entity_id": state.entity_id,
                    "label": friendly_name(state),
                    "domain": state.entity_id.split(".", 1)[0],
                    "device_class": state.attributes.get("device_class"),
                    "state": state.state,
                    "reason": reason,
                }
            )

    selected_ids = {str(entity_id) for entity_id in selected_entity_ids or []}
    known_ids = {state.entity_id for state in hass.states.async_all()}
    for entity_id in sorted(selected_ids - known_ids):
        unsupported.append(
            {
                "entity_id": entity_id,
                "label": entity_id,
                "domain": entity_id.split(".", 1)[0],
                "device_class": None,
                "state": "missing",
                "reason": "entity not found",
            }
        )

    return sorted(unsupported, key=lambda entity: entity["entity_id"])


def build_sync_payload(state: State, requested_device_class: str) -> dict[str, Any]:
    """Build a HubConnect device sync payload."""

    mapping = get_entity_mapping(state)
    if mapping is None:
        return {"status": "error", "message": "unsupported device"}

    if requested_device_class != mapping.device_class:
        return {"status": "error", "message": "device class mismatch"}

    return {
        "status": "success",
        "name": state.entity_id,
        "label": friendly_name(state),
        "currentValues": [build_attribute_payload(state, mapping)],
    }


def build_attribute_payload(state: State, mapping: EntityMapping) -> dict[str, Any]:
    """Build one HubConnect attribute payload."""

    return {
        "name": mapping.attribute,
        "value": hubconnect_value(state, mapping),
        "unit": state.attributes.get("unit_of_measurement") or mapping.unit,
    }


def hubconnect_value(state: State, mapping: EntityMapping) -> str:
    """Translate HA state values into HubConnect attribute values."""

    if state.state in UNKNOWN_STATES:
        return state.state

    if mapping.attribute == "contact":
        return "open" if state.state == "on" else "closed"

    if mapping.attribute in {"motion", "acceleration"}:
        return "active" if state.state == "on" else "inactive"

    if mapping.attribute == "presence":
        return "present" if state.state == "on" else "not present"

    if mapping.attribute == "water":
        return "wet" if state.state == "on" else "dry"

    if mapping.attribute in {"smoke", "carbonMonoxide"}:
        return "detected" if state.state == "on" else "clear"

    return state.state


def build_command_payload(state: State) -> dict[str, list[dict[str, Any]]]:
    """Return a minimal HubConnect command map for an HA entity."""

    domain = state.entity_id.split(".", 1)[0]

    if domain in {"switch", "light"}:
        return {"on": [], "off": []}

    return {}


async def async_execute_command(
    hass: HomeAssistant,
    entity_id: str,
    command: str,
    encoded_params: str,
) -> dict[str, str]:
    """Execute a HubConnect command against a Home Assistant entity."""

    state = hass.states.get(entity_id)
    if state is None:
        return {"status": "error", "message": "device not found"}

    if command == "uninstalled":
        return {"status": "success"}

    mapping = get_entity_mapping(state)
    if mapping is None:
        return {"status": "error", "message": "unsupported device"}

    domain = entity_id.split(".", 1)[0]

    if command in {"on", "off"} and domain in {"switch", "light"}:
        await hass.services.async_call(
            "homeassistant",
            f"turn_{command}",
            {"entity_id": entity_id},
            blocking=True,
        )
        return {"status": "success"}

    if command == "setLevel" and domain == "light":
        params = _decode_command_params(encoded_params)
        if not params:
            return {"status": "error", "message": "missing level"}

        level = max(0, min(100, int(params[0])))
        brightness = round(level * 255 / 100)
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": entity_id, "brightness": brightness},
            blocking=True,
        )
        return {"status": "success"}

    return {"status": "error", "message": f"unsupported command: {command}"}


def _decode_command_params(encoded_params: str) -> list[Any]:
    """Decode HubConnect command params from a URL path segment."""

    if encoded_params == "null":
        return []

    decoded = unquote(encoded_params)
    params = json.loads(decoded)
    if isinstance(params, list):
        return params

    return []


def friendly_name(state: State) -> str:
    """Return the best display name for an HA state."""

    return state.attributes.get("friendly_name") or state.entity_id


def _selected_states(
    hass: HomeAssistant,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> list[State]:
    """Return HA states matching selected entity ids."""

    selected_ids = {str(entity_id) for entity_id in selected_entity_ids or []}
    return [
        state
        for state in hass.states.async_all()
        if state.entity_id in selected_ids
    ]
