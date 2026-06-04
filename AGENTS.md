# linux2mqtt — agent onboarding

Homelab MQTT bridge: publish a Linux/SBC box's power + system telemetry to Home
Assistant via MQTT discovery. **Power comes from the `powerguess` library**
(a dependency); this project owns the MQTT layer and all non-power telemetry.

**Org:** TigreGotico / **Branch:** dev (work) / master (stable) / **depends on:** powerguess

## Layout

| Path | Purpose |
|------|---------|
| `linux2mqtt/__main__.py` | the bridge: build a `powerguess.PowerStatMonitor` + telemetry readers, publish each cycle |
| `linux2mqtt/config.py` | env-var config (MQTT, HA, components, calibration passthrough) |
| `linux2mqtt/mqtt_client.py` | paho client + HA auto-discovery (power/energy/cost/source + CPU/GPU/Pi) + LWT availability |
| `linux2mqtt/_mqtt.py` | paho 1.x/2.x client factory |
| `linux2mqtt/cpu.py` | CPU telemetry: util/freq/temp + package power via RAPL |
| `linux2mqtt/rapl.py` | x86 RAPL powercap reader (CPU package watts) |
| `linux2mqtt/gpu.py` | NVIDIA GPU telemetry via nvidia-smi (validated power, util, temp, mem) |
| `linux2mqtt/rpi.py` | Raspberry Pi vcgencmd: throttling / overheating / overclocking / undervoltage |
| `linux2mqtt/wizard.py` | `linux2mqtt-calibrate`: smart-plug + battery calibration (writes a powerguess Calibration) |
| `docs/` | Home Assistant, components, raspberry-pi, configuration |
| `test/` | offline pytest suite (MQTT clients, SMBus/RAPL/nvidia-smi/vcgencmd mocked) |

## Boundary (vs powerguess)

Anything that returns **watts for the whole device** (estimate, INA219, PMIC,
battery, powerstat, calibration, dataset/model) lives in **powerguess** and is
imported. This project adds **non-watt telemetry** (CPU/GPU/Pi temperature,
utilization, frequency, throttling, overclock), the MQTT/HA discovery layer,
energy/cost accounting, and the guided calibration wizard. RAPL CPU-package power
and GPU power ride here with their telemetry; PMIC (whole-board) is powerguess's.

## Conventions

- Import power from `powerguess`; never reimplement estimation/calibration here.
- HA discovery: retained `homeassistant/<component>/<device_id>/<key>/config`,
  with an availability topic + Last Will.
- Component power is validated/omitted when the sensor is unreliable (nvidia-smi
  garbage, root-only RAPL) — never publish a fake number.
- Versions bump from conventional-commit prefixes — never edit `linux2mqtt/version.py`.

## Run

```bash
pip install -e ../powerguess -e .[test]
pytest -q
MQTT_HOST=192.168.1.10 MQTT_USER=… MQTT_PASSWORD=… python -m linux2mqtt
```
