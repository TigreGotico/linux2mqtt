# Configuration

All settings are environment variables, read once at startup.

## Monitor

| Variable | Default | Meaning |
| --- | --- | --- |
| `MEASURE_INTERVAL` | `5` | seconds between measurements |
| `PUBLISH_INTERVAL` | `5` | minimum seconds between MQTT publishes |
| `PUBLISH_DELTA` | `0.5` | publish early when power moves by this many W (0 disables) |
| `SMOOTH` | `false` | rolling-average the powerstat readings |
| `PREFER_BATTERY` | `false` | trust battery rails over the estimate when discharging |
| `USE_POWERSTAT` | `true` | use powerstat/RAPL when installed and privileged |

## Calibration & sources

| Variable | Default | Meaning |
| --- | --- | --- |
| `CALIBRATION_FILE` | _(none)_ | JSON calibration to load, and where auto-calibration is saved |
| `CALIBRATION_IDLE_W` / `CALIBRATION_LOAD_W` | _(none)_ | manual idle/peak watts (the bounds) |
| `CALIBRATION_PSU_W` | _(none)_ | with `CALIBRATION_IDLE_W` but no `LOAD_W`, use the PSU rating as a loose upper bound (see [theory](theory.md)) |
| `CALIBRATION_VOLTAGE` | `5.0` | supply voltage for manual calibration |
| `AUTO_CALIBRATE` | `true` | learn idle/peak from measured readings |
| `USE_INA219` | `false` | read an INA219 I²C power monitor (needs `[ina219]`) |
| `INA219_BUS` / `INA219_ADDRESS` / `INA219_SHUNT_OHMS` | `1` / `0x40` / `0.1` | INA219 wiring |
| `MODEL_FILE` | _(none)_ | trained predictor JSON (see dataset.md) |
| `DATASET_FILE` | _(none)_ | append measured `features→watts` rows here |

## MQTT

| Variable | Default |
| --- | --- |
| `MQTT_HOST` | `localhost` |
| `MQTT_PORT` | `1883` |
| `MQTT_USER` / `MQTT_PASSWORD` | _(none)_ |
| `MQTT_TOPIC_PREFIX` | `powerguess` |
| `MQTT_CLIENT_ID` | `powerguess-client` |
| `MQTT_QOS` | `0` |
| `MQTT_RETAIN` | `true` |
| `MQTT_KEEPALIVE` | `60` |
| `MQTT_RETRY_COUNT` | `5` |
| `MQTT_RETRY_MAX_BACKOFF` | `30` |
| `MQTT_CONNECT_TIMEOUT` | `2.0` |

## Home Assistant

| Variable | Default |
| --- | --- |
| `HA_ENABLED` | `true` |
| `HA_DISCOVERY_PREFIX` | `homeassistant` |
| `DEVICE_NAME` | `PowerGuess` |
| `DEVICE_ID` | `powerguess_01` |

## Energy & cost

| Variable | Default | Meaning |
| --- | --- | --- |
| `ENERGY_FILE` | _(none)_ | persist the cumulative kWh counter here so it survives restarts |
| `ENERGY_TARIFF` | `0` | price per kWh; when > 0 a cost sensor is published |
| `CURRENCY` | `EUR` | unit for the cost sensor |

## Components

The CPU and GPU are tracked as their own entities (not as the total).

| Variable | Default | Meaning |
| --- | --- | --- |
| `USE_CPU` | `true` | publish CPU utilization/frequency/temperature; plus CPU **package** power via RAPL when `/sys/class/powercap/.../energy_uj` is readable (often root-only) |
| `USE_GPU` | `true` | publish GPU utilization/temperature/memory (and power, if credible) via `nvidia-smi` |
| `GPU_INDEX` | `0` | which GPU to read |
| `USE_RPI` | `true` | Raspberry Pi via `vcgencmd`: PMIC board power (Pi 5) as a measured total source, plus undervoltage/throttling binary sensors — see [raspberry-pi.md](raspberry-pi.md) |

Note: RAPL measures the CPU package only, so it is a component — not the
whole-device total. The total comes from INA219 / battery / the estimate.

## Logging

| Variable | Default |
| --- | --- |
| `LOG_LEVEL` | `INFO` |
