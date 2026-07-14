"""Hubitat shadow device registry for HubConnect."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .mapping import get_attribute_mapping, normalize_unit

SIGNAL_SHADOW_DEVICES_UPDATED = f"{DOMAIN}_shadow_devices_updated"
SIGNAL_SHADOW_ENTITY_UPDATED = f"{DOMAIN}_shadow_entity_updated"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_shadows"


@dataclass(slots=True)
class ShadowEntityDescription:
    """One HA entity created from a Hubitat device attribute."""

    device_id: str
    device_class: str
    label: str
    attribute: str
    value: Any
    unit: str = ""

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""

        return f"{self.device_id}_{self.attribute}"

    @property
    def platform(self) -> Platform:
        """Return the HA platform for this entity."""

        return get_attribute_mapping(self.attribute).platform

    @property
    def ha_device_class(self):
        """Return the HA device class for this entity."""

        return get_attribute_mapping(self.attribute).device_class

    @property
    def on_values(self) -> frozenset[str]:
        """Return values considered on/true for this attribute."""

        return get_attribute_mapping(self.attribute).on_values


@dataclass(slots=True)
class ShadowRegistry:
    """Runtime registry of Hubitat devices sent to Home Assistant."""

    entities: dict[str, ShadowEntityDescription] = field(default_factory=dict)
    requests: list[dict[str, Any]] = field(default_factory=list)
    platform_events: list[dict[str, Any]] = field(default_factory=list)
    export_pushes: list[dict[str, Any]] = field(default_factory=list)

    def log_request(self, method: str, path: str, status: str, detail: str = "") -> None:
        """Store a small in-memory request log."""

        self.requests.append(
            {
                "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "method": method,
                "path": path,
                "status": status,
                "detail": detail,
            }
        )
        self.requests = self.requests[-50:]

    def log_platform_event(
        self, platform: str, event: str, count: int = 0, detail: str = ""
    ) -> None:
        """Store a small in-memory platform/entity log."""

        self.platform_events.append(
            {
                "platform": platform,
                "event": event,
                "count": count,
                "detail": detail,
            }
        )
        self.platform_events = self.platform_events[-50:]

    def log_export_push(
        self,
        target: str,
        status: str,
        detail: str = "",
        payload: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
    ) -> None:
        """Store a small in-memory log of HA-to-Hubitat export pushes."""

        self.export_pushes.append(
            {
                "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "target": target,
                "status": status,
                "detail": detail,
                "payload": payload,
                "response": response,
            }
        )
        self.export_pushes = self.export_pushes[-50:]

    def upsert_devices(self, device_class: str, devices: list[dict[str, Any]]) -> None:
        """Create or update shadow entities from HubConnect devices/save data."""

        for device in devices:
            device_id = str(device["id"])
            label = str(device.get("label") or device_id)
            for attr in device.get("attr") or []:
                attribute = str(attr.get("name"))
                unique_id = f"{device_id}_{attribute}"
                unit = normalize_unit(attribute, attr.get("unit"))
                if unique_id in self.entities:
                    entity = self.entities[unique_id]
                    entity.device_class = device_class
                    entity.label = label
                    entity.value = attr.get("value")
                    entity.unit = unit
                else:
                    self.entities[unique_id] = ShadowEntityDescription(
                        device_id=device_id,
                        device_class=device_class,
                        label=label,
                        attribute=attribute,
                        value=attr.get("value"),
                        unit=unit,
                    )

    def cleanup(self, device_ids: list[Any]) -> list[str]:
        """Remove shadow entities not in Hubitat's cleanup list."""

        keep_ids = {str(device_id) for device_id in device_ids}
        removed_unique_ids = [
            unique_id
            for unique_id, entity in self.entities.items()
            if entity.device_id not in keep_ids
        ]
        self.entities = {
            unique_id: entity
            for unique_id, entity in self.entities.items()
            if entity.device_id in keep_ids
        }
        return removed_unique_ids

    def update_event(self, device_id: str, event: dict[str, Any]) -> bool:
        """Update a shadow entity from a HubConnect event payload."""

        attribute = str(event.get("name"))
        unique_id = f"{device_id}_{attribute}"
        entity = self.entities.get(unique_id)
        if entity is None:
            device_entities = [
                entity
                for entity in self.entities.values()
                if entity.device_id == str(device_id)
            ]
            if not device_entities:
                return False

            existing = device_entities[0]
            entity = ShadowEntityDescription(
                device_id=str(device_id),
                device_class=existing.device_class,
                label=str(event.get("displayName") or existing.label),
                attribute=attribute,
                value=event.get("value"),
                unit=normalize_unit(attribute, event.get("unit")),
            )
            self.entities[unique_id] = entity
            return True

        entity.value = event.get("value")
        entity.unit = normalize_unit(attribute, event.get("unit")) or entity.unit
        return True

    def as_dict(self) -> dict[str, Any]:
        """Return a debug representation of the shadow registry."""

        return {
            unique_id: {
                "device_id": entity.device_id,
                "device_class": entity.device_class,
                "label": entity.label,
                "attribute": entity.attribute,
                "value": entity.value,
                "unit": entity.unit,
                "platform": entity.platform.value,
            }
            for unique_id, entity in sorted(self.entities.items())
        }

    def to_storage(self) -> dict[str, Any]:
        """Return storage data for persisted shadows."""

        return {"entities": self.as_dict()}

    def load_storage(self, data: dict[str, Any] | None) -> None:
        """Load persisted shadows."""

        if not data:
            return

        self.entities = {
            unique_id: ShadowEntityDescription(
                device_id=str(entity["device_id"]),
                device_class=str(entity["device_class"]),
                label=str(entity["label"]),
                attribute=str(entity["attribute"]),
                value=entity.get("value"),
                unit=normalize_unit(
                    str(entity["attribute"]),
                    entity.get("unit"),
                ),
            )
            for unique_id, entity in data.get("entities", {}).items()
        }


def get_shadow_registry(hass: HomeAssistant) -> ShadowRegistry:
    """Return the shared shadow registry."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    registry = domain_data.get("_shadow_registry")
    if registry is None:
        registry = ShadowRegistry()
        domain_data["_shadow_registry"] = registry
    return registry


def get_shadow_store(hass: HomeAssistant) -> Store:
    """Return the storage helper for shadow entities."""

    return Store(hass, STORAGE_VERSION, STORAGE_KEY)


async def async_load_shadow_registry(hass: HomeAssistant) -> ShadowRegistry:
    """Load the shadow registry from storage."""

    registry = get_shadow_registry(hass)
    registry.load_storage(await get_shadow_store(hass).async_load())
    return registry


async def async_save_shadow_registry(hass: HomeAssistant) -> None:
    """Persist the shadow registry to storage."""

    registry = get_shadow_registry(hass)
    await get_shadow_store(hass).async_save(registry.to_storage())


def notify_shadow_devices_updated(hass: HomeAssistant) -> None:
    """Notify platforms that shadow devices changed."""

    async_dispatcher_send(hass, SIGNAL_SHADOW_DEVICES_UPDATED)


def notify_shadow_entity_updated(hass: HomeAssistant, unique_id: str) -> None:
    """Notify one entity that its value changed."""

    async_dispatcher_send(hass, f"{SIGNAL_SHADOW_ENTITY_UPDATED}_{unique_id}")
