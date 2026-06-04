# Raspberry Pi / SBC

Single-board computers are the case PowerGuess exists for — headless, no battery,
no smart plug, and no x86 power telemetry. Here's how it behaves and how to get
real numbers.

## What works out of the box

- **Model detection** — `/proc/device-tree/model` identifies the board and loads
  the matching profile (`pi4.json`, `pi3b.json`, `pi02.json`, …).
- **CPU component** — utilization, frequency, and temperature (from
  `/sys/class/thermal`) are published like on any host. (No `cpu_power`: RAPL is
  x86-only.)
- **Total power** — with no measured source, it's the **estimate** from CPU load
  against the board profile, with an honest error band.

## Get measured power (best → easiest)

1. **Raspberry Pi 5 only — zero hardware.** The Pi 5 PMIC reports per-rail voltage
   and current via `vcgencmd pmic_read_adc`; PowerGuess sums them into real
   whole-board power (source `pmic`). Auto-detected — the SBC analogue to x86 RAPL.
   **Pi 3/4 have a PMIC but expose no ADC telemetry**, so there's no firmware-only
   power path there — PowerGuess probes once at startup and, finding none, won't
   poll it.
2. **INA219 / INA260 power HAT — any Pi/SBC, including Pi 3/4.** A cheap I²C power
   monitor on the supply gives exact total power. `pip install powerguess[ina219]`,
   `USE_INA219=true`. This is the measured path for Pi 3/4 and non-Pi SBCs.
3. **Calibrate the estimate with a smart plug** — `powerguess-calibrate` measures
   idle and peak over MQTT and pins the profile to your board + peripherals. Or
   bound it with `CALIBRATION_IDLE_W` + `CALIBRATION_PSU_W`.

The profiles are deliberately coarse (a Pi 4 with a couple of USB SSDs draws very
differently from a bare one), so a meter or a calibration is the way to trust the
number — and that data can feed the [dataset/model](dataset.md).

## Throttling, overheating, overclocking

When `vcgencmd` is available, PowerGuess publishes SoC health sensors (auto-enabled
via `USE_RPI`):

- **Throttling** — `throttled`, `freq_capped` binary sensors (+ `throttled_occurred`
  history), and the live `arm_clock` (MHz) which drops when the firmware throttles.
- **Overheating** — `soft_temp_limit` and `soft_temp_limit_occurred` binary sensors
  (the firmware's thermal-throttle flag), alongside `cpu_temperature`.
- **Overclocking** — `overclocked` (set when `over_voltage > 0`), plus the
  `over_voltage` and configured `arm_freq` sensors and the live `arm_clock`.
- **Undervoltage** — `undervoltage` / `undervoltage_occurred` (SD-card-corrupting,
  worth an alert on its own).

### Running in a container

`vcgencmd` is statically linked (only needs libc), so wire it in by mounting the
host binary and the VideoCore device — no extra libraries:

```bash
docker run -d --name powerguess --network host --restart unless-stopped \
  -e MQTT_HOST=127.0.0.1 -e MQTT_USER=<u> -e MQTT_PASSWORD=<p> \
  -e POWERGUESS_MODEL="$(tr -d '\0' </proc/device-tree/model)" \
  -e CALIBRATION_FILE=/data/calibration.json -e ENERGY_FILE=/data/energy.json \
  -v powerguess-data:/data \
  -v /sys/class/thermal:/sys/class/thermal:ro \
  -v /usr/bin/vcgencmd:/usr/bin/vcgencmd:ro --device /dev/vcio --device /dev/vchiq \
  powerguess:latest
```

`POWERGUESS_MODEL` is passed in because `/proc/device-tree` isn't reliably visible
inside a container. On a Pi 5, add nothing else — PMIC board power is detected
automatically.

## Summary

| | Pi 3/4 (bare) | Pi 5 (bare) | + INA219 HAT | + smart plug |
| --- | --- | --- | --- | --- |
| total power | estimate (±band) | **measured (PMIC)** | **measured** | calibrated estimate |
| CPU util/temp/freq | ✅ | ✅ | ✅ | ✅ |
| undervoltage/throttle | ✅ | ✅ | ✅ | ✅ |

So: a **Pi 5** gets real power for free; a **Pi 3/4** needs an INA219 HAT or a
smart-plug calibration for measured power, but still gets the estimate, CPU
telemetry, and undervoltage/throttling sensors.
