# Home Assistant integration

PowerGuess publishes to MQTT using Home Assistant's MQTT discovery, so the
entities appear on their own when both PowerGuess and the
[MQTT integration](https://www.home-assistant.io/integrations/mqtt/) point at
the same broker. No YAML is required.

## Entities

A single device, PowerGuess (`powerguess_01` by default), exposes:

The power readings are power, current, and voltage. Everything else is a
diagnostic entity, in HA's Diagnostic section. Energy and cost are not
exposed.

| Entity | Unit | Category |
| --- | --- | --- |
| `sensor.<dev>_power` | W | measurement |
| `sensor.<dev>_current` | A | measurement |
| `sensor.<dev>_voltage` | V | measurement |
| `sensor.<dev>_source` | — | diagnostic: provenance: `ina219`/`pmic`/`powerstat`/`battery`/`estimate` |
| `sensor.<dev>_error_margin` | W | diagnostic: ± band on an estimate |
| `sensor.<dev>_power_floor` | W | diagnostic: idle floor (envelope lower bound) |
| `sensor.<dev>_power_ceiling` | W | diagnostic: peak/PSU ceiling (envelope upper bound) |
| `sensor.<dev>_model` | — | diagnostic |

It also breaks out per-component telemetry. CPU (always present):

| Entity | Unit | Notes |
| --- | --- | --- |
| `sensor.powerguess_cpu_utilization` | % | |
| `sensor.powerguess_cpu_frequency` | MHz | |
| `sensor.powerguess_cpu_temperature` | °C | |
| `sensor.powerguess_cpu_power` | W | CPU package power via RAPL, only when `/sys/class/powercap/.../energy_uj` is readable (often root-only) |

GPU (NVIDIA):

| Entity | Unit | Notes |
| --- | --- | --- |
| `sensor.powerguess_gpu_utilization` | % | |
| `sensor.powerguess_gpu_temperature` | °C | |
| `sensor.powerguess_gpu_memory` | % | VRAM used |
| `sensor.powerguess_gpu_power` | W | only when `nvidia-smi` reports a credible value (validated against the power limit, some laptop GPUs report garbage and are skipped) |

On a Raspberry Pi it adds binary sensors (`device_class: problem`):
`binary_sensor.powerguess_undervoltage`, `binary_sensor.powerguess_throttled`,
and `binary_sensor.powerguess_undervoltage_occurred`. See
[raspberry-pi.md](raspberry-pi.md).

The source and error-margin sensors show whether the power figure is measured
or estimated. Floor and ceiling show the envelope the estimate sits in (see
[powerguess](https://github.com/TigreGotico/powerguess) for the envelope
theory). All entities carry an MQTT availability topic with a Last Will, so
Home Assistant marks them unavailable if the service stops, instead of
showing a stale value. On devices with a battery it also adds
`battery_level` (%), `battery_power` (W), `battery_status`, and the
`charging` binary sensor.

Run more than one instance by giving each a unique `DEVICE_ID`/`DEVICE_NAME`
and a distinct `MQTT_TOPIC_PREFIX`.

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
`sensor.powerguess_energy` (kWh, `state_class: total_increasing`). Add it
directly under Settings → Energy → Individual devices. No Riemann-sum helper
is needed. Set `ENERGY_FILE` to persist the counter across restarts, and set
`ENERGY_TARIFF` to also get a `cost` sensor.

## MQTT topics

| Topic | Payload |
| --- | --- |
| `powerguess/state` | `{"power", "voltage", "current", "source", "measured", "error_margin", "energy", "timestamp"}` |
| `powerguess/battery` | `{"level", "status", "charging", "power", "voltage"}` |
| `powerguess/model` | `{"model"}` |
| `homeassistant/sensor/<id>/<key>/config` | discovery (retained) |

The topic prefix and discovery prefix are configurable. See
[configuration](configuration.md).

---
[Home](index.md) · [Components →](components.md)
