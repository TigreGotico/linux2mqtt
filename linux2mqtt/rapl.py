"""Read x86 package power directly from the kernel's RAPL powercap interface.

``/sys/class/powercap/intel-rapl:*/energy_uj`` is a monotonic microjoule counter
per CPU package. Power is the energy delta over the time delta — no ``powerstat``,
no subprocess, no fragile column parsing. The counter wraps at
``max_energy_range_uj``, which is handled. On many systems ``energy_uj`` is
root-readable only; when it isn't readable the reader reports itself unavailable
and PowerGuess falls back to the next source.
"""

from __future__ import annotations

import glob
import os
import time
from typing import List, Optional, Tuple

_BASE = "/sys/class/powercap"


def _package_domains() -> List[str]:
    # Top-level intel-rapl:N domains are CPU packages (skip the :N:M subzones).
    return sorted(glob.glob(os.path.join(_BASE, "intel-rapl:[0-9]*")))


def available() -> bool:
    """True when at least one package energy counter exists and is readable."""
    for d in _package_domains():
        path = os.path.join(d, "energy_uj")
        if os.access(path, os.R_OK):
            try:
                with open(path) as f:
                    f.read()
                return True
            except OSError:
                continue
    return False


class RaplReader:
    """Turn the RAPL energy counters into a power reading across calls."""

    def __init__(self):
        self._domains = []
        for d in _package_domains():
            energy = os.path.join(d, "energy_uj")
            if not os.access(energy, os.R_OK):
                continue
            wrap = self._read_int(os.path.join(d, "max_energy_range_uj")) or 0
            self._domains.append((energy, wrap))
        self._last_energy: Optional[int] = None
        self._last_time: Optional[float] = None

    @staticmethod
    def _read_int(path: str) -> Optional[int]:
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _total_energy(self) -> Optional[int]:
        total = 0
        ok = False
        for energy_path, _ in self._domains:
            value = self._read_int(energy_path)
            if value is not None:
                total += value
                ok = True
        return total if ok else None

    @property
    def _wrap(self) -> int:
        return sum(w for _, w in self._domains) or 0

    def read(self) -> Optional[Tuple[float, float, float]]:
        """Return ``(voltage, current, power)`` in W, or ``None`` until two reads.

        Voltage/current aren't exposed by RAPL, so voltage is 0 and current 0 —
        callers that need them derive from a known supply voltage; power is exact.
        """
        now = time.monotonic()
        energy = self._total_energy()
        if energy is None:
            return None
        if self._last_energy is None:
            self._last_energy, self._last_time = energy, now
            return None
        dt = now - self._last_time
        delta = energy - self._last_energy
        if delta < 0 and self._wrap:  # counter wrapped
            delta += self._wrap
        self._last_energy, self._last_time = energy, now
        if dt <= 0:
            return None
        watts = (delta / 1_000_000) / dt  # µJ -> J, over seconds
        return 0.0, 0.0, max(0.0, watts)
