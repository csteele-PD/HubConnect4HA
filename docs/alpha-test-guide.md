# Alpha Test Guide

This project is an early Home Assistant custom integration that behaves like a
HubConnect remote endpoint for Hubitat. The alpha goal is to prove selected,
bidirectional device sharing before broadening device coverage.

## Current Working Scope

Hubitat to Home Assistant:

- Hubitat HubConnect Server can pair with Home Assistant as a remote client.
- Hubitat-selected devices are sent to Home Assistant with `/devices/save`.
- Home Assistant creates persistent shadow devices and entities.
- Hubitat live events update Home Assistant entities immediately.
- Hubitat selection changes remove unshared Home Assistant shadow entities.

Home Assistant to Hubitat:

- Home Assistant exports only entities selected in HubConnect integration options.
- `/devices/get` returns the currently selected supported HA entities.
- Saving options pushes selected HA entities to Hubitat with `/devices/save`.
- Saving options also sends cleanup so deselected HA entities are removed from Hubitat.
- Hubitat commands can control exported HA switches.

## Supported HA Export Classes

Current HA-to-Hubitat export mapping:

| Home Assistant entity | HubConnect class | Required Hubitat driver |
| --- | --- | --- |
| `switch` | `switch` | `HubConnect Switch` |
| non-dimming `light` | `switch` | `HubConnect Switch` |
| dimming `light` | `dimmer` | `HubConnect Dimmer` |
| `binary_sensor` contact/opening/window/door | `contact` | `HubConnect Contact Sensor` |
| `binary_sensor` motion/occupancy | `motion` | `HubConnect Motion Sensor` |
| `binary_sensor` moisture | `moisture` | `HubConnect Moisture Sensor` |
| `binary_sensor` presence | `presence` | `HubConnect Presence Sensor` |
| `binary_sensor` smoke/gas | `smoke` | `HubConnect SmokeCO` |
| `sensor` temperature | `v_temperature` | `HubConnect Virtual Temperature Sensor` |
| `sensor` humidity | `v_humidity` | `HubConnect Virtual Virtual Humidity Sensor` |
| `sensor` illuminance | `v_illuminance` | `HubConnect Virtual Illuminance Sensor` |
| `sensor` power | `power` | `HubConnect Power Meter` |
| `sensor` energy | `energy` | `HubConnect Energy Meter` |

Unsupported selected entities are intentionally excluded from export and reported
in the debug endpoint.

## Selection Model

Both directions are selected-only:

- Hubitat to HA: select devices in the Hubitat HubConnect Server Instance.
- HA to Hubitat: select HA entities in the HubConnect integration options.

There is no implicit export-all behavior. If an all-devices mode is added later,
it should be an explicit selector option.

## Useful Debug Commands

Check what Home Assistant will expose to Hubitat:

```bash
curl -H "Authorization: Bearer TOKEN" \
  http://HOME_ASSISTANT:8123/api/hubconnect/devices/get
```

Inspect imported Hubitat shadows, HA export payloads, driver requirements, push
responses, and cleanup state:

```bash
curl -H "Authorization: Bearer TOKEN" \
  http://HOME_ASSISTANT:8123/api/hubconnect/system/shadows/get
```

Key `shadows/get` fields:

- `entities`: active Hubitat-to-HA shadow registry.
- `requests`: recent HubConnect calls received by HA.
- `platform_events`: HA platform setup/add activity.
- `entity_registry`: HA entity registry entries owned by this integration.
- `orphaned_entity_registry`: registry entries no longer backed by shadows.
- `live_entities`: loaded HubConnect entity objects.
- `orphaned_live_entities`: loaded objects no longer backed by shadows.
- `shadow_states`: current HA states for imported Hubitat shadow entities.
- `ha_export.selected_entity_ids`: selected HA entities.
- `ha_export.current_payload`: protocol payload HA will send to Hubitat.
- `ha_export.required_drivers`: Hubitat drivers required by selected HA exports.
- `ha_export.unsupported_entities`: selected HA entities excluded from export.
- `ha_export.pushes`: recent HA-to-Hubitat `/devices/save` POSTs and responses.

## Known Alpha Limitations

- Device coverage is intentionally incomplete.
- Standalone HA battery sensors are not exported yet because HubConnect has no
  native standalone battery deviceclass.
- Button `released` may not arrive through classic HubConnect button selection.
- Speech synthesis devices are command-oriented and do not create useful HA
  shadow entities yet.
- Thermostat support is useful for testing but still rough.
- Direct HA state writes are still prototype behavior and should be revisited
  before hardening.
- Debug output is intentionally verbose and should be trimmed or moved to
  diagnostics before release.
