"""Cover platform for HubConnect Hubitat shadow entities."""

from __future__ import annotations

from homeassistant.components.cover import CoverDeviceClass, CoverEntity
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
    """Set up HubConnect cover entities."""

    known: set[str] = set()
    registry = get_shadow_registry(hass)
    registry.log_platform_event("cover", "setup")

    @callback
    def add_new_entities() -> None:
        registry = get_shadow_registry(hass)
        try:
            entities = []
            for description in registry.entities.values():
                if description.platform.value != "cover":
                    continue
                if description.unique_id in known:
                    continue
                entities.append(HubConnectShadowCover(description))

            if entities:
                for entity in entities:
                    known.add(entity.unique_id)
                registry.log_platform_event("cover", "add", len(entities))
                async_add_entities(entities)
            else:
                registry.log_platform_event("cover", "add_none", 0)
        except Exception as err:  # noqa: BLE001
            registry.log_platform_event("cover", "error", 0, repr(err))

    add_new_entities()
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SHADOW_DEVICES_UPDATED, add_new_entities)
    )


class HubConnectShadowCover(CoverEntity, HubConnectShadowEntity):
    """Cover entity mirrored from Hubitat."""

    def __init__(self, description) -> None:
        """Initialize the cover."""

        HubConnectShadowEntity.__init__(self, description)
        if description.attribute == "door":
            self._attr_device_class = CoverDeviceClass.GARAGE
        elif description.attribute == "windowShade":
            self._attr_device_class = CoverDeviceClass.SHADE

    async def async_added_to_hass(self) -> None:
        """Register live shadow update hooks."""

        await HubConnectShadowEntity.async_added_to_hass(self)

    @property
    def is_closed(self) -> bool | None:
        """Return true if the cover is closed."""

        if self._description.value is None:
            return None

        value = str(self._description.value).lower()
        if value in {"closed", "close"}:
            return True
        if value in {"open", "opening", "closing", "partially open"}:
            return False
        return None

    @property
    def is_opening(self) -> bool:
        """Return true if the cover is opening."""

        return str(self._description.value).lower() == "opening"

    @property
    def is_closing(self) -> bool:
        """Return true if the cover is closing."""

        return str(self._description.value).lower() == "closing"
