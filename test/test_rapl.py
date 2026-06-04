"""RAPL reader tested against fake sysfs counters (no real powercap needed)."""
import linux2mqtt.rapl as rapl_mod
from linux2mqtt.rapl import RaplReader


class FakeRapl(RaplReader):
    """RaplReader with scripted energy/time instead of sysfs."""

    def __init__(self, energies, times):
        self._energies = list(energies)
        self._times = list(times)
        self._domains = [("fake", 1_000_000_000)]  # wrap value
        self._last_energy = None
        self._last_time = None

    def _total_energy(self):
        return self._energies.pop(0) if self._energies else None

    def read(self):
        # Override the clock with scripted times.
        import linux2mqtt.rapl as m
        orig = m.time.monotonic
        m.time.monotonic = lambda: self._times.pop(0)
        try:
            return super().read()
        finally:
            m.time.monotonic = orig


def test_first_read_returns_none():
    r = FakeRapl([1_000_000], [100.0])
    assert r.read() is None  # need a baseline first


def test_power_from_energy_delta():
    # 10 J consumed over 2 s = 5 W. energy in µJ.
    r = FakeRapl([0, 10_000_000], [100.0, 102.0])
    assert r.read() is None
    v, i, p = r.read()
    assert round(p, 2) == 5.0


def test_counter_wraparound():
    # delta would be negative; wrap is 1e9 µJ -> add it back.
    r = FakeRapl([999_000_000, 1_000_000], [10.0, 11.0])
    assert r.read() is None
    _, _, p = r.read()
    # (1_000_000 - 999_000_000 + 1_000_000_000) µJ = 2_000_000 µJ = 2 J over 1 s
    assert round(p, 2) == 2.0


def test_available_is_boolean(monkeypatch):
    monkeypatch.setattr(rapl_mod, "_package_domains", lambda: [])
    assert rapl_mod.available() is False
