"""Helpers for translating Home Assistant state into HubConnect payloads."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import unquote

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er


UNKNOWN_STATES = {"unknown", "unavailable"}
EXPORT_DEVICE_PREFIX = "ha_device_"


@dataclass(frozen=True, slots=True)
class EntityMapping:
    """HubConnect mapping for a Home Assistant entity."""

    device_class: str
    attribute: str
    unit: str = ""


@dataclass(slots=True)
class ExportGroup:
    """A group of HA entities that should become one HubConnect child device."""

    id: str
    label: str
    device_class: str
    states: list[tuple[State, EntityMapping]]


# HubConnect deviceclass keys must match the Groovy NATIVE_DEVICES table. Prefer
# standard mirror drivers when they exist; use v_* only for standalone synthetic
# measurements where HubConnect has no plain native class.
HUBCONNECT_EXPORT_ATTRIBUTES: dict[str, set[str]] = {
    "contact": {"contact", "temperature", "battery"},
    "dimmer": {"switch", "level"},
    "energy": {"energy"},
    "moisture": {"water", "temperature", "battery"},
    "motion": {"motion", "temperature", "battery"},
    "omnipurpose": {
        "motion",
        "temperature",
        "humidity",
        "illuminance",
        "ultravioletIndex",
        "tamper",
        "battery",
    },
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
    "omnipurpose": "HubConnect Omnipurpose Sensor",
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
    for group in build_export_groups(hass, selected_entity_ids):
        grouped_devices.setdefault(group.device_class, []).append(
            {
                "id": group.id,
                "label": group.label,
                "attr": [
                    build_attribute_payload(state, mapping)
                    for state, mapping in group.states
                ],
                "commands": build_group_command_payload(group),
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

    for group in build_export_groups(hass, selected_entity_ids):
        requirement = requirements.setdefault(
            group.device_class,
            {
                "deviceclass": group.device_class,
                "driver": HUBCONNECT_EXPORT_DRIVERS[group.device_class],
                "attributes": set(),
                "entities": [],
            },
        )
        for state, mapping in group.states:
            requirement["attributes"].add(mapping.attribute)
            requirement["entities"].append(
                {
                    "entity_id": state.entity_id,
                    "export_id": group.id,
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


def build_cleanup_device_ids(
    hass: HomeAssistant,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> list[str]:
    """Return exported HubConnect ids that should be preserved on cleanup."""

    cleanup_ids: set[str] = set()
    selected_ids = set(selected_entity_ids or [])
    for state in _selected_states(hass, selected_ids):
        if get_entity_mapping(state) is None:
            continue
        cleanup_ids.add(export_device_id_for_state(hass, state, selected_ids))

    return sorted(cleanup_ids)


def build_sync_payload(
    hass: HomeAssistant,
    device_id: str,
    requested_device_class: str,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Build a HubConnect device sync payload."""

    group = find_export_group(hass, device_id, selected_entity_ids)
    if group is None:
        return {"status": "error", "message": "device not found"}

    if requested_device_class != group.device_class:
        return {"status": "error", "message": "device class mismatch"}

    return {
        "status": "success",
        "name": group.id,
        "label": group.label,
        "currentValues": [
            build_attribute_payload(state, mapping)
            for state, mapping in group.states
        ],
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


def build_group_command_payload(group: ExportGroup) -> dict[str, list[dict[str, Any]]]:
    """Return the HubConnect command map for a grouped export."""

    commands: dict[str, list[dict[str, Any]]] = {}
    for state, _mapping in group.states:
        commands.update(build_command_payload(state))
    return commands


async def async_execute_command(
    hass: HomeAssistant,
    device_id: str,
    command: str,
    encoded_params: str,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> dict[str, str]:
    """Execute a HubConnect command against a Home Assistant entity."""

    state = _command_target_state(hass, device_id, selected_entity_ids)
    if state is None:
        return {"status": "error", "message": "device not found"}

    if command == "uninstalled":
        return {"status": "success"}

    mapping = get_entity_mapping(state)
    if mapping is None:
        return {"status": "error", "message": "unsupported device"}

    domain = state.entity_id.split(".", 1)[0]

    if command in {"on", "off"} and domain in {"switch", "light"}:
        await hass.services.async_call(
            "homeassistant",
            f"turn_{command}",
            {"entity_id": state.entity_id},
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
            {"entity_id": state.entity_id, "brightness": brightness},
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


def build_export_groups(
    hass: HomeAssistant,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> list[ExportGroup]:
    """Build grouped HA exports that should map to Hubitat child devices."""

    groups: dict[str, ExportGroup] = {}

    for state in _selected_states(hass, selected_entity_ids):
        if state.state in UNKNOWN_STATES:
            continue

        mapping = get_entity_mapping(state)
        if mapping is None:
            continue

        export_base_id = _export_device_base_id_for_state(hass, state)
        potential_attributes = _potential_attributes_for_state_device(hass, state)
        device_class = _best_device_class_for_attributes(potential_attributes)
        export_id = export_base_id
        if device_class is None:
            device_class = mapping.device_class
            export_id = f"{export_base_id}_{device_class}"
        if mapping.attribute not in HUBCONNECT_EXPORT_ATTRIBUTES.get(
            device_class,
            set(),
        ):
            continue

        group = groups.setdefault(
            export_id,
            ExportGroup(
                id=export_id,
                label=export_device_label(hass, state),
                device_class=device_class,
                states=[],
            ),
        )
        group.states.append((state, mapping))

    for group in groups.values():
        group.states.sort(key=lambda item: item[1].attribute)

    return sorted(groups.values(), key=lambda group: group.id)


def find_export_group(
    hass: HomeAssistant,
    device_id: str,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> ExportGroup | None:
    """Find an exported HA device group by HubConnect device id."""

    for group in build_export_groups(hass, selected_entity_ids):
        if group.id == device_id:
            return group
    return None


def export_device_id_for_state(
    hass: HomeAssistant,
    state: State,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> str:
    """Return the HubConnect device id for an exported HA state."""

    for group in build_export_groups(hass, selected_entity_ids):
        if any(
            group_state.entity_id == state.entity_id
            for group_state, _mapping in group.states
        ):
            return group.id
    return _export_device_base_id_for_state(hass, state)


def export_device_label_for_state(
    hass: HomeAssistant,
    state: State,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> str:
    """Return the HubConnect device label for an exported HA state."""

    for group in build_export_groups(hass, selected_entity_ids):
        if any(
            group_state.entity_id == state.entity_id
            for group_state, _mapping in group.states
        ):
            return group.label
    return export_device_label(hass, state)


def _export_device_base_id_for_state(hass: HomeAssistant, state: State) -> str:
    """Return the base HubConnect device id for an exported HA state."""

    device_id = _ha_device_id_for_state(hass, state)
    if device_id:
        return f"{EXPORT_DEVICE_PREFIX}{device_id}"
    return state.entity_id


def export_device_label(hass: HomeAssistant, state: State) -> str:
    """Return the HubConnect device label for an exported HA state."""

    device_id = _ha_device_id_for_state(hass, state)
    if not device_id:
        return friendly_name(state)

    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return friendly_name(state)

    return (
        device.name_by_user
        or device.name
        or device.model
        or device.manufacturer
        or friendly_name(state)
    )


def _best_device_class_for_attributes(attributes: set[str]) -> str | None:
    """Choose the most specific HubConnect class for a set of attributes."""

    candidates = [
        device_class
        for device_class, supported_attributes in HUBCONNECT_EXPORT_ATTRIBUTES.items()
        if attributes <= supported_attributes
    ]
    if not candidates:
        return None

    return sorted(
        candidates,
        key=lambda device_class: (
            len(HUBCONNECT_EXPORT_ATTRIBUTES[device_class] - attributes),
            device_class.startswith("v_"),
            device_class,
        ),
    )[0]


def _potential_attributes_for_state_device(
    hass: HomeAssistant,
    state: State,
) -> set[str]:
    """Return all exportable HubConnect attrs on the same HA device."""

    device_id = _ha_device_id_for_state(hass, state)
    if not device_id:
        mapping = get_entity_mapping(state)
        return {mapping.attribute} if mapping else set()

    attributes: set[str] = set()
    registry = er.async_get(hass)
    for entry in er.async_entries_for_device(registry, device_id):
        possible_state = hass.states.get(entry.entity_id)
        if possible_state is None:
            continue
        mapping = get_entity_mapping(possible_state)
        if mapping is not None:
            attributes.add(mapping.attribute)
    return attributes


def _ha_device_id_for_state(hass: HomeAssistant, state: State) -> str | None:
    """Return the HA device registry id for a state, if one exists."""

    entry = er.async_get(hass).async_get(state.entity_id)
    return entry.device_id if entry else None


def _command_target_state(
    hass: HomeAssistant,
    device_id: str,
    selected_entity_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> State | None:
    """Return the selected HA entity that can execute a HubConnect command."""

    direct_state = hass.states.get(device_id)
    if direct_state is not None:
        return direct_state

    group = find_export_group(hass, device_id, selected_entity_ids)
    if group is None:
        return None

    for state, _mapping in group.states:
        if state.entity_id.split(".", 1)[0] in {"switch", "light"}:
            return state
    return group.states[0][0] if group.states else None


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
