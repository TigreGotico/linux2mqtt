# WiFi & Bluetooth scans

For hosts with radios, linux2mqtt reports the RF environment and nearby devices —
useful for presence detection, neighbour-AP monitoring, and as a **geolocation
fingerprint** for a downstream service (see *ingeo* below). `USE_RADIO=true`.

Inactive (no entities) where there's no WiFi/Bluetooth or the tooling is missing —
e.g. a wired server. Backends: `nmcli` (WiFi) and `bluetoothctl` (Bluetooth).

## Sensors

| Entity | Source | Notes |
| --- | --- | --- |
| WiFi Signal | sensor (%) | the **connected** network's signal — read every cycle |
| WiFi SSID | sensor | connected SSID (diagnostic) |
| WiFi APs Visible | sensor (count) | last scan; the full `{ssid,bssid,signal,channel}` list is the sensor's **attributes** |
| Bluetooth Devices | sensor (count) | last scan; `{mac,name}` list in attributes |
| BT *&lt;mac&gt;* | binary_sensor (presence) | per `WATCH_BT_MACS` entry — phone near = home |

Connected-WiFi signal is cheap (every cycle). **Scans are expensive and briefly
disrupt the radio**, so they run on a slow cadence (`RADIO_SCAN_INTERVAL`,
default 300 s) and publish to `<prefix>/wifi_scan` and `<prefix>/bt_scan`.

## Presence

```bash
WATCH_BT_MACS=AA:BB:CC:DD:EE:FF,11:22:33:44:55:66
```

Each MAC becomes a `presence` binary sensor — on when the device appears in a scan.

## ingeo / geolocation

The WiFi scan (`<prefix>/wifi_scan` → `{networks: [{bssid, signal, ...}]}`) and BT
scan are a location **fingerprint**. linux2mqtt is the *producer*; a geolocation
service (**ingeo**) consumes the BSSID/RSSI set and resolves a position. Keeping
the two separate means the device with the radio does the scan and the service
does the maths. (Note: public WiFi-geolocation backends are largely gone —
ingeo needs a key or a local fingerprint DB.)

## In a container

`nmcli`/`bluetoothctl` are **clients** — they talk to the host's NetworkManager /
BlueZ over D-Bus. Ship them (the image does) and mount the system bus:

```
--net host -v /run/dbus:/run/dbus:ro
```

and the host must run NetworkManager (WiFi) and `bluetooth.service` (BT).

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `USE_RADIO` | `true` | WiFi/Bluetooth scanning |
| `RADIO_SCAN_INTERVAL` | `300` | seconds between full scans |
| `WATCH_BT_MACS` | (none) | BT MACs → presence binary sensors |
