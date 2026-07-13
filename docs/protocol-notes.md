# HubConnect Protocol Notes

These notes describe the HTTP surface the Home Assistant integration needs to emulate.

## Initial Endpoint Set

The first implementation should support these HubConnect remote-client routes:

```text
GET  /api/hubconnect/ping
GET  /api/hubconnect/system/versions/get
GET  /api/hubconnect/modes/get
GET  /api/hubconnect/devices/get
GET  /api/hubconnect/device/{device_id}/sync/{device_class}
GET  /api/hubconnect/event/{device_id}/{device_command}/{command_params}
GET  /api/hubconnect/modes/set/{name}
POST /api/hubconnect/devices/save
```

The route prefix is Home Assistant-specific. Hubitat will need a client URI that points at `http://HOME_ASSISTANT:8123/api/hubconnect`.

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
