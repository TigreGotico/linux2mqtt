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

## GPU (NVIDIA)

Auto-detected via `nvidia-smi` (`USE_GPU=true`, `GPU_INDEX=0`):

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
