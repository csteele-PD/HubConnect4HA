# HubConnect for Home Assistant

Experimental Home Assistant custom integration that aims to act as a HubConnect remote endpoint for a Hubitat HubConnect Server Instance.

This repository is in early protocol-discovery and test-build shape. The current integration can pair Home Assistant as a HubConnect remote client, accept Hubitat-selected devices, create persistent Home Assistant shadow entities, and update those entities from live Hubitat events.

## First Local Test

Copy `custom_components/hubconnect` into your Home Assistant config directory:

```text
config/custom_components/hubconnect
```

Restart Home Assistant, then go to:

```text
Settings -> Devices & services -> Add integration -> HubConnect
```

Create the integration and keep the generated bearer token. After setup, this endpoint should answer:

```text
GET http://HOME_ASSISTANT:8123/api/hubconnect/ping
Authorization: Bearer YOUR_TOKEN
```

Expected response:

```json
{"status":"received"}
```

Hubitat pairing and device selection currently exercise these key endpoints:

```text
GET  /api/hubconnect/ping
GET  /api/hubconnect/system/versions/get
GET  /api/hubconnect/system/tsreport/get
POST /api/hubconnect/system/drivers/save
GET  /api/hubconnect/devices/get
POST /api/hubconnect/devices/save
GET  /api/hubconnect/device/{device_id}/event/{event_json}
```

The first inventory endpoint is also available:

```text
GET http://HOME_ASSISTANT:8123/api/hubconnect/devices/get
Authorization: Bearer YOUR_TOKEN
```

It exposes selected supported HA entities: switches, lights, temperature sensors, humidity sensors, illuminance sensors, power sensors, energy sensors, voltage sensors, and common binary sensors such as motion, contact, water, smoke, and presence. A future "all" mode should be an explicit selector choice, not implicit auto-export behavior.

## Pairing With Hubitat

Open the HubConnect integration options in Home Assistant and paste the connection key from the Hubitat HubConnect Server Instance.

Use a Home Assistant base URL that Hubitat can reach on the LAN, for example:

```text
http://192.168.7.70:8123
```

## Device Selection

This integration should eventually support both directions under one integration:

- Hubitat to Home Assistant: import only devices selected in the Hubitat HubConnect Server Instance. The HubConnect remote flow has no implicit "all" behavior.
- Home Assistant to Hubitat: export only entities selected in Home Assistant. If "all" is offered later, it should be an explicit selector option.

## HACS Test

Once this repository is pushed to GitHub, add it to HACS as a custom repository:

```text
HACS -> three-dot menu -> Custom repositories
```

Use the repository URL and choose `Integration` as the category.

## External References

Useful references for future mapping work:

- `HubitatCommunity/HubConnect` for the original HubConnect Hubitat project by Steve White / Retail Media Concepts LLC.
- `danTapps/homebridge-hubitat-hubconnect` for HubConnect remote endpoint behavior and device mapping ideas.
- `jason0x43/hacs-hubitat` for Home Assistant-native Hubitat entity conventions.

See `NOTICE.md` for HubConnect attribution notes.
