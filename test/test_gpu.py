from linux2mqtt.gpu import GPUReading, parse_gpu_csv, _validate_power


def test_parse_valid_row():
    r = parse_gpu_csv("85.5, 115.0, 70, 65, 4096, 8192, NVIDIA RTX 4070")
    assert r.name == "NVIDIA RTX 4070"
    assert r.utilization == 70 and r.temperature == 65
    assert r.power == 85.5 and r.power_valid is True
    assert r.as_dict()["memory_percent"] == 50.0


def test_reject_garbage_power_without_limit():
    # The real laptop case: 752 W draw, no power limit -> power unavailable.
    r = parse_gpu_csv("752.67, [N/A], 0, 50, 15, 6144, RTX 3060 Laptop GPU")
    assert r.power is None and r.power_valid is False
    # ...but utilization/temp/memory are still reported.
    assert r.temperature == 50 and r.memory_total == 6144
    assert "power" not in r.as_dict()


def test_accept_plausible_power_without_limit():
    r = parse_gpu_csv("21.5, [N/A], 0, 48, 15, 6144, RTX 3060 Laptop GPU")
    assert r.power == 21.5 and r.power_valid is True


def test_reject_power_far_over_limit():
    r = parse_gpu_csv("400, 115, 99, 80, 7000, 8192, RTX 4070")
    assert r.power is None  # 400 >> 115*1.3


def test_validate_power_helper():
    assert _validate_power(50, 115) == 50
    assert _validate_power(200, 115) is None
    assert _validate_power(21.5, None) == 21.5
    assert _validate_power(752, None) is None
    assert _validate_power(0, 115) is None


def test_short_row_returns_none():
    assert parse_gpu_csv("85, 115, 70") is None
