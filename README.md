# HubConnect for Home Assistant

Experimental Home Assistant custom integration that aims to act as a HubConnect remote endpoint for a Hubitat HubConnect Server Instance.

This repository is in early protocol-discovery and test-build shape. The current integration only proves that Home Assistant can load the custom component and answer a few HubConnect-style HTTP endpoints.

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

The first inventory endpoint is also available:

```text
GET http://HOME_ASSISTANT:8123/api/hubconnect/devices/get
Authorization: Bearer YOUR_TOKEN
```

It auto-exposes a small set of currently supported HA entities: switches, lights, temperature sensors, humidity sensors, illuminance sensors, power sensors, energy sensors, voltage sensors, and common binary sensors such as motion, contact, water, smoke, and presence.

## Pairing With Hubitat

Open the HubConnect integration options in Home Assistant and paste the connection key from the Hubitat HubConnect Server Instance.

Use a Home Assistant base URL that Hubitat can reach on the LAN, for example:

```text
http://192.168.7.70:8123
```

## HACS Test

Once this repository is pushed to GitHub, add it to HACS as a custom repository:

```text
HACS -> three-dot menu -> Custom repositories
```

Use the repository URL and choose `Integration` as the category.

## Reference Material

`ReferenceMaterial/` contains source used to understand HubConnect's existing protocol. It is not part of the Home Assistant integration package.
