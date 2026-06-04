"""NVIDIA GPU telemetry as a first-class component, via ``nvidia-smi``.

Tracks the GPU as its own thing alongside whole-device power: utilization,
temperature, memory, and — when the driver reports it credibly — power draw.

GPU power from ``nvidia-smi`` is unreliable on some hardware (several laptop GPUs
report a fixed/garbage value with no power limit). So power is **validated**
against the reported limit and a sane ceiling; when it doesn't check out, power is
returned as ``None`` (unavailable) rather than published as a fake number. The
other fields are reliable across hardware.
"""

from __future__ import annotations

import dataclasses
import subprocess
from shutil import which
from typing import Optional

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
