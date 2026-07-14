# HubConnect Remote Client for HA

HubConnect Remote Client for HA is a Home Assistant custom integration that lets
Home Assistant participate as a HubConnect remote client for a Hubitat
HubConnect Server Instance.

This integration is currently alpha-quality. The core selected-device flows are
working, but device coverage is still incomplete.

## What Works Today

- Pair Home Assistant with a Hubitat HubConnect Server Instance.
- Import Hubitat-selected devices into Home Assistant.
- Update imported Home Assistant entities from live Hubitat events.
- Remove imported Home Assistant entities when they are no longer shared by
  Hubitat.
- Export selected Home Assistant entities to Hubitat.
- Control exported Home Assistant switches from Hubitat.
- Remove exported Home Assistant devices from Hubitat when they are no longer
  selected in Home Assistant.

Both directions are selection-based. This integration does not automatically
share all Hubitat devices or all Home Assistant entities.

## Install With HACS

Until this repository is listed in the default HACS store, add it as a custom
repository:

1. In Home Assistant, open HACS.
2. Open the three-dot menu.
3. Choose **Custom repositories**.
4. Add this repository URL:

   ```text
   https://github.com/csteele-PD/HubConnect4HA
   ```

5. Choose **Integration** as the category.
6. Install **HubConnect Remote Client for HA**.
7. Restart Home Assistant.

## Manual Install

Copy this directory:

```text
custom_components/hubconnect
```

to your Home Assistant config directory:

```text
config/custom_components/hubconnect
```

Restart Home Assistant.

## Add The Integration

In Home Assistant:

```text
Settings -> Devices & services -> Add integration -> HubConnect
```

Create the integration and keep the generated bearer token. Hubitat uses this
token when calling the Home Assistant HubConnect endpoint.

## Pair With Hubitat

In Home Assistant:

1. Open the HubConnect integration.
2. Open **Configure**.
3. Paste the connection key from your Hubitat HubConnect Server Instance.
4. Enter a Home Assistant base URL that Hubitat can reach on your LAN, for
   example:

   ```text
   http://homeassistant.local:8123
   ```

5. Select any Home Assistant entities you want to expose to Hubitat.
6. Save the options.

In Hubitat, verify that the Home Assistant remote client is online.

## Share Hubitat Devices To Home Assistant

Use the normal HubConnect Server Instance selectors in Hubitat. Devices selected
there are sent to Home Assistant and become HubConnect shadow devices/entities.

When a selected Hubitat device changes state, Home Assistant should update
immediately.

If you later deselect a Hubitat device and choose to remove unused devices,
Home Assistant removes the corresponding shadow entities.

## Share Home Assistant Entities To Hubitat

Open the HubConnect integration options in Home Assistant and select the HA
entities to expose to Hubitat.

Currently supported HA export types include:

| Home Assistant entity | HubConnect class |
| --- | --- |
| `switch` | `switch` |
| non-dimming `light` | `switch` |
| dimming `light` | `dimmer` |
| contact/opening/window/door `binary_sensor` | `contact` |
| motion/occupancy `binary_sensor` | `motion` |
| moisture `binary_sensor` | `moisture` |
| presence `binary_sensor` | `presence` |
| smoke/gas `binary_sensor` | `smoke` |
| temperature `sensor` | `v_temperature` |
| humidity `sensor` | `v_humidity` |
| illuminance `sensor` | `v_illuminance` |
| power `sensor` | `power` |
| energy `sensor` | `energy` |

Unsupported selected entities are skipped and reported in the debug endpoint.

## Debugging

Check what Home Assistant is currently exposing to Hubitat:

```bash
curl -H "Authorization: Bearer TOKEN" \
  http://HOME_ASSISTANT:8123/api/hubconnect/devices/get
```

Inspect imported Hubitat shadows, exported HA payloads, required Hubitat
drivers, unsupported selected entities, and recent HA-to-Hubitat push results:

```bash
curl -H "Authorization: Bearer TOKEN" \
  http://HOME_ASSISTANT:8123/api/hubconnect/system/shadows/get
```

Useful fields in `shadows/get`:

- `entities`: imported Hubitat shadow entities.
- `requests`: recent HubConnect calls received by Home Assistant.
- `ha_export.current_payload`: HA entities that will be sent to Hubitat.
- `ha_export.required_drivers`: Hubitat drivers required by selected HA exports.
- `ha_export.unsupported_entities`: selected HA entities that cannot be exported.
- `ha_export.pushes`: recent HA-to-Hubitat `/devices/save` POSTs and responses.

## Known Alpha Limitations

- Device coverage is incomplete.
- Standalone HA battery sensors are not exported yet.
- Button `released` may not arrive through classic HubConnect button selection.
- Speech synthesis devices are command-oriented and are not yet useful as HA
  shadow entities.
- Thermostat support exists but is still rough.
- Debug output is intentionally verbose.

More detail is available in [docs/alpha-test-guide.md](docs/alpha-test-guide.md).

## HubConnect Credits

HubConnect for Hubitat was created by Steve White / Retail Media Concepts LLC.
This integration is an independent Python implementation of a compatible Home
Assistant remote endpoint.

See [NOTICE.md](NOTICE.md) for attribution notes.

Original HubConnect documentation:

```text
https://hubconnect.hubitatcommunity.com/
```
