# Component breakdown (CPU & GPU)

Beyond the whole-device total, PowerGuess publishes per-component telemetry as its
own Home Assistant entities under the same device. Each component reports the
reliable signals everywhere, and **power only when the source is trustworthy** —
a guess or a known-bad sensor reading is never published as a number.

## CPU

Always published (`USE_CPU=true`, the default):

| Entity | Unit | Source |
| --- | --- | --- |
| `cpu_utilization` | % | psutil |
| `cpu_frequency` | MHz | psutil |
| `cpu_temperature` | °C | `psutil` / `/sys/class/thermal` |
| `cpu_power` | W | **RAPL** — only when `/sys/class/powercap/.../energy_uj` is readable |

`cpu_power` is the CPU **package** power from Intel/AMD RAPL (`powerguess/rapl.py`),
computed from `energy_uj` deltas. It's often root-only readable, in which case the
entity is simply omitted rather than faked. RAPL measures the *package*, not the
whole device — which is exactly why it's a component here and **not** the
total-power source.

### Reading RAPL as non-root (containers / uid-mapped)

Since CVE-2020-8694, `energy_uj` is `0400 root`. A container run as a non-root uid
(e.g. to reach the user D-Bus session bus for [MPRIS](audio.md)) can't read it, so
`cpu_power` drops. To expose it persistently, add a udev rule on the **host**:

```bash
echo 'SUBSYSTEM=="powercap", ACTION=="add", RUN+="/bin/chmod -R a+r /sys/class/powercap/%k"' \
  | sudo tee /etc/udev/rules.d/99-rapl.rules
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=powercap
```

(or a one-shot systemd service running `chmod -R a+r /sys/class/powercap/intel-rapl:*`).
This re-exposes the RAPL power side-channel to local users — fine on a trusted
host. Restart the container afterwards so it re-detects RAPL.

## GPU (NVIDIA & AMD)

Auto-detected (`USE_GPU=true`, `GPU_INDEX=0`): **NVIDIA** via `nvidia-smi`, **AMD**
via the amdgpu **sysfs/hwmon** interface (`gpu_busy_percent`, `temp1_input`,
`power1_average`/`power1_input`, `mem_info_vram_*`) — no extra tools, like RAPL.
With multiple AMD cards (dGPU + APU iGPU), `GPU_INDEX` picks among them (0 = first).
In a container the host `/sys` must be visible (e.g. `--privileged`).

| Entity | Unit | Notes |
| --- | --- | --- |
| `gpu_utilization` | % | |
| `gpu_temperature` | °C | |
| `gpu_memory` | % | VRAM used |
| `gpu_power` | W | **validated** — published only when credible |

### Why GPU power is validated

`nvidia-smi` power draw is unreliable on some hardware — several laptop GPUs report
a fixed/garbage value with no power limit (one RTX 3060 Laptop reported **752 W**).
So `powerguess/gpu.py` checks the reading against the GPU's power limit and a sane
ceiling: a value over the limit (×1.3), or over 600 W with no limit reported, is
treated as **unavailable** and the `gpu_power` entity is not published. Utilization,
temperature, and memory are reliable and always published.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `USE_CPU` | `true` | publish the CPU component |
| `USE_GPU` | `true` | publish the GPU component (NVIDIA) |
| `GPU_INDEX` | `0` | which GPU to read |

## Roadmap

The component model is extensible behind the same pattern — per-RAPL-domain (DRAM)
breakout and non-NVIDIA GPUs are natural additions. On a Raspberry Pi the SoC is
its own "component" of sorts: see [raspberry-pi.md](raspberry-pi.md) for the
throttling / overheating / overclocking sensors.
