from linux2mqtt.rpi import available, parse_throttled


def test_parse_throttled_clear():
    flags = parse_throttled("throttled=0x0")
    assert not any(flags.values())


def test_parse_throttled_undervoltage_now():
    assert parse_throttled("throttled=0x1")["undervoltage"] is True


def test_parse_throttled_history():
    flags = parse_throttled("throttled=0x50005")
    assert flags["undervoltage"] and flags["throttled"]
    assert flags["undervoltage_occurred"] and flags["throttled_occurred"]


def test_parse_throttled_thermal_history():
    # 0xe0000 = freq-cap + throttle + soft-temp-limit *occurred* (the real Pi 4).
    flags = parse_throttled("throttled=0xe0000")
    assert flags["soft_temp_limit_occurred"] is True
    assert flags["throttled_occurred"] is True
    assert flags["freq_capped_occurred"] is True
    assert flags["undervoltage"] is False  # nothing active now


def test_soc_telemetry(monkeypatch):
    import linux2mqtt.rpi as rpi

    responses = {
        ("get_throttled",): "throttled=0xe0000",
        ("measure_clock", "arm"): "frequency(48)=1500345728",
        ("get_config", "arm_freq"): "arm_freq=1500",
        ("get_config", "over_voltage"): "over_voltage=0",
        ("measure_volts", "core"): "volt=0.8500V",
        ("measure_temp",): "temp=67.2'C",
    }
    monkeypatch.setattr(rpi, "_vcgencmd", lambda *a: responses.get(a))
    t = rpi.soc_telemetry()
    assert t["arm_clock_mhz"] == 1500.3
    assert t["arm_freq_config_mhz"] == 1500
    assert t["over_voltage"] == 0
    assert t["core_volts"] == 0.85
    assert t["temperature"] == 67.2
    assert t["overclocked"] is False
    assert t["soft_temp_limit_occurred"] is True


def test_soc_telemetry_overclocked(monkeypatch):
    import linux2mqtt.rpi as rpi
    monkeypatch.setattr(rpi, "_vcgencmd", lambda *a:
                        "over_voltage=6" if a == ("get_config", "over_voltage")
                        else "throttled=0x0" if a == ("get_throttled",) else None)
    assert rpi.soc_telemetry()["overclocked"] is True


def test_parse_throttled_garbage():
    assert parse_throttled("nonsense") == {}


def test_available_is_bool():
    assert isinstance(available(), bool)
