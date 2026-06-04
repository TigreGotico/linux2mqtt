import json

import pytest

from linux2mqtt.config import Config
from linux2mqtt.mqtt_client import MQTTClient
from powerguess.reading import Reading


class FakeClient:
    def __init__(self):
        self.published = []
        self.on_connect = self.on_disconnect = None

    def username_pw_set(self, *a):
        pass

    def connect(self, *a, **k):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, json.loads(payload)))


@pytest.fixture
def client_with_battery():
    fake = FakeClient()
    c = MQTTClient(has_battery=True, client=fake)
    c._connected = True
    return c, fake


def test_discovery_without_battery():
    fake = FakeClient()
    c = MQTTClient(has_battery=False, client=fake)
    c._connected = True
    c.publish_discovery()
    keys = [t.split("/")[-2] for t, _ in fake.published]
    assert keys == ["power", "current", "voltage", "energy", "source",
                    "error_margin", "power_floor", "power_ceiling", "model"]
    energy = [p for t, p in fake.published if t.endswith("/energy/config")][0]
    assert energy["device_class"] == "energy"
    assert energy["state_class"] == "total_increasing"


def test_discovery_with_battery(client_with_battery):
    c, fake = client_with_battery
    c.publish_discovery()
    topics = [t for t, _ in fake.published]
    assert any("battery_level" in t for t in topics)
    assert any("binary_sensor" in t and "charging" in t for t in topics)
    assert len(topics) == 13  # 9 core (incl. envelope) + 4 battery


def test_publish_reading_carries_provenance_and_energy(client_with_battery):
    c, fake = client_with_battery
    r = Reading(5.1, 5.0, 1.02, "estimate", error_margin=1.5)
    assert c.publish_reading(r, energy_wh=1234.5, bounds=(2.7, 10.0),
                             force=True) is True
    topic, payload = fake.published[-1]
    assert topic == "powerguess/state"
    assert payload["source"] == "estimate" and payload["measured"] is False
    assert payload["error_margin"] == 1.5
    assert payload["energy"] == round(1234.5 / 1000, 4)
    assert payload["floor"] == 2.7 and payload["ceiling"] == 10.0


def test_discovery_includes_availability_and_envelope():
    fake = FakeClient()
    c = MQTTClient(has_battery=False, client=fake)
    c._connected = True
    c.publish_discovery()
    keys = [t.split("/")[-2] for t, _ in fake.published]
    assert "power_floor" in keys and "power_ceiling" in keys
    power_cfg = [p for t, p in fake.published if t.endswith("/power/config")][0]
    assert power_cfg["availability_topic"] == "powerguess/availability"
    assert power_cfg["payload_not_available"] == "offline"


def test_cost_sensor_when_tariff_set():
    Config.ENERGY_TARIFF = 0.30
    Config.CURRENCY = "EUR"
    try:
        fake = FakeClient()
        c = MQTTClient(has_battery=False, client=fake)
        c._connected = True
        c.publish_discovery()
        assert any(t.endswith("/cost/config") for t, _ in fake.published)
        c.publish_reading(Reading(10, 5, 2, "estimate"), energy_wh=2000, force=True)
        payload = fake.published[-1][1]
        assert payload["cost"] == round(2.0 * 0.30, 4)  # 2 kWh * 0.30
    finally:
        Config.ENERGY_TARIFF = 0.0


def test_delta_publishing(client_with_battery):
    c, fake = client_with_battery
    Config.PUBLISH_DELTA = 0.5
    assert c.publish_reading(Reading(5.0, 5, 1, "estimate"), force=True) is True
    # within PUBLISH_INTERVAL and below delta -> suppressed
    assert c.publish_reading(Reading(5.2, 5, 1, "estimate")) is False
    # jump beyond delta -> published immediately
    assert c.publish_reading(Reading(9.0, 5, 1.8, "estimate")) is True


def test_publish_battery(client_with_battery):
    c, fake = client_with_battery
    c.publish_battery({"capacity": 79, "status": "Charging", "power": 9.1,
                       "voltage": 16.9})
    topic, payload = fake.published[-1]
    assert topic == "powerguess/battery"
    assert payload["charging"] is True and payload["level"] == 79
