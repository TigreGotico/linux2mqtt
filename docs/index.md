# linux2mqtt documentation

linux2mqtt publishes a Linux or SBC box's power and system telemetry to MQTT
for Home Assistant. The [powerguess](https://github.com/TigreGotico/powerguess)
library provides the power reading. This project adds the telemetry and the
MQTT/HA bridge.

## Pages

- **[Home Assistant](homeassistant.md)**: the entities, dashboard cards, the
  energy dashboard, MQTT topics, and availability.
- **[Components](components.md)**: the CPU and GPU breakdown (utilization,
  temperature, frequency/VRAM, validated power).
- **[System telemetry](system.md)**: memory, disk, uptime, load, network,
  disk-IO, fan, and a process/service watch.
- **[Audio & media](audio.md)**: PipeWire/PulseAudio/ALSA status, volume/mic
  control, and MPRIS now-playing and transport (MQTT command topics).
- **[WiFi & Bluetooth](radio.md)**: connected signal, periodic AP/BT scans, BT
  presence, and a geolocation fingerprint for ingeo.
- **[Deployment](deployment.md)**: Docker recipes per host: the base run, the
  capability-to-mount matrix, and worked examples (Pi, server, audio box,
  laptop).
- **[Dashboard](../dashboards/linux2mqtt.yaml)**: a ready Lovelace dashboard.
- **[Raspberry Pi](raspberry-pi.md)**: Pi 5 PMIC power, INA219 HATs, and the
  throttling, overheating, and overclocking sensors, plus `vcgencmd` in a
  container.
- **[Configuration](configuration.md)**: every environment variable.

## Calibrating the power estimate

```bash
linux2mqtt-calibrate            # measure idle/peak with an MQTT smart plug
linux2mqtt-calibrate --battery  # laptops: automatic, CPU+GPU load, no smart plug
```

The estimate model, bounded-envelope theory, calibration API, and
dataset/trainer are documented in
[powerguess](https://github.com/TigreGotico/powerguess).
