# HubConnect Protocol Notes

These notes describe the HTTP surface the Home Assistant integration needs to emulate.

## Initial Endpoint Set

The current prototype supports these HubConnect remote-client routes:

```text
GET  /api/hubconnect/ping
GET  /api/hubconnect/system/versions/get
GET  /api/hubconnect/system/tsreport/get
POST /api/hubconnect/system/drivers/save
GET  /api/hubconnect/modes/get
GET  /api/hubconnect/devices/get
GET  /api/hubconnect/device/{device_id}/sync/{device_class}
GET  /api/hubconnect/device/{device_id}/event/{event_json}
GET  /api/hubconnect/event/{device_id}/{device_command}/{command_params}
GET  /api/hubconnect/modes/set/{name}
POST /api/hubconnect/devices/save
```

The route prefix is Home Assistant-specific. Hubitat will need a client URI that points at `http://HOME_ASSISTANT:8123/api/hubconnect`.

`devices/save` creates persistent Home Assistant shadow entities for Hubitat-selected devices. Device resends are idempotent enough for current testing and preserve existing shadow objects so live event updates do not lag by one event.

## Device Selection Model

The integration should support both import and export flows under one Home Assistant integration, but both flows are selection-driven:

- Hubitat to Home Assistant imports only devices selected in the Hubitat HubConnect Server Instance. HubConnect remote clients do not receive an implicit "all devices" selection.
- Home Assistant to Hubitat exports only entities selected in the HubConnect integration options. `/devices/get` must not auto-export every mappable Home Assistant entity. A future "all" choice may exist only as an explicit selector option.

## Reference Implementations

Use both protocol-native and Home Assistant-native references when expanding support:

- Dan Tapps' `danTapps/homebridge-hubitat-hubconnect` for a Node.js HubConnect remote endpoint and HubConnect-to-platform device mapping behavior.
- Jason 0x43's `jason0x43/hacs-hubitat` for Home Assistant entity/platform conventions.

## First Device Classes To Map

Start with low-risk, common entities:

```text
switch          -> switch
light           -> switch, dimmer, rgbbulb, rgbwbulb
binary_sensor   -> contact, motion, moisture
sensor          -> v_temperature, v_humidity, power, energy
lock            -> lock
cover           -> windowshade
climate         -> thermostat
```

## Event Shape

HubConnect device events are URL-encoded JSON objects:

```json
{
  "name": "switch",
  "value": "on",
  "unit": "",
  "displayName": "Kitchen Light",
  "data": ""
}
```

The event handler updates the persistent shadow state and writes the corresponding Home Assistant entity state directly through the entity registry. That direct state write is a prototype decision to revisit before hardening the integration.

## Debug Endpoint

`GET /api/hubconnect/system/shadows/get` returns the shadow registry, recent requests, entity registry entries, live entity objects, and current Home Assistant states for HubConnect entities.

For removal tests, compare:

- `entities`: active HubConnect shadow entities after the latest selected-device payload.
- `orphaned_entity_registry`: Home Assistant entity-registry entries whose HubConnect shadow no longer exists.
- `orphaned_live_entities`: loaded HubConnect entity objects whose HubConnect shadow no longer exists.
