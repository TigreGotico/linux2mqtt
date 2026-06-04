import os
import linux2mqtt.gpu as gpu_mod
from linux2mqtt.gpu import GPUReading, parse_gpu_csv, _validate_power, AmdGPU


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


def _fake_amd_card(tmp_path, busy=100, vram_used=16969158656, vram_total=17163091968,
                   temp=62000, power_avg=122000000, power_input=None):
    dev = tmp_path / "card0" / "device"
    hw = dev / "hwmon" / "hwmon9"
    hw.mkdir(parents=True)
    (dev / "vendor").write_text("0x1002\n")
    (dev / "gpu_busy_percent").write_text(f"{busy}\n")
    (dev / "mem_info_vram_used").write_text(f"{vram_used}\n")
    (dev / "mem_info_vram_total").write_text(f"{vram_total}\n")
    (hw / "temp1_input").write_text(f"{temp}\n")
    if power_avg is not None:
        (hw / "power1_average").write_text(f"{power_avg}\n")
    if power_input is not None:
        (hw / "power1_input").write_text(f"{power_input}\n")
    return str(dev)


def test_amd_read_dgpu(tmp_path, monkeypatch):
    dev = _fake_amd_card(tmp_path)
    monkeypatch.setattr(AmdGPU, "cards", staticmethod(lambda: [dev]))
    r = AmdGPU(0).read()
    assert r.name == "AMD GPU"
    assert r.utilization == 100.0 and r.temperature == 62.0
    assert r.power == 122.0 and r.power_valid is True
    assert r.as_dict()["memory_percent"] == 98.9  # 16.97/17.16 GB


def test_amd_power_input_fallback(tmp_path, monkeypatch):
    # APU/iGPU style: only power1_input present.
    dev = _fake_amd_card(tmp_path, busy=0, power_avg=None, power_input=37189000)
    monkeypatch.setattr(AmdGPU, "cards", staticmethod(lambda: [dev]))
    assert AmdGPU(0).read().as_dict()["power"] == 37.19


def test_amd_unavailable(monkeypatch):
    monkeypatch.setattr(AmdGPU, "cards", staticmethod(lambda: []))
    assert AmdGPU.available() is False
