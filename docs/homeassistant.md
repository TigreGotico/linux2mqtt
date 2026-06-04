# Home Assistant integration

PowerGuess publishes to MQTT with Home Assistant's MQTT discovery, so the
entities appear on their own when both PowerGuess and the
[MQTT integration](https://www.home-assistant.io/integrations/mqtt/) point at the
same broker. No YAML required.

## Entities

A single device, **PowerGuess** (`powerguess_01` by default), exposing:

| Entity | Unit | Device class |
| --- | --- | --- |
| `sensor.powerguess_power` | W | power |
| `sensor.powerguess_current` | A | current |
| `sensor.powerguess_voltage` | V | voltage |
| `sensor.powerguess_energy` | kWh | energy (total_increasing) |
| `sensor.powerguess_source` | — | provenance: `ina219`/`powerstat`/`battery`/`estimate` |
| `sensor.powerguess_error_margin` | W | ± band on an estimate |
| `sensor.powerguess_power_floor` | W | idle floor (envelope lower bound) |
| `sensor.powerguess_power_ceiling` | W | peak/PSU ceiling (envelope upper bound) |
| `sensor.powerguess_cost` | currency | energy × tariff (only if `ENERGY_TARIFF` set) |
| `sensor.powerguess_model` | — | — |

It also breaks out per-component telemetry. **CPU** (always):

| Entity | Unit | Notes |
| --- | --- | --- |
| `sensor.powerguess_cpu_utilization` | % | |
| `sensor.powerguess_cpu_frequency` | MHz | |
| `sensor.powerguess_cpu_temperature` | °C | |
| `sensor.powerguess_cpu_power` | W | CPU **package** power via RAPL — only when `/sys/class/powercap/.../energy_uj` is readable (often root-only) |

**GPU** (NVIDIA):

| Entity | Unit | Notes |
| --- | --- | --- |
| `sensor.powerguess_gpu_utilization` | % | |
| `sensor.powerguess_gpu_temperature` | °C | |
| `sensor.powerguess_gpu_memory` | % | VRAM used |
| `sensor.powerguess_gpu_power` | W | only when `nvidia-smi` reports a credible value (validated against the power limit; some laptop GPUs report garbage and are skipped) |

On a Raspberry Pi it adds **binary sensors** (`device_class: problem`):
`binary_sensor.powerguess_undervoltage`, `binary_sensor.powerguess_throttled`,
and `binary_sensor.powerguess_undervoltage_occurred` — see
[raspberry-pi.md](raspberry-pi.md).

The **source** and **error margin** sensors tell you whether the power figure is
measured or estimated; **floor**/**ceiling** show the [envelope](theory.md) the
estimate sits in. All entities are tied to an MQTT **availability** topic with a
Last Will, so Home Assistant marks them *unavailable* if the service stops rather
than showing a stale value. On devices with a battery it also adds `battery_level`
(%), `battery_power` (W), `battery_status`, and the `charging` binary sensor.

Run more than one instance by giving each a unique `DEVICE_ID` / `DEVICE_NAME`
(and a distinct `MQTT_TOPIC_PREFIX`).

## Dashboard card

```yaml
type: entities
title: PowerGuess
entities:
  - entity: sensor.powerguess_power
    name: Power draw
  - entity: sensor.powerguess_current
    name: Current
  - entity: sensor.powerguess_voltage
    name: Voltage
  - entity: sensor.powerguess_model
    name: Device
```

A gauge for the live draw:

```yaml
type: gauge
entity: sensor.powerguess_power
name: Power draw
unit: W
min: 0
max: 15
severity:
  green: 0
  yellow: 8
  red: 12
```

## Energy dashboard

PowerGuess integrates power over time itself and publishes
`sensor.powerguess_energy` (kWh, `state_class: total_increasing`) — add it
directly under **Settings → Energy → Individual devices**. No Riemann-sum helper
needed. Set `ENERGY_FILE` to persist the counter across restarts; set
`ENERGY_TARIFF` to also get a `cost` sensor.

## MQTT topics

| Topic | Payload |
| --- | --- |
| `powerguess/state` | `{"power", "voltage", "current", "source", "measured", "error_margin", "energy", "timestamp"}` |
| `powerguess/battery` | `{"level", "status", "charging", "power", "voltage"}` |
| `powerguess/model` | `{"model"}` |
| `homeassistant/sensor/<id>/<key>/config` | discovery (retained) |

Topic prefix and discovery prefix are configurable
([configuration](configuration.md)).
