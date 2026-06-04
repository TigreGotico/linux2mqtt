"""Raspberry Pi specifics via ``vcgencmd``.

Two SBC-only capabilities the generic paths can't provide:

- **PMIC board power** — the Pi 5 PMIC reports per-rail voltage *and* current
  through ``vcgencmd pmic_read_adc``; summing ``V × I`` over the rails gives real
  whole-board power with no extra hardware (the ARM analogue to x86 RAPL).
- **Throttling / undervoltage** — ``vcgencmd get_throttled`` flags under-voltage
  and thermal/frequency throttling, which on a Pi is both power-relevant and a
  data-integrity warning.

Everything no-ops cleanly when ``vcgencmd`` isn't present (i.e. not a Pi).
"""

from __future__ import annotations

import re
import subprocess
from shutil import which
from typing import Dict, Optional

def available() -> bool:
    return bool(which("vcgencmd"))


def _vcgencmd(*args: str) -> Optional[str]:
    if not which("vcgencmd"):
        return None
    try:
        out = subprocess.run(["vcgencmd", *args], capture_output=True, text=True,
                             timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


# (PMIC board power lives in powerguess.pmic — it's a measured *total* source.
#  This module is Pi system telemetry: throttling, clocks, voltages, overclock.)


def parse_throttled(text: str) -> Dict[str, bool]:
    """Decode a ``throttled=0x…`` value into named flags."""
    try:
        value = int(text.split("=")[-1].strip(), 16)
    except (ValueError, IndexError):
        return {}
    return {
        "undervoltage": bool(value & 0x1),
        "freq_capped": bool(value & 0x2),
        "throttled": bool(value & 0x4),
        "soft_temp_limit": bool(value & 0x8),
        "undervoltage_occurred": bool(value & 0x10000),
        "freq_capped_occurred": bool(value & 0x20000),
        "throttled_occurred": bool(value & 0x40000),
        "soft_temp_limit_occurred": bool(value & 0x80000),
    }


def get_throttled() -> Dict[str, bool]:
    """Current throttling / undervoltage flags, or empty when unavailable."""
    out = _vcgencmd("get_throttled")
    return parse_throttled(out) if out else {}


def _num(out: Optional[str]) -> Optional[float]:
    """Pull the leading number from a ``key=value[unit]`` vcgencmd response."""
    if not out:
        return None
    val = out.split("=")[-1].strip()
    m = re.match(r"-?[\d.]+", val)
    return float(m.group()) if m else None


def soc_telemetry() -> Dict[str, object]:
    """Throttling flags plus clock/voltage/overclock telemetry for a Pi.

    Covers the three things worth alerting on: **throttling**
    (``throttled`` / ``freq_capped``), **overheating** (``soft_temp_limit`` and
    the SoC temperature), and **overclocking** (configured ``arm_freq`` /
    ``over_voltage`` above stock, and the live ARM clock).
    """
    data: Dict[str, object] = dict(get_throttled())
    arm_clock = _num(_vcgencmd("measure_clock", "arm"))
    arm_cfg = _num(_vcgencmd("get_config", "arm_freq"))
    over_voltage = _num(_vcgencmd("get_config", "over_voltage"))
    core_volts = _num(_vcgencmd("measure_volts", "core"))
    temp = _num(_vcgencmd("measure_temp"))
    if arm_clock is not None:
        data["arm_clock_mhz"] = round(arm_clock / 1_000_000, 1)
    if arm_cfg is not None:
        data["arm_freq_config_mhz"] = arm_cfg
    if over_voltage is not None:
        data["over_voltage"] = over_voltage
    if core_volts is not None:
        data["core_volts"] = round(core_volts, 4)
    if temp is not None:
        data["temperature"] = round(temp, 1)
    # Overclocked: an explicit over-voltage, or a configured clock above the
    # measured stock ceiling (firmware reports config in MHz).
    data["overclocked"] = bool((over_voltage or 0) > 0)
    return data
