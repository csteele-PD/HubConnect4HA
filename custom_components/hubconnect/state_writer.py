"""Prototype state writer for Hubitat shadow entities."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .shadow import ShadowEntityDescription, get_shadow_registry


def write_shadow_states(hass: HomeAssistant) -> None:
    """Write shadow entities directly to HA states as a prototype fallback."""

    registry = get_shadow_registry(hass)
    for entity in registry.entities.values():
        entity_id = _state_entity_id(entity)
        value = entity.value
        if entity.platform.value == "binary_sensor":
            value = "on" if str(entity.value) in entity.on_values else "off"

        hass.states.async_set(
            entity_id,
            value if value is not None else "unknown",
            {
                "friendly_name": f"{entity.label} {entity.attribute}",
                "hubconnect_device_id": entity.device_id,
                "hubconnect_device_class": entity.device_class,
                "hubconnect_attribute": entity.attribute,
                "unit_of_measurement": entity.unit,
                "device_class": entity.ha_device_class,
            },
        )


def _state_entity_id(entity: ShadowEntityDescription) -> str:
    """Return a deterministic fallback entity id."""

    platform = entity.platform.value
    slug = "".join(
        char.lower() if char.isalnum() else "_"
        for char in f"hubconnect_{entity.device_id}_{entity.attribute}"
    )
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"{platform}.{slug.strip('_')}"
