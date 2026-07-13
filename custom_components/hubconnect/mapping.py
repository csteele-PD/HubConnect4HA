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
    "alarm": AttributeMapping(Platform.SENSOR),
    "battery": AttributeMapping(Platform.SENSOR, SensorDeviceClass.BATTERY, "%"),
    "button": AttributeMapping(Platform.SENSOR),
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
    "coolingSetpoint": AttributeMapping(Platform.CLIMATE),
    "codeChanged": AttributeMapping(Platform.SENSOR),
    "codeLength": AttributeMapping(Platform.SENSOR),
    "current": AttributeMapping(Platform.SENSOR, SensorDeviceClass.CURRENT, "A"),
    "door": AttributeMapping(Platform.COVER),
    "doubleTapped": AttributeMapping(Platform.SENSOR),
    "energy": AttributeMapping(Platform.SENSOR, SensorDeviceClass.ENERGY),
    "heatingSetpoint": AttributeMapping(Platform.CLIMATE),
    "held": AttributeMapping(Platform.SENSOR),
    "hue": AttributeMapping(Platform.SENSOR, default_unit="%"),
    "humidity": AttributeMapping(Platform.SENSOR, SensorDeviceClass.HUMIDITY, "%"),
    "illuminance": AttributeMapping(
        Platform.SENSOR,
        SensorDeviceClass.ILLUMINANCE,
        "lx",
    ),
    "lastCodeName": AttributeMapping(Platform.SENSOR),
    "level": AttributeMapping(Platform.SENSOR, default_unit="%"),
    "lock": AttributeMapping(Platform.BINARY_SENSOR, BinarySensorDeviceClass.LOCK),
    "lockCodes": AttributeMapping(Platform.SENSOR),
    "maxCodes": AttributeMapping(Platform.SENSOR),
    "motion": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.MOTION,
        on_values=frozenset({"active"}),
    ),
    "mute": AttributeMapping(
        Platform.BINARY_SENSOR,
        on_values=frozenset({"muted", "on", "true"}),
    ),
    "numberOfButtons": AttributeMapping(Platform.SENSOR),
    "position": AttributeMapping(Platform.SENSOR, default_unit="%"),
    "power": AttributeMapping(Platform.SENSOR, SensorDeviceClass.POWER, "W"),
    "presence": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.PRESENCE,
        on_values=frozenset({"present"}),
    ),
    "pressure": AttributeMapping(Platform.SENSOR, SensorDeviceClass.PRESSURE),
    "pushed": AttributeMapping(Platform.SENSOR),
    "released": AttributeMapping(Platform.SENSOR),
    "saturation": AttributeMapping(Platform.SENSOR, default_unit="%"),
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
    "supportedThermostatFanModes": AttributeMapping(Platform.CLIMATE),
    "supportedThermostatModes": AttributeMapping(Platform.CLIMATE),
    "temperature": AttributeMapping(Platform.SENSOR, SensorDeviceClass.TEMPERATURE),
    "thermostatFanMode": AttributeMapping(Platform.CLIMATE),
    "thermostatMode": AttributeMapping(Platform.CLIMATE),
    "thermostatOperatingState": AttributeMapping(Platform.CLIMATE),
    "thermostatSetpoint": AttributeMapping(Platform.CLIMATE),
    "ultravioletIndex": AttributeMapping(Platform.SENSOR),
    "valve": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.OPENING,
        on_values=frozenset({"open"}),
    ),
    "version": AttributeMapping(Platform.SENSOR),
    "voltage": AttributeMapping(Platform.SENSOR, SensorDeviceClass.VOLTAGE, "V"),
    "volume": AttributeMapping(Platform.SENSOR, default_unit="%"),
    "water": AttributeMapping(
        Platform.BINARY_SENSOR,
        BinarySensorDeviceClass.MOISTURE,
        on_values=frozenset({"wet"}),
    ),
    "windowShade": AttributeMapping(Platform.COVER),
}

DEFAULT_MAPPING = AttributeMapping(Platform.SENSOR)


def get_attribute_mapping(attribute: str) -> AttributeMapping:
    """Return the mapping for a HubConnect attribute."""

    return ATTRIBUTE_MAPPINGS.get(attribute, DEFAULT_MAPPING)


def normalize_unit(attribute: str, unit: object) -> str:
    """Normalize HubConnect units for Home Assistant."""

    if unit is None or str(unit).strip() == "" or str(unit).lower() == "null":
        return get_attribute_mapping(attribute).default_unit

    normalized = str(unit)
    if normalized == "lux":
        return "lx"

    return normalized
