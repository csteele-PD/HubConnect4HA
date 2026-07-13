"""Binary sensor platform for HubConnect Hubitat shadow entities."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import HubConnectShadowEntity
from .shadow import SIGNAL_SHADOW_DEVICES_UPDATED, get_shadow_registry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HubConnect binary sensor entities."""

    known: set[str] = set()
    registry = get_shadow_registry(hass)
    registry.log_platform_event("binary_sensor", "setup")

    @callback
    def add_new_entities() -> None:
        registry = get_shadow_registry(hass)
        try:
            entities = []
            for description in registry.entities.values():
                if description.platform.value != "binary_sensor":
                    continue
                if description.unique_id in known:
                    continue
                entities.append(HubConnectShadowBinarySensor(description))

            if entities:
                for entity in entities:
                    known.add(entity.unique_id)
                registry.log_platform_event("binary_sensor", "add", len(entities))
                async_add_entities(entities)
            else:
                registry.log_platform_event("binary_sensor", "add_none", 0)
        except Exception as err:  # noqa: BLE001
            registry.log_platform_event("binary_sensor", "error", 0, repr(err))

    add_new_entities()
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SHADOW_DEVICES_UPDATED, add_new_entities)
    )


class HubConnectShadowBinarySensor(BinarySensorEntity, HubConnectShadowEntity):
    """Binary sensor entity mirrored from Hubitat."""

    def __init__(self, description) -> None:
        """Initialize the binary sensor."""

        HubConnectShadowEntity.__init__(self, description)
        self._attr_device_class = description.ha_device_class

    async def async_added_to_hass(self) -> None:
        """Register live shadow update hooks."""

        await HubConnectShadowEntity.async_added_to_hass(self)

    @property
    def is_on(self) -> bool | None:
        """Return true if the sensor is on."""

        if self._description.value is None:
            return None
        return str(self._description.value) in self._description.on_values
