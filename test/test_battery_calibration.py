"""Battery-meter calibration (no smart plug), with /sys reads mocked."""
import linux2mqtt.wizard as wiz
from linux2mqtt.wizard import BatteryMeter, autocalibrate_battery

DISCHARGING = {"capacity": 80, "voltage": 11.1, "current": 1.5, "power": 16.6,
               "status": "Discharging", "name": "BAT1"}
FULL = dict(DISCHARGING, status="Full", power=0.0, current=0.0)


def test_meter_discharging(monkeypatch):
    monkeypatch.setattr(wiz, "get_battery_info", lambda: iter([DISCHARGING]))
    m = BatteryMeter()
    assert m.discharging() is True
    assert m.read() == 16.6
    assert m.voltage() == 11.1


def test_meter_on_ac_reads_nothing(monkeypatch):
    monkeypatch.setattr(wiz, "get_battery_info", lambda: iter([FULL]))
    m = BatteryMeter()
    assert m.discharging() is False
    assert m.read() is None


def test_autocalibrate_refuses_on_ac(monkeypatch):
    monkeypatch.setattr(wiz, "get_battery_info", lambda: iter([FULL]))
    cal, warnings, summary = autocalibrate_battery()
    assert cal is None
    assert any("on AC" in w for w in warnings)


def test_autocalibrate_from_battery(monkeypatch):
    # Scripted meter: idle readings then load readings; load generation is a no-op.
    seq = iter([16.0, 16.2, 15.8] + [45.0, 47.0, 46.5])

    class FakeMeter:
        def discharging(self):
            return True

        def voltage(self):
            return 11.1

        def read(self):
            try:
                return next(seq)
            except StopIteration:
                return 46.0

    monkeypatch.setattr(wiz, "BatteryMeter", lambda: FakeMeter())
    monkeypatch.setattr(wiz, "generate_load", lambda *a, **k: [])
    monkeypatch.setattr(wiz, "generate_gpu_load", lambda *a, **k: None)
    monkeypatch.setattr(wiz.time, "sleep", lambda *a: None)
    monkeypatch.setattr(wiz, "_sample",
                        lambda meter, seconds, on_tick=None:
                        [meter.read() for _ in range(3)])

    cal, warnings, summary = autocalibrate_battery(idle_seconds=3, load_seconds=3)
    assert cal is not None
    assert cal.idle_power < cal.load_power
    assert cal.voltage == 11.1
    assert 15 <= cal.idle_power <= 17
    assert 44 <= cal.load_power <= 48
