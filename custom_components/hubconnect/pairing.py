"""HubConnect pairing helpers."""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession


class PairingError(ValueError):
    """Raised when HubConnect pairing fails."""


def decode_connection_key(connection_key: str) -> dict[str, Any]:
    """Decode a HubConnect server connection key."""

    try:
        decoded = base64.b64decode(connection_key).decode()
        data = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as err:
        raise PairingError("invalid_connection_key") from err

    if not data.get("uri") or not data.get("token"):
        raise PairingError("invalid_connection_key")

    if data.get("type") == "smartthings":
        raise PairingError("wrong_platform")

    return data


async def async_pair_with_hubitat(
    hass: HomeAssistant,
    hubitat_data: dict[str, Any],
    ha_base_url: str,
    remote_name: str,
    token: str,
    entry_id: str,
) -> None:
    """Tell the Hubitat server instance how to call this HA endpoint."""

    remote_key = base64.b64encode(
        json.dumps(
            {
                "uri": f"{ha_base_url.rstrip('/')}/api/hubconnect",
                "name": remote_name,
                "type": hubitat_data.get("type", "homebridge"),
                "token": token,
                "mac": "home-assistant",
                "customDriverDBVersion": 0,
            },
            separators=(",", ":"),
        ).encode()
    ).decode()

    url = _hubitat_url(
        hubitat_data["uri"],
        f"/connect/{remote_key}",
        hubitat_data["token"],
    )
    session = async_get_clientsession(hass)

    try:
        response = await session.get(
            url,
            headers={"Authorization": f"Bearer {hubitat_data['token']}"},
            timeout=15,
        )
        data = await response.json(content_type=None)
    except (ClientError, TimeoutError, ValueError) as err:
        raise PairingError("cannot_connect") from err

    if response.status != 200 or str(data.get("status")) != "success":
        raise PairingError(data.get("message") or "pairing_rejected")


def _hubitat_url(base_uri: str, path: str, token: str) -> str:
    """Build a Hubitat app URL with both path and query token auth."""

    url = f"{base_uri.rstrip('/')}{path}"
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'access_token': token})}"
