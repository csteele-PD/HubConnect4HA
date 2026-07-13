"""Climate platform for HubConnect Hubitat shadow entities."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.components.climate.const import HVACAction
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import HubConnectShadowEntity
from .shadow import (
    SIGNAL_SHADOW_DEVICES_UPDATED,
    SIGNAL_SHADOW_ENTITY_UPDATED,
    ShadowEntityDescription,
    get_shadow_registry,
)

THERMOSTAT_ATTRIBUTES = {
    "coolingSetpoint",
    "heatingSetpoint",
    "supportedThermostatFanModes",
    "supportedThermostatModes",
    "temperature",
    "thermostatFanMode",
    "thermostatMode",
    "thermostatOperatingState",
    "thermostatSetpoint",
}

MODE_MAP = {
    "auto": HVACMode.HEAT_COOL,
    "cool": HVACMode.COOL,
    "emergency heat": HVACMode.HEAT,
    "heat": HVACMode.HEAT,
    "off": HVACMode.OFF,
}

ACTION_MAP = {
    "cooling": HVACAction.COOLING,
    "fan only": HVACAction.FAN,
    "heating": HVACAction.HEATING,
    "idle": HVACAction.IDLE,
    "pending cool": HVACAction.COOLING,
    "pending heat": HVACAction.HEATING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HubConnect climate entities."""

    known: set[str] = set()
    registry = get_shadow_registry(hass)
    registry.log_platform_event("climate", "setup")

    @callback
    def add_new_entities() -> None:
        registry = get_shadow_registry(hass)
        try:
            entities = []
            thermostat_device_ids = {
                description.device_id
                for description in registry.entities.values()
                if description.device_class == "thermostat"
                and description.attribute in THERMOSTAT_ATTRIBUTES
            }
            for device_id in sorted(thermostat_device_ids):
                if device_id in known:
                    continue
                description = next(
                    item
                    for item in registry.entities.values()
                    if item.device_id == device_id
                )
                entities.append(HubConnectShadowClimate(description))

            if entities:
                for entity in entities:
                    known.add(entity.unique_id)
                registry.log_platform_event("climate", "add", len(entities))
                async_add_entities(entities)
            else:
                registry.log_platform_event("climate", "add_none", 0)
        except Exception as err:  # noqa: BLE001
            registry.log_platform_event("climate", "error", 0, repr(err))

    add_new_entities()
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SHADOW_DEVICES_UPDATED, add_new_entities)
    )


class HubConnectShadowClimate(ClimateEntity, HubConnectShadowEntity):
    """Climate entity mirrored from a Hubitat thermostat."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    )
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT

    def __init__(self, description: ShadowEntityDescription) -> None:
        """Initialize the thermostat."""

        self._description = description
        self._attr_unique_id = description.device_id
        self._sync_device_info()

    async def async_added_to_hass(self) -> None:
        """Register live thermostat update hooks."""

        live_entities = self.hass.data.setdefault(DOMAIN, {}).setdefault(
            "_shadow_entities", {}
        )
        live_entities[self.unique_id] = self
        self.async_on_remove(lambda: live_entities.pop(self.unique_id, None))
        for attribute in THERMOSTAT_ATTRIBUTES:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    f"{SIGNAL_SHADOW_ENTITY_UPDATED}_{self.unique_id}_{attribute}",
                    self.async_refresh_from_shadow,
                )
            )

    @callback
    def async_refresh_from_shadow(self) -> None:
        """Refresh this entity from the shared shadow registry."""

        registry = get_shadow_registry(self.hass)
        description = next(
            (
                entity
                for entity in registry.entities.values()
                if entity.device_id == self.unique_id
            ),
            None,
        )
        if description is not None:
            self._description = description
            self._sync_device_info()
        self.async_write_ha_state()

    def _value(self, attribute: str):
        """Return one thermostat shadow value."""

        entity = get_shadow_registry(self.hass).entities.get(
            f"{self.unique_id}_{attribute}"
        )
        return entity.value if entity else None

    @property
    def current_temperature(self):
        """Return current temperature."""

        return _number_or_none(self._value("temperature"))

    @property
    def target_temperature(self):
        """Return target temperature."""

        return _number_or_none(self._value("thermostatSetpoint"))

    @property
    def target_temperature_low(self):
        """Return heating setpoint."""

        return _number_or_none(self._value("heatingSetpoint"))

    @property
    def target_temperature_high(self):
        """Return cooling setpoint."""

        return _number_or_none(self._value("coolingSetpoint"))

    @property
    def hvac_mode(self):
        """Return current HVAC mode."""

        return MODE_MAP.get(str(self._value("thermostatMode")).lower(), HVACMode.OFF)

    @property
    def hvac_modes(self):
        """Return supported HVAC modes."""

        value = self._value("supportedThermostatModes")
        if isinstance(value, list):
            modes = value
        else:
            modes = str(value or "off,heat,cool,auto").replace("[", "").replace("]", "").split(",")
        mapped = [
            MODE_MAP[item.strip().lower()]
            for item in modes
            if item.strip().lower() in MODE_MAP
        ]
        return mapped or [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]

    @property
    def hvac_action(self):
        """Return current HVAC action."""

        return ACTION_MAP.get(str(self._value("thermostatOperatingState")).lower())

    @property
    def fan_mode(self):
        """Return current fan mode."""

        value = self._value("thermostatFanMode")
        return str(value) if value is not None else None

    @property
    def fan_modes(self):
        """Return supported fan modes."""

        value = self._value("supportedThermostatFanModes")
        if isinstance(value, list):
            return [str(item) for item in value]
        if value:
            return [
                item.strip()
                for item in str(value).replace("[", "").replace("]", "").split(",")
                if item.strip()
            ]
        return None


def _number_or_none(value):
    """Return a numeric value or None."""

    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
