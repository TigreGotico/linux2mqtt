# linux2mqtt

linux2mqtt publishes a Linux box's power and system telemetry to MQTT, with
Home Assistant auto-discovery, and is built for the homelab. Power readings
come from the [powerguess](https://github.com/TigreGotico/powerguess) library
(measured or estimated, with provenance). linux2mqtt adds the system sensors
and the MQTT/Home Assistant bridge.

## Entities

Under one Home Assistant device:

- **Power**: total device watts (measured from INA219, Pi 5 PMIC, or
  battery, or estimated), plus current and voltage. Source, error margin, and
  the idle/peak envelope are diagnostic entities. Energy and cost are not
  exposed.
- **CPU**: utilization, frequency, temperature, and package power (RAPL).
- **GPU** (NVIDIA): utilization, temperature, VRAM, and validated power.
- **Raspberry Pi**: throttling, overheating, overclocking, and undervoltage
  binary sensors.
- **System**: memory/swap, disk usage and free space (per mount), uptime,
  load average, network and disk-IO throughput, fan speed, CPU cores, OS
  info, and a configurable process/service watch (`WATCH_PROCESSES`). See
  [docs/system.md](docs/system.md).
- **Audio & media**: PipeWire/PulseAudio/ALSA status, volume/mic control
  (number/switch), and MPRIS now-playing and transport buttons. See
  [docs/audio.md](docs/audio.md).
- **WiFi & Bluetooth**: connected signal, periodic AP/BT scans (a
  geolocation fingerprint), and BT presence sensors (`WATCH_BT_MACS`). See
  [docs/radio.md](docs/radio.md).

A ready Lovelace dashboard is in
[`dashboards/linux2mqtt.yaml`](dashboards/linux2mqtt.yaml).

## Run

```bash
pip install linux2mqtt
MQTT_HOST=192.168.1.10 MQTT_USER=… MQTT_PASSWORD=… python -m linux2mqtt
```

Or run it in Docker (see [`docker-compose.yml`](docker-compose.yml), which
includes the Raspberry Pi `vcgencmd` recipe):

```bash
docker run -d --name linux2mqtt --network host --restart unless-stopped \
  -e MQTT_HOST=127.0.0.1 -e MQTT_USER=… -e MQTT_PASSWORD=… \
  ghcr.io/tigregotico/linux2mqtt:latest
```

## Calibrate the power estimate

```bash
linux2mqtt-calibrate            # smart plug over MQTT
linux2mqtt-calibrate --battery  # laptop battery, fully automatic (CPU+GPU load)
```

## Docs

- [Home Assistant](docs/homeassistant.md): entities, cards, energy dashboard.
- [Components](docs/components.md): the CPU/GPU breakdown.
- [Raspberry Pi](docs/raspberry-pi.md): PMIC power, throttle/overheat/overclock,
  and running `vcgencmd` in a container.
- [Configuration](docs/configuration.md): all environment variables.

Power estimation, calibration, and the dataset/model live in
[powerguess](https://github.com/TigreGotico/powerguess).

## License

Apache-2.0
