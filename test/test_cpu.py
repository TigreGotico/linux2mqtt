import linux2mqtt.cpu as cpu_mod
from linux2mqtt.cpu import CPUMonitor, CPUReading, read_cpu_temp


def test_cpu_reading_as_dict_without_power():
    r = CPUReading(utilization=37.4, frequency_mhz=2400.6, temperature=55.2, power=None)
    d = r.as_dict()
    assert d == {"utilization": 37.4, "frequency_mhz": 2401.0, "temperature": 55.2}
    assert r.power_valid is False
    assert "power" not in d


def test_cpu_reading_with_power():
    r = CPUReading(40, 3000, 60, power=18.7)
    assert r.power_valid is True
    assert r.as_dict()["power"] == 18.7


def test_read_cpu_temp_is_float():
    assert isinstance(read_cpu_temp(), float)


def test_monitor_reads_without_rapl(monkeypatch):
    # No RAPL -> reading has util/freq/temp but power is None.
    monkeypatch.setattr(cpu_mod, "rapl_available", lambda: False)
    m = CPUMonitor()
    assert m.power_available() is False
    r = m.read()
    assert isinstance(r, CPUReading)
    assert r.power is None
    assert r.utilization >= 0


def test_monitor_reads_power_with_rapl(monkeypatch):
    class FakeRapl:
        def read(self):
            return 0.0, 0.0, 22.5

    monkeypatch.setattr(cpu_mod, "rapl_available", lambda: True)
    monkeypatch.setattr(cpu_mod, "RaplReader", lambda: FakeRapl())
    m = CPUMonitor()
    assert m.power_available() is True
    assert m.read().power == 22.5
