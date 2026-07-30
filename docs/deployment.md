# Deployment (Docker)

Run one container per host, each publishing to your MQTT broker. Most
features are auto-detected and either validated or absent: they light up only
when the host has the hardware/tooling and the container can reach it, which
is what the mounts below are for.

## Base recipe

```bash
docker run -d --name linux2mqtt --network host --pid host --restart unless-stopped \
  -e MQTT_HOST=192.168.1.10 -e MQTT_USER=<u> -e MQTT_PASSWORD=<p> \
  -e MQTT_TOPIC_PREFIX=l2m_<host> -e MQTT_CLIENT_ID=l2m-<host> \
  -e DEVICE_ID=l2m_<host> -e DEVICE_NAME="<host>" \
  -e DISK_PATHS=/host -v /:/host:ro \
  ghcr.io/tigregotico/linux2mqtt:latest
```

> **Multi-host:** every host must have a unique `MQTT_TOPIC_PREFIX`,
> `MQTT_CLIENT_ID`, and `DEVICE_ID`, or they collide on the broker.

- `--network host`: reach a localhost broker and read real network counters.
- `--pid host`: the process watch (`WATCH_PROCESSES`) and load see the host.
- `-v /:/host:ro` + `DISK_PATHS=/host`: disk usage for the host, not the
  image.
- `POWERGUESS_MODEL="$(cat /sys/class/dmi/id/product_name)"` (x86) or
  `"$(tr -d '\0' </proc/device-tree/model)"` (Pi): `/sys` and `/proc` model
  detection is not reliable in a container, so pass it in.

## Capability → what to add

