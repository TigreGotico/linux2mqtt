# System telemetry

Beyond power and the CPU/GPU/Pi components, linux2mqtt publishes general host
telemetry from `psutil` (`USE_SYSTEM=true`, the default). Anything unavailable on
a host (no fan sensor, an unreadable mount, no load average) is omitted, not faked.

## Sensors

| Entity | Source | Notes |
| --- | --- | --- |
| RAM Usage / RAM Used / RAM Total | `virtual_memory` | % and MB |
| Swap Usage | `swap_memory` | % |
| Disk *&lt;mount&gt;* Usage / Free | `disk_usage` | per `DISK_PATHS`; % and GB. **The SBC metric** — a full SD card corrupts a Pi |
| Uptime | `boot_time` | `device_class: timestamp` — HA shows "x days ago" and flags reboots |
| Load 1m / 5m / 15m | `os.getloadavg` | |
| Network Up / Down | `net_io_counters` | kB/s (rate) |
| Disk Read / Write | `disk_io_counters` | kB/s (rate) |
| IP Address | socket | diagnostic |
| CPU Cores | `cpu_count` | diagnostic |
| Fan Speed | `sensors_fans` | rpm — only where a fan sensor exists (most x86/servers; few Pis) |
| Operating System / Architecture | `platform` | diagnostic, published once |

Network and disk-IO are **rates**, computed between successive reads — the first
reading after start seeds the baseline and carries no rate yet.

## Process / service watch

Name the services you care about and each becomes a `binary_sensor`
(`device_class: running`) — match is a substring of the process name **and**
command line, so `homeassistant` matches a `python -m homeassistant` process:

```bash
WATCH_PROCESSES=sshd,mosquitto,homeassistant,dockerd
```

### In a container

A container has its own PID namespace and filesystem, so by default the process
watch sees only the container's own processes and disk usage reflects the image's
overlay. To watch the **host**, run with `--pid host` and bind-mount the mounts
you want to report, e.g. `-v /:/host:ro` with `DISK_PATHS=/host`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `USE_SYSTEM` | `true` | publish host system telemetry |
| `DISK_PATHS` | `/` | comma-separated mounts to report disk usage for |
| `WATCH_PROCESSES` | (none) | comma-separated process/service names → running sensors |
