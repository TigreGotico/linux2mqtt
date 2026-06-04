"""CPU package telemetry as a component, mirroring the GPU.

Utilization, frequency, and temperature are read from psutil/sysfs and are
reliable everywhere. CPU *package power* comes from RAPL
(:mod:`powerguess.rapl`) when its sysfs counter is readable — note RAPL measures
the CPU package only, **not** the whole device, which is exactly why it belongs
here as a component rather than as the total-device power source.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

import psutil

from .rapl import RaplReader, available as rapl_available


def read_cpu_temp() -> float:
    """Best-effort CPU temperature in °C (thermal/DVFS tracks power)."""
    try:
        temps = psutil.sensors_temperatures()
        for key in ("coretemp", "cpu_thermal", "k10temp", "acpitz"):
            if temps.get(key):
                return float(temps[key][0].current)
        for entries in temps.values():
            if entries:
                return float(entries[0].current)
    except Exception:
        pass
    try:  # Raspberry Pi / generic sysfs
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return 0.0


@dataclasses.dataclass(frozen=True)
class CPUReading:
    utilization: float          # %
    frequency_mhz: float        # MHz
    temperature: float          # °C
    power: Optional[float]      # W (RAPL package), or None when unavailable

    @property
    def power_valid(self) -> bool:
        return self.power is not None

    def as_dict(self) -> dict:
        d = {
            "utilization": round(self.utilization, 1),
            "frequency_mhz": round(self.frequency_mhz, 0),
            "temperature": round(self.temperature, 1),
        }
        if self.power is not None:
            d["power"] = round(self.power, 2)
        return d


class CPUMonitor:
    """Read CPU utilization/frequency/temperature, and package power via RAPL."""

    def __init__(self):
        self._rapl = RaplReader() if rapl_available() else None

    def power_available(self) -> bool:
        return self._rapl is not None

    def read(self) -> CPUReading:
        freq = psutil.cpu_freq()
        power = None
        if self._rapl is not None:
            try:
                result = self._rapl.read()  # None on the first call (baseline)
                if result and result[2]:
                    power = result[2]
            except Exception:
                power = None
        return CPUReading(
            utilization=float(psutil.cpu_percent()),
            frequency_mhz=float(freq.current) if freq else 0.0,
            temperature=read_cpu_temp(),
            power=power,
        )
