"""Base entity for HubConnect Hubitat shadow entities."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN
from .shadow import (
    SIGNAL_SHADOW_ENTITY_UPDATED,
    ShadowEntityDescription,
    get_shadow_registry,
)


class HubConnectShadowEntity:
    """Mixin for Hubitat entities mirrored into Home Assistant."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, description: ShadowEntityDescription) -> None:
        """Initialize the entity."""

        self._description = description
        self._attr_unique_id = description.unique_id
        self._attr_name = description.attribute
        self._sync_device_info()

    def _sync_device_info(self) -> None:
        """Refresh Home Assistant device metadata from the shadow description."""

        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._description.device_id)},
            "name": self._description.label,
            "manufacturer": "Hubitat",
            "model": f"HubConnect {self._description.device_class}",
        }

    @callback
    def async_refresh_from_shadow(self) -> None:
        """Refresh this entity from the shared shadow registry."""

        description = get_shadow_registry(self.hass).entities.get(self.unique_id)
        if description is not None:
            self._description = description
            self._sync_device_info()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to shadow entity updates."""

        live_entities = self.hass.data.setdefault(DOMAIN, {}).setdefault(
            "_shadow_entities", {}
        )
        live_entities[self.unique_id] = self
        self.async_on_remove(lambda: live_entities.pop(self.unique_id, None))
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_SHADOW_ENTITY_UPDATED}_{self._description.unique_id}",
                self.async_refresh_from_shadow,
            )
        )
