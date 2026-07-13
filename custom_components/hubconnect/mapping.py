"""Central HubConnect attribute mapping table."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform


@dataclass(frozen=True, slots=True)
class AttributeMapping:
    """Home Assistant mapping for one HubConnect attribute."""

    platform: Platform
    device_class: str | None = None
    default_unit: str = ""
    on_values: frozenset[str] = frozenset()


ATTRIBUTE_MAPPINGS: dict[str, AttributeMapping] = {
    "acceleration": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.VIBRATION,
        on_values=frozenset({"active"}),
    ),
    "battery": AttributeMapping(Platform.SENSOR, SensorDeviceClass.BATTERY, "%"),
    "carbonMonoxide": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.CO,
        on_values=frozenset({"detected"}),
    ),
    "contact": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.OPENING,
        on_values=frozenset({"open"}),
    ),
    "current": AttributeMapping(Platform.SENSOR, SensorDeviceClass.CURRENT, "A"),
    "energy": AttributeMapping(Platform.SENSOR, SensorDeviceClass.ENERGY),
    "humidity": AttributeMapping(Platform.SENSOR, SensorDeviceClass.HUMIDITY, "%"),
    "illuminance": AttributeMapping(
        Platform.SENSOR,
        SensorDeviceClass.ILLUMINANCE,
        "lx",
    ),
    "lock": AttributeMapping(Platform.BINARY_SENSOR, BinarySensorDeviceClass.LOCK),
    "motion": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.MOTION,
        on_values=frozenset({"active"}),
    ),
    "power": AttributeMapping(Platform.SENSOR, SensorDeviceClass.POWER, "W"),
    "presence": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.PRESENCE,
        on_values=frozenset({"present"}),
    ),
    "pressure": AttributeMapping(Platform.SENSOR, SensorDeviceClass.PRESSURE),
    "smoke": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.SMOKE,
        on_values=frozenset({"detected"}),
    ),
    "sound": AttributeMapping(Platform.BINARY_SENSOR, BinarySensorDeviceClass.SOUND),
    "switch": AttributeMapping(
        Platform.SWITCH,
        on_values=frozenset({"on"}),
    ),
    "tamper": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.TAMPER,
        on_values=frozenset({"detected", "tampered"}),
    ),
    "temperature": AttributeMapping(Platform.SENSOR, SensorDeviceClass.TEMPERATURE),
    "ultravioletIndex": AttributeMapping(Platform.SENSOR),
    "valve": AttributeMapping(Platform.BINARY_SENSOR, BinarySensorDeviceClass.OPENING),
    "voltage": AttributeMapping(Platform.SENSOR, SensorDeviceClass.VOLTAGE, "V"),
    "water": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.MOISTURE,
        on_values=frozenset({"wet"}),
    ),
}

DEFAULT_MAPPING = AttributeMapping(Platform.SENSOR)


def get_attribute_mapping(attribute: str) -> AttributeMapping:
    """Return the mapping for a HubConnect attribute."""

    return ATTRIBUTE_MAPPINGS.get(attribute, DEFAULT_MAPPING)


def normalize_unit(attribute: str, unit: object) -> str:
    """Normalize HubConnect units for Home Assistant."""

    if unit is None or str(unit).lower() == "null":
        return get_attribute_mapping(attribute).default_unit

    normalized = str(unit)
    if normalized == "lux":
        return "lx"

    return normalized
