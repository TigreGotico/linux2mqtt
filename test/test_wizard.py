from linux2mqtt.wizard import (MQTTPowerMeter, build_calibration, parse_power,
                               summarise)


# --- parse_power ---------------------------------------------------------------

def test_parse_bare_number():
    assert parse_power("4.2") == 4.2


def test_parse_tasmota_json():
    payload = '{"Time":"...","ENERGY":{"Power":12.3,"Voltage":230}}'
    assert parse_power(payload, "ENERGY.Power") == 12.3


def test_parse_case_insensitive_path():
    assert parse_power('{"energy":{"power":7}}', "ENERGY.Power") == 7.0


def test_parse_shelly_apower_autodetect():
    assert parse_power('{"apower": 9.5, "voltage": 230}') == 9.5


def test_parse_garbage_returns_none():
    assert parse_power("not power", "ENERGY.Power") is None
    assert parse_power("") is None


# --- summarise -----------------------------------------------------------------

def test_summarise():
    s = summarise([2, 4, 6, 8, 100])
    assert s["n"] == 5
    assert s["median"] == 6
    assert s["max"] == 100
    assert s["min"] == 2


def test_summarise_empty():
    assert summarise([])["n"] == 0


# --- build_calibration ---------------------------------------------------------

def test_build_calibration_typical():
    idle = [2.6, 2.7, 2.7, 2.8]
    load = [6.0, 6.3, 6.4, 6.5, 6.4]
    cal, warnings = build_calibration(idle, load, voltage=5.0, psu_watts=15)
    assert cal.idle_power == 2.7  # median
    assert cal.load_power >= 6.3  # ~p90
    assert cal.voltage == 5.0
    assert cal.source == "manual"
    assert warnings == []


def test_build_calibration_warns_load_not_above_idle():
    cal, warnings = build_calibration([5, 5, 5], [5, 5, 5])
    assert any("not above idle" in w for w in warnings)


def test_build_calibration_warns_over_psu():
    cal, warnings = build_calibration([2, 2], [50, 51, 52], psu_watts=15)
    assert any("exceeds the PSU rating" in w for w in warnings)


def test_build_calibration_no_readings():
    cal, warnings = build_calibration([], [])
    assert cal is None
    assert any("no plug readings" in w for w in warnings)


# --- MQTTPowerMeter with a fake client ----------------------------------------

class FakeMsg:
    def __init__(self, payload):
        self.payload = payload.encode("utf-8")


class FakeClient:
    def __init__(self):
        self.on_message = None
        self.subscribed = []

    def username_pw_set(self, *a):
        pass

    def connect(self, *a, **k):
        pass

    def subscribe(self, topic):
        self.subscribed.append(topic)

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass


def test_meter_parses_incoming_messages():
    fake = FakeClient()
    meter = MQTTPowerMeter("h", 1883, "tele/plug/SENSOR", key="ENERGY.Power",
                           client=fake)
    meter.connect()
    assert fake.subscribed == ["tele/plug/SENSOR"]
    fake.on_message(fake, None, FakeMsg('{"ENERGY":{"Power":5.5}}'))
    assert meter.latest() == 5.5
    assert meter.wait_for_reading(timeout=1) is True
