"""Switch platform for HubConnect Hubitat shadow entities."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    """Set up HubConnect switch entities."""

    known: set[str] = set()
    registry = get_shadow_registry(hass)
    registry.log_platform_event("switch", "setup")

    @callback
    def add_new_entities() -> None:
        registry = get_shadow_registry(hass)
        try:
            entities = []
            for description in registry.entities.values():
                if description.platform.value != "switch":
                    continue
                if description.unique_id in known:
                    continue
                entities.append(HubConnectShadowSwitch(description))

            if entities:
                for entity in entities:
                    known.add(entity.unique_id)
                registry.log_platform_event("switch", "add", len(entities))
                async_add_entities(entities)
            else:
                registry.log_platform_event("switch", "add_none", 0)
        except Exception as err:  # noqa: BLE001
            registry.log_platform_event("switch", "error", 0, repr(err))

    add_new_entities()
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SHADOW_DEVICES_UPDATED, add_new_entities)
    )


class HubConnectShadowSwitch(SwitchEntity, HubConnectShadowEntity):
    """Switch entity mirrored from Hubitat."""

    def __init__(self, description) -> None:
        """Initialize the switch."""

        HubConnectShadowEntity.__init__(self, description)

    async def async_added_to_hass(self) -> None:
        """Register live shadow update hooks."""

        await HubConnectShadowEntity.async_added_to_hass(self)

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""

        if self._description.value is None:
            return None
        return str(self._description.value) == "on"

    async def async_turn_on(self, **kwargs) -> None:
        """Optimistically turn the shadow switch on."""

        self._description.value = "on"
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Optimistically turn the shadow switch off."""

        self._description.value = "off"
        self.async_write_ha_state()