| Feature | Add |
| --- | --- |
| CPU temperature | `-v /sys/class/thermal:/sys/class/thermal:ro` (or `--privileged`) |
| CPU power (RAPL, x86) | `--privileged` (root reads `energy_uj`), or non-root + the [RAPL udev rule](components.md#reading-rapl-as-non-root-containers--uid-mapped) |
| GPU: AMD | `--privileged` (exposes host `/sys/class/drm` + hwmon) |
| GPU: NVIDIA | nvidia-container-toolkit + `--gpus all`, or (no toolkit) `--privileged` + mount the binary/lib: `-v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro -v $(readlink -f /usr/lib/libnvidia-ml.so.1):/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro` |
| Raspberry Pi (PMIC/throttle) | `-v /usr/bin/vcgencmd:/usr/bin/vcgencmd:ro --device /dev/vcio --device /dev/vchiq` |
| Audio (volume/mic) | `-e PULSE_SERVER=unix:/run/user/<uid>/pulse/native -v /run/user/<uid>/pulse:/run/user/<uid>/pulse` (+ `-v ~/.config/pulse/cookie:/root/.config/pulse/cookie:ro` when running as root) |
| MPRIS | run as the session uid `--user <uid>:<uid>` + `-e DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus -v /run/user/<uid>/bus:/run/user/<uid>/bus` |
| WiFi/BT scan | `-v /run/dbus:/run/dbus:ro` (image ships `nmcli`/`bluetoothctl`, host runs NetworkManager/BlueZ) |

> **The root-vs-session conflict:** MPRIS and the user pulse socket need the
> container to run as the session uid (`--user 1000`). RAPL CPU power needs
> root. To get both on one host, run as the uid and apply the
> [RAPL udev rule](components.md#reading-rapl-as-non-root-containers--uid-mapped).
> Or run linux2mqtt natively, not containerized.

## Worked examples

### Raspberry Pi (HA host)
```bash
docker run -d --name linux2mqtt --network host --pid host --restart unless-stopped \
  -e MQTT_HOST=127.0.0.1 -e MQTT_USER=<u> -e MQTT_PASSWORD=<p> \
  -e DEVICE_NAME="HA Pi" -e DEVICE_ID=l2m_pi -e MQTT_TOPIC_PREFIX=l2m_pi \
  -e POWERGUESS_MODEL="$(tr -d '\0' </proc/device-tree/model)" \
  -e DISK_PATHS=/host -v /:/host:ro -v /sys/class/thermal:/sys/class/thermal:ro \
  -v /usr/bin/vcgencmd:/usr/bin/vcgencmd:ro --device /dev/vcio --device /dev/vchiq \
  -v /run/dbus:/run/dbus:ro \
  ghcr.io/tigregotico/linux2mqtt:latest
```

### x86 headless server (CPU power, AMD GPU)
```bash
docker run -d --name linux2mqtt --privileged --network host --pid host --restart unless-stopped \
  -e MQTT_HOST=<broker> -e MQTT_USER=<u> -e MQTT_PASSWORD=<p> \
  -e DEVICE_NAME="server" -e DEVICE_ID=l2m_server -e MQTT_TOPIC_PREFIX=l2m_server \
  -e USE_RPI=false -e POWERGUESS_MODEL="$(cat /sys/class/dmi/id/product_name)" \
  -e DISK_PATHS=/host -v /:/host:ro -v /sys/class/thermal:/sys/class/thermal:ro \
  ghcr.io/tigregotico/linux2mqtt:latest
```
`--privileged` gives RAPL CPU power and AMD GPU (`/sys/class/drm`) for free.

### Audio box (audio + MPRIS + GPU + CPU power)
This runs as the session uid for MPRIS/pulse. The
[RAPL udev rule](components.md#reading-rapl-as-non-root-containers--uid-mapped)
keeps CPU power despite being non-root.
```bash
U=$(id -u)
docker run -d --name linux2mqtt --privileged --user $U:$U \
  --group-add audio --group-add bluetooth --network host --pid host --restart unless-stopped \
  -e MQTT_HOST=<broker> -e MQTT_USER=<u> -e MQTT_PASSWORD=<p> \
  -e DEVICE_NAME="audiobox" -e DEVICE_ID=l2m_audiobox -e MQTT_TOPIC_PREFIX=l2m_audiobox \
  -e USE_RPI=false -e POWERGUESS_MODEL="$(cat /sys/class/dmi/id/product_name)" -e HOME=/tmp \
  -e XDG_RUNTIME_DIR=/run/user/$U \
  -e PULSE_SERVER=unix:/run/user/$U/pulse/native \
  -e DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$U/bus \
  -e DISK_PATHS=/host -e ENERGY_FILE=/tmp/energy.json -e CALIBRATION_FILE=/tmp/calibration.json \
  -v /:/host:ro -v /sys/class/thermal:/sys/class/thermal:ro -v /run/dbus:/run/dbus:ro \
  -v /run/user/$U/pulse:/run/user/$U/pulse -v /run/user/$U/bus:/run/user/$U/bus \
  ghcr.io/tigregotico/linux2mqtt:latest
```

### Laptop (battery + NVIDIA GPU, no toolkit)
```bash
U=$(id -u); ML=$(readlink -f /usr/lib/libnvidia-ml.so.1)
docker run -d --name linux2mqtt --privileged --network host --pid host --restart unless-stopped \
  -e MQTT_HOST=<broker> -e MQTT_USER=<u> -e MQTT_PASSWORD=<p> \
  -e DEVICE_NAME="laptop" -e DEVICE_ID=l2m_laptop -e MQTT_TOPIC_PREFIX=l2m_laptop \
  -e POWERGUESS_MODEL="$(cat /sys/class/dmi/id/product_name)" \
  -e PULSE_SERVER=unix:/run/user/$U/pulse/native \
  -e DISK_PATHS=/host -v /:/host:ro -v /run/dbus:/run/dbus:ro \
  -v /run/user/$U/pulse:/run/user/$U/pulse \
  -v /home/<user>/.config/pulse/cookie:/root/.config/pulse/cookie:ro \
  -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
  -v $ML:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro \
  ghcr.io/tigregotico/linux2mqtt:latest
```
Battery gives measured power when on DC. Run as root here for NVIDIA/RAPL.
MPRIS would need the uid trade-off described above.

See [`docker-compose.yml`](../docker-compose.yml) for the compose equivalent.

---
[← WiFi & Bluetooth](radio.md) · [Home](index.md) · [Raspberry Pi →](raspberry-pi.md)
