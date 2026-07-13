"""Constants for the HubConnect integration."""

from homeassistant.const import Platform

DOMAIN = "hubconnect"

CONF_REMOTE_NAME = "remote_name"
CONF_TOKEN = "token"
CONF_HA_BASE_URL = "ha_base_url"
CONF_EXPORTED_ENTITY_IDS = "exported_entity_ids"
CONF_HUBITAT_CONNECTION_KEY = "hubitat_connection_key"
CONF_HUBITAT_URI = "hubitat_uri"
CONF_HUBITAT_TOKEN = "hubitat_token"
CONF_HUBITAT_TYPE = "hubitat_type"
CONF_HUBITAT_CONNECTION_TYPE = "hubitat_connection_type"

DEFAULT_REMOTE_NAME = "Home Assistant"

HTTP_BASE = "/api/hubconnect"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.SENSOR,
    Platform.SWITCH,
]
