"""GPU telemetry as a first-class component — NVIDIA via ``nvidia-smi``, AMD via
the amdgpu sysfs/hwmon interface.

Tracks the GPU as its own thing alongside whole-device power: utilization,
temperature, memory, and — when reported credibly — power draw.

GPU power from ``nvidia-smi`` is unreliable on some hardware (several laptop GPUs
report a fixed/garbage value with no power limit), so power is **validated**
against the reported limit and a sane ceiling; when it doesn't check out, power is
returned as ``None`` rather than published as a fake number. AMD reports power in
``hwmon`` (``power1_average``/``power1_input``, microwatts), validated against the
same ceiling. The other fields are reliable across hardware.
"""

from __future__ import annotations

import dataclasses
import glob
import os
import subprocess
from shutil import which
from typing import List, Optional

_QUERY = ("power.draw,power.limit,utilization.gpu,temperature.gpu,"
          "memory.used,memory.total,name")
_SANE_MAX_W = 600.0  # no consumer GPU sustains more; reject obvious garbage


@dataclasses.dataclass(frozen=True)
class GPUReading:
    name: str
    utilization: float          # %
    temperature: float          # °C
    memory_used: float          # MB
    memory_total: float         # MB
    power: Optional[float]      # W, or None when the driver's value isn't credible

    @property
    def power_valid(self) -> bool:
        return self.power is not None

    def as_dict(self) -> dict:
        d = {
            "name": self.name,
            "utilization": round(self.utilization, 1),
            "temperature": round(self.temperature, 1),
            "memory_used": round(self.memory_used, 1),
            "memory_total": round(self.memory_total, 1),
            "memory_percent": round(100 * self.memory_used / self.memory_total, 1)
            if self.memory_total else 0.0,
        }
        if self.power is not None:
            d["power"] = round(self.power, 2)
        return d


def _to_float(token: str) -> Optional[float]:
    token = token.strip()
    if not token or token.upper().startswith(("N/A", "[N/A]", "[NOT")):
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _validate_power(draw: Optional[float], limit: Optional[float]) -> Optional[float]:
    """Trust GPU power only when it's positive and bounded by a sane limit."""
    if draw is None or draw <= 0:
        return None
    if limit is not None:
        return draw if draw <= limit * 1.3 else None
    # No limit reported (the unreliable case) — accept only plausible values.
    return draw if draw <= _SANE_MAX_W else None


def parse_gpu_csv(line: str) -> Optional[GPUReading]:
    """Parse one nvidia-smi CSV row (noheader,nounits) into a GPUReading."""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 7:
        return None
    draw, limit, util, temp, mem_used, mem_total = (_to_float(p) for p in parts[:6])
    name = parts[6] or "GPU"
    return GPUReading(
        name=name,
        utilization=util or 0.0,
        temperature=temp or 0.0,
        memory_used=mem_used or 0.0,
        memory_total=mem_total or 0.0,
        power=_validate_power(draw, limit),
    )


class NvidiaGPU:
    """Read GPU telemetry from ``nvidia-smi`` (GPU index 0)."""

    def __init__(self, index: int = 0):
        self.index = index

    @staticmethod
    def available() -> bool:
        return bool(which("nvidia-smi"))

    def read(self) -> Optional[GPUReading]:
        if not which("nvidia-smi"):
            return None
        try:
            out = subprocess.run(
                ["nvidia-smi", f"--id={self.index}",
                 f"--query-gpu={_QUERY}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return parse_gpu_csv(out.stdout.strip().split("\n")[0])


def _sysfs_int(path: str) -> Optional[int]:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


class AmdGPU:
    """Read AMD GPU telemetry from amdgpu sysfs/hwmon (no extra tools)."""

    def __init__(self, index: int = 0):
        cards = self.cards()
        self._dev = cards[index] if index < len(cards) else cards[0]
        hwmons = sorted(glob.glob(os.path.join(self._dev, "hwmon", "hwmon*")))
        self._hwmon = hwmons[0] if hwmons else None

    @staticmethod
    def cards() -> List[str]:
        """device dirs of AMD GPUs (vendor 0x1002) that report utilization."""
        found = []
        for dev in sorted(glob.glob("/sys/class/drm/card[0-9]*/device")):
            try:
                with open(os.path.join(dev, "vendor")) as f:
                    vendor = f.read().strip()
            except OSError:
                continue
            if vendor == "0x1002" and os.path.exists(os.path.join(dev, "gpu_busy_percent")):
                found.append(dev)
        return found

    @staticmethod
    def available() -> bool:
        return bool(AmdGPU.cards())

    def read(self) -> Optional[GPUReading]:
        util = _sysfs_int(os.path.join(self._dev, "gpu_busy_percent"))
        if util is None:
            return None
        used = _sysfs_int(os.path.join(self._dev, "mem_info_vram_used")) or 0
        total = _sysfs_int(os.path.join(self._dev, "mem_info_vram_total")) or 0
        temp = power = None
        if self._hwmon:
            t = _sysfs_int(os.path.join(self._hwmon, "temp1_input"))
            temp = t / 1000.0 if t is not None else None
            uw = (_sysfs_int(os.path.join(self._hwmon, "power1_average"))
                  or _sysfs_int(os.path.join(self._hwmon, "power1_input")))
            power = uw / 1_000_000.0 if uw else None
        return GPUReading(
            name="AMD GPU",
            utilization=float(util),
            temperature=temp or 0.0,
            memory_used=used / 1_048_576.0,
            memory_total=total / 1_048_576.0,
            power=_validate_power(power, None),
        )


def detect_gpu(index: int = 0):
    """Return an NVIDIA or AMD GPU monitor, or None when no GPU is found."""
    if NvidiaGPU.available():
        return NvidiaGPU(index)
    if AmdGPU.available():
        return AmdGPU(index)
    return None
