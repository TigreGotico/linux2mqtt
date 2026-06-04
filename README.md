# linux2mqtt

Publish a Linux box's **power and system telemetry** to MQTT with Home Assistant
auto-discovery — built for the homelab. Power comes from the
[powerguess](https://github.com/JarbasAl/powerguess) library (measured or
estimated, with provenance); linux2mqtt adds the system sensors and the bridge.

## Entities

Under one Home Assistant device:

- **Power** — total device watts (measured: INA219 / Pi 5 PMIC / battery; or
  estimated with an error band), plus **energy** (kWh), **cost**, the source and
  error-margin, and the idle/peak envelope.
- **CPU** — utilization, frequency, temperature, and package power (RAPL).
- **GPU** (NVIDIA) — utilization, temperature, VRAM, and validated power.
- **Raspberry Pi** — throttling, overheating, overclocking, and undervoltage
  binary sensors.

## Run

```bash
pip install linux2mqtt
MQTT_HOST=192.168.1.10 MQTT_USER=… MQTT_PASSWORD=… python -m linux2mqtt
```

Or in Docker (see [`docker-compose.yml`](docker-compose.yml); the Raspberry Pi
`vcgencmd` recipe is included):

```bash
docker run -d --name linux2mqtt --network host --restart unless-stopped \
  -e MQTT_HOST=127.0.0.1 -e MQTT_USER=… -e MQTT_PASSWORD=… \
  ghcr.io/jarbasal/linux2mqtt:latest
```

## Calibrate the power estimate

```bash
linux2mqtt-calibrate            # smart plug over MQTT
linux2mqtt-calibrate --battery  # laptop battery, fully automatic (CPU+GPU load)
```

## Docs

- [Home Assistant](docs/homeassistant.md) — entities, cards, energy dashboard.
- [Components](docs/components.md) — the CPU/GPU breakdown.
- [Raspberry Pi](docs/raspberry-pi.md) — PMIC power, throttle/overheat/overclock,
  `vcgencmd` in a container.
- [Configuration](docs/configuration.md) — all environment variables.

Power estimation, calibration, and the dataset/model live in
[powerguess](https://github.com/JarbasAl/powerguess).

## License

Apache-2.0
