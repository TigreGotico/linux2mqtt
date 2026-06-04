import linux2mqtt.system as system
from linux2mqtt.system import SystemMonitor, disk_label, proc_id


def test_disk_label():
    assert disk_label("/") == "root"
    assert disk_label("/mnt/data") == "mnt_data"
    assert disk_label("/var/log/") == "var_log"


def test_proc_id():
    assert proc_id("Home Assistant") == "home_assistant"
    assert proc_id("mosquitto") == "mosquitto"


def test_read_core_fields(monkeypatch):
    monkeypatch.setattr(system, "_fan_rpm", lambda: None)
    mon = SystemMonitor(disk_paths=["/"])
    r = mon.read()
    assert 0 <= r["ram_percent"] <= 100
    assert r["ram_total_mb"] > 0
    assert "swap_percent" in r and "uptime" in r and r["cpu_cores"] >= 1
    assert "root" in r["disk"]
    assert set(r["disk"]["root"]) == {"percent", "free_gb", "total_gb"}


def test_network_rate_after_two_reads(monkeypatch):
    monkeypatch.setattr(system, "_fan_rpm", lambda: None)
    mon = SystemMonitor()
    mon.read()           # seeds baseline — no rate yet
    r2 = mon.read()
    assert "net_tx_kbps" in r2 and "net_rx_kbps" in r2


def test_fan_omitted_when_absent(monkeypatch):
    monkeypatch.setattr(system, "_fan_rpm", lambda: None)
    assert SystemMonitor().has_fan is False
    assert "fan_rpm" not in SystemMonitor().read()


def test_fan_present(monkeypatch):
    monkeypatch.setattr(system, "_fan_rpm", lambda: 2400)
    mon = SystemMonitor()
    assert mon.has_fan is True
    assert mon.read()["fan_rpm"] == 2400


def test_processes_substring_match(monkeypatch):
    class P:
        def __init__(self, info): self.info = info
    procs = [P({"name": "mosquitto", "cmdline": ["/usr/sbin/mosquitto", "-c", "x"]}),
             P({"name": "python3", "cmdline": ["python3", "-m", "homeassistant"]})]
    monkeypatch.setattr(system.psutil, "process_iter", lambda attrs=None: iter(procs))
    mon = SystemMonitor(watch_processes=["mosquitto", "homeassistant", "nginx"])
    out = mon.processes()
    assert out == {"mosquitto": True, "homeassistant": True, "nginx": False}


def test_processes_empty_when_no_watch():
    assert SystemMonitor().processes() == {}


def test_info_fields():
    info = SystemMonitor().info()
    assert info["cpu_cores"] >= 1 and info["os"] and info["architecture"]
